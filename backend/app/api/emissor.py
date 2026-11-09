"""Emissor de NFS-e: cadastros (empresas emissoras, dados do prestador, serviços e tomadores)."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.escopo import escritorio_atual
from app.core import brasilapi
from app.core.certificados import situacao_validade
from app.core.db import sessao
from app.emissor import tabelas
from app.fiscal.documentos import cnpj_valido, cpf_valido, raiz_cnpj
from app.models import Certificado, EmissorEmpresa, Empresa, NotaEmitida, ServicoEmissor, Tomador

router = APIRouter(prefix="/api/emissor", tags=["emissor"])

OP_SIMPLES = {"1", "2", "3"}       # não optante | MEI | ME/EPP
REG_AP_TRIB_SN = {"1", "2", "3"}
REG_ESP_TRIB = {"0", "1", "2", "3", "4", "5", "6", "9"}


# ---------------------------------------------------------------------------
# Esquemas
# ---------------------------------------------------------------------------

class ConfigIn(BaseModel):
    inscricao_municipal: str | None = None
    op_simples: str
    reg_ap_trib_sn: str | None = None
    reg_esp_trib: str = "0"
    serie: str = "1"
    proximo_numero: int = Field(1, ge=1)
    cod_municipio: str | None = None
    percentual_tributos: Decimal | None = Field(None, ge=0, le=100)


class EmissaoLote(BaseModel):
    empresa_ids: list[int]
    emite: bool


class ServicoIn(BaseModel):
    descricao: str
    ctribnac: str
    cnbs: str
    ctribmun: str | None = None
    cindop: str | None = None
    cclasstrib: str | None = None
    ativo: bool = True


class TomadorIn(BaseModel):
    documento: str
    nome: str
    inscricao_municipal: str | None = None
    cep: str | None = None
    cod_municipio: str | None = None
    municipio: str | None = None
    uf: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    telefone: str | None = None
    email: str | None = None


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def _dig(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def _txt(v: str | None) -> str | None:
    v = re.sub(r"\s+", " ", v or "").strip()
    return v or None


def _empresa(db: Session, empresa_id: int, esc: int) -> Empresa:
    e = db.get(Empresa, empresa_id)
    if e is None or e.escritorio_id != esc:
        raise HTTPException(404, "Empresa não encontrada.")
    return e


def config_prestador(db: Session, e: Empresa) -> EmissorEmpresa:
    """Dados de prestador; na primeira vez, o regime vem do Simples informado pela BrasilAPI."""
    c = db.get(EmissorEmpresa, e.id)
    if c is None:
        d = e.dados_brasilapi or {}
        if d.get("opcao_pelo_mei"):
            op, ap = "2", None
        elif d.get("opcao_pelo_simples"):
            op, ap = "3", "1"
        else:
            op, ap = "1", None
        ibge = d.get("codigo_municipio_ibge")
        c = EmissorEmpresa(empresa_id=e.id, op_simples=op, reg_ap_trib_sn=ap, reg_esp_trib="0", serie="1", proximo_numero=1,
                           cod_municipio=str(ibge) if ibge else None)
        db.add(c)
        db.flush()
    return c


def certificado_emissor(db: Session, e: Empresa) -> Certificado | None:
    """Certificado que assina a DPS: tem que ser da própria empresa (procuração não vale, E0718)."""
    if not (e.is_contabilidade or e.modo_certificado == "proprio") or not e.certificado_id:
        return None
    c = db.get(Certificado, e.certificado_id)
    if c is None or c.tipo != "e-CNPJ" or raiz_cnpj(c.titular_doc) != raiz_cnpj(e.cnpj):
        return None
    return c


def _item_empresa(db: Session, e: Empresa) -> dict:
    cfg = db.get(EmissorEmpresa, e.id)
    cert = certificado_emissor(db, e)
    n_serv = db.scalar(select(func.count()).select_from(ServicoEmissor)
                       .where(ServicoEmissor.empresa_id == e.id, ServicoEmissor.ativo)) or 0
    pendencias = []
    if cert is None:
        pendencias.append("Cadastre o certificado A1 da própria empresa (a procuração não serve para emitir).")
    elif situacao_validade(cert.validade) == "vencido":
        pendencias.append(f"O certificado venceu em {cert.validade:%d/%m/%Y}.")
    if n_serv == 0:
        pendencias.append("Cadastre pelo menos um serviço.")
    if cfg is not None and not cfg.cod_municipio:
        pendencias.append("Informe o município da empresa (código IBGE) nos dados do prestador.")
    if not e.ativa:
        pendencias.append("A empresa está inativa.")
    return {
        "id": e.id, "cnpj": e.cnpj, "razao_social": e.razao_social, "nome_fantasia": e.nome_fantasia,
        "apelido": e.apelido, "uf": e.uf, "municipio": e.municipio, "ativa": e.ativa,
        "is_contabilidade": e.is_contabilidade, "emite_nfse": e.emite_nfse,
        "certificado": None if cert is None else {
            "titular_nome": cert.titular_nome, "titular_doc": cert.titular_doc, "validade": cert.validade,
            "situacao": situacao_validade(cert.validade), "filial": cert.titular_doc != e.cnpj},
        "servicos": n_serv,
        "config": None if cfg is None else {
            "inscricao_municipal": cfg.inscricao_municipal, "op_simples": cfg.op_simples,
            "reg_ap_trib_sn": cfg.reg_ap_trib_sn, "reg_esp_trib": cfg.reg_esp_trib,
            "serie": cfg.serie, "proximo_numero": cfg.proximo_numero, "cod_municipio": cfg.cod_municipio,
            "percentual_tributos": float(cfg.percentual_tributos) if cfg.percentual_tributos is not None else None},
        "pendencias": pendencias,
        "pronta": e.emite_nfse and not pendencias,
    }


def _servico_out(s: ServicoEmissor) -> dict:
    serv = tabelas.servico(s.ctribnac)
    return {
        "id": s.id, "empresa_id": s.empresa_id, "descricao": s.descricao, "ctribnac": s.ctribnac,
        "ctribnac_formatado": tabelas.formatar_ctribnac(s.ctribnac),
        "ctribnac_descricao": serv["descricao"] if serv else None,
        "cnbs": s.cnbs, "cnbs_formatado": tabelas.formatar_nbs(s.cnbs), "cnbs_descricao": tabelas.nbs_descricao(s.cnbs),
        "ctribmun": s.ctribmun, "cindop": s.cindop, "cclasstrib": s.cclasstrib, "ativo": s.ativo,
        "atualizado_em": s.atualizado_em,
    }


def _validar_servico(d: ServicoIn) -> dict:
    descricao = (d.descricao or "").strip()
    if not descricao:
        raise HTTPException(422, "Informe a descrição do serviço.")
    if len(descricao) > 2000:
        raise HTTPException(422, "A descrição pode ter no máximo 2.000 caracteres.")
    ctrib, nbs = _dig(d.ctribnac), _dig(d.cnbs)
    if tabelas.servico(ctrib) is None:
        raise HTTPException(422, "Código de tributação nacional não encontrado na lista oficial (LC 116).")
    if len(nbs) != 9 or tabelas.nbs_descricao(nbs) is None:
        raise HTTPException(422, "Código NBS não encontrado na tabela oficial (NBS 2.0).")
    campos = {"descricao": descricao, "ctribnac": ctrib, "cnbs": nbs, "ativo": d.ativo}
    for nome, tam, rotulo in (("ctribmun", 3, "O código municipal"), ("cindop", 6, "O indicador da operação (cIndOp)"),
                              ("cclasstrib", 6, "A classificação tributária (cClassTrib)")):
        v = _dig(getattr(d, nome))
        if v and len(v) != tam:
            raise HTTPException(422, f"{rotulo} deve ter {tam} dígitos.")
        campos[nome] = v or None
    return campos


def _tomador_out(t: Tomador) -> dict:
    return {c: getattr(t, c) for c in ("id", "documento", "nome", "inscricao_municipal", "cep", "cod_municipio",
                                       "municipio", "uf", "logradouro", "numero", "complemento", "bairro",
                                       "telefone", "email", "atualizado_em")}


def _documento(v: str) -> str:
    d = _dig(v)
    if (len(d) == 14 and cnpj_valido(d)) or (len(d) == 11 and cpf_valido(d)):
        return d
    raise HTTPException(422, "CNPJ ou CPF inválido: confira os dígitos.")


def _validar_tomador(d: TomadorIn) -> dict:
    nome = _txt(d.nome)
    if not nome:
        raise HTTPException(422, "Informe o nome ou a razão social do tomador.")
    campos = {"documento": _documento(d.documento), "nome": nome[:300]}
    cep, mun, fone = _dig(d.cep), _dig(d.cod_municipio), _dig(d.telefone)
    if cep and len(cep) != 8:
        raise HTTPException(422, "O CEP deve ter 8 dígitos.")
    if mun and len(mun) != 7:
        raise HTTPException(422, "O código IBGE do município deve ter 7 dígitos.")
    if fone and not 6 <= len(fone) <= 20:
        raise HTTPException(422, "Telefone inválido: informe DDD e número.")
    email = _txt(d.email)
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "E-mail inválido.")
    if any([cep, mun, _txt(d.logradouro)]) and not (cep and mun and _txt(d.logradouro) and _txt(d.numero) and _txt(d.bairro)):
        raise HTTPException(422, "Endereço incompleto: informe CEP, município, logradouro, número e bairro, ou deixe o endereço em branco.")
    campos.update(cep=cep or None, cod_municipio=mun or None, telefone=fone or None, email=email,
                  inscricao_municipal=_txt(d.inscricao_municipal), municipio=_txt(d.municipio),
                  uf=(_txt(d.uf) or "").upper()[:2] or None, logradouro=_txt(d.logradouro),
                  numero=_txt(d.numero), complemento=_txt(d.complemento), bairro=_txt(d.bairro))
    return campos


def tomador_da_brasilapi(bruto: dict) -> dict:
    tipo = _txt(bruto.get("descricao_tipo_de_logradouro"))
    logr = _txt(bruto.get("logradouro"))
    if tipo and logr and not logr.upper().startswith(tipo.upper()):
        logr = f"{tipo} {logr}"
    ibge = bruto.get("codigo_municipio_ibge")
    return {
        "nome": _txt(bruto.get("razao_social")), "cep": _dig(bruto.get("cep")) or None,
        "cod_municipio": str(ibge) if ibge else None,
        "municipio": brasilapi._titulo(bruto.get("municipio")), "uf": _txt(bruto.get("uf")),
        "logradouro": logr, "numero": _txt(bruto.get("numero")) or "S/N",
        "complemento": _txt(bruto.get("complemento")), "bairro": _txt(bruto.get("bairro")),
        "telefone": _dig(bruto.get("ddd_telefone_1")) or None,
        "email": (_txt(bruto.get("email")) or "").lower() or None,
    }


# ---------------------------------------------------------------------------
# Empresas emissoras
# ---------------------------------------------------------------------------

@router.get("/empresas")
def listar_empresas(db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    empresas = db.scalars(select(Empresa).where(Empresa.escritorio_id == esc)
                          .order_by(Empresa.is_contabilidade.desc(), Empresa.razao_social))
    return [_item_empresa(db, e) for e in empresas]


@router.put("/empresas/emissao")
def definir_emissao(dados: EmissaoLote, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    ids = set(dados.empresa_ids)
    if not ids:
        raise HTTPException(422, "Selecione pelo menos uma empresa.")
    empresas = list(db.scalars(select(Empresa).where(Empresa.escritorio_id == esc, Empresa.id.in_(ids))))
    if len(empresas) != len(ids):
        raise HTTPException(404, "Empresa não encontrada.")
    for e in empresas:
        e.emite_nfse = dados.emite
        if dados.emite:
            config_prestador(db, e)
    db.commit()
    return {"atualizadas": len(empresas)}


@router.get("/empresas/{empresa_id}")
def obter_empresa(empresa_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    e = _empresa(db, empresa_id, esc)
    config_prestador(db, e)
    db.commit()
    return _item_empresa(db, e)


@router.put("/empresas/{empresa_id}/config")
def salvar_config(empresa_id: int, dados: ConfigIn, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    e = _empresa(db, empresa_id, esc)
    if dados.op_simples not in OP_SIMPLES:
        raise HTTPException(422, "Situação no Simples Nacional inválida.")
    ap = dados.reg_ap_trib_sn or None
    if dados.op_simples == "3":
        if ap not in REG_AP_TRIB_SN:
            raise HTTPException(422, "Para ME/EPP do Simples, informe o regime de apuração dos tributos.")
    elif ap:
        raise HTTPException(422, "O regime de apuração do Simples só vale para ME/EPP optante.")
    if dados.reg_esp_trib not in REG_ESP_TRIB:
        raise HTTPException(422, "Regime especial de tributação inválido.")
    serie = _dig(dados.serie)
    if not serie or not 1 <= int(serie) <= 49999:
        raise HTTPException(422, "A série deve estar entre 1 e 49999 (faixa de aplicativo próprio).")
    im = _txt(dados.inscricao_municipal)
    if im and len(im) > 15:
        raise HTTPException(422, "A inscrição municipal pode ter no máximo 15 caracteres.")
    mun = _dig(dados.cod_municipio)
    if mun and len(mun) != 7:
        raise HTTPException(422, "O código IBGE do município deve ter 7 dígitos.")
    c = config_prestador(db, e)
    c.cod_municipio = mun or c.cod_municipio
    c.percentual_tributos = dados.percentual_tributos
    c.inscricao_municipal, c.op_simples, c.reg_ap_trib_sn = im, dados.op_simples, ap
    c.reg_esp_trib, c.serie, c.proximo_numero = dados.reg_esp_trib, str(int(serie)), dados.proximo_numero
    db.commit()
    return _item_empresa(db, e)


# ---------------------------------------------------------------------------
# Serviços
# ---------------------------------------------------------------------------

@router.get("/empresas/{empresa_id}/servicos")
def listar_servicos(empresa_id: int, inativos: bool = False, db: Session = Depends(sessao),
                    esc: int = Depends(escritorio_atual)):
    _empresa(db, empresa_id, esc)
    stmt = select(ServicoEmissor).where(ServicoEmissor.empresa_id == empresa_id)
    if not inativos:
        stmt = stmt.where(ServicoEmissor.ativo)
    return [_servico_out(s) for s in db.scalars(stmt.order_by(ServicoEmissor.ativo.desc(), ServicoEmissor.descricao))]


@router.post("/empresas/{empresa_id}/servicos", status_code=201)
def criar_servico(empresa_id: int, dados: ServicoIn, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    _empresa(db, empresa_id, esc)
    s = ServicoEmissor(empresa_id=empresa_id, **_validar_servico(dados))
    db.add(s)
    db.commit()
    return _servico_out(s)


def _servico(db: Session, servico_id: int, esc: int) -> ServicoEmissor:
    s = db.get(ServicoEmissor, servico_id)
    if s is None or db.get(Empresa, s.empresa_id).escritorio_id != esc:
        raise HTTPException(404, "Serviço não encontrado.")
    return s


@router.put("/servicos/{servico_id}")
def editar_servico(servico_id: int, dados: ServicoIn, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    s = _servico(db, servico_id, esc)
    for k, v in _validar_servico(dados).items():
        setattr(s, k, v)
    db.commit()
    return _servico_out(s)


@router.delete("/servicos/{servico_id}", status_code=204)
def excluir_servico(servico_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    db.delete(_servico(db, servico_id, esc))
    db.commit()


# ---------------------------------------------------------------------------
# Tabelas oficiais
# ---------------------------------------------------------------------------

@router.get("/codigos/servicos")
def codigos_servicos(q: str = "", limite: int = Query(30, ge=1, le=400)):
    return tabelas.buscar_servicos(q, limite)


@router.get("/codigos/nbs")
def codigos_nbs(q: str = "", limite: int = Query(30, ge=1, le=200)):
    return tabelas.buscar_nbs(q, limite)


@router.get("/codigos/sugestoes/{ctribnac}")
def codigos_sugestoes(ctribnac: str):
    return tabelas.sugestoes(_dig(ctribnac))


# ---------------------------------------------------------------------------
# Tomadores
# ---------------------------------------------------------------------------

@router.get("/tomadores")
def listar_tomadores(q: str = "", db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    stmt = select(Tomador).where(Tomador.escritorio_id == esc)
    if q.strip():
        conds = [Tomador.nome.ilike(f"%{q.strip()}%")]
        if _dig(q):
            conds.append(Tomador.documento.like(f"%{_dig(q)}%"))
        stmt = stmt.where(or_(*conds))
    return [_tomador_out(t) for t in db.scalars(stmt.order_by(Tomador.nome).limit(200))]


@router.get("/tomadores/consulta/{documento}")
def consultar_tomador(documento: str, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    """Primeiro os tomadores já salvos; se for CNPJ novo, a BrasilAPI. Nada é gravado aqui."""
    doc = _documento(documento)
    salvo = db.scalar(select(Tomador).where(Tomador.escritorio_id == esc, Tomador.documento == doc))
    if salvo:
        return {"origem": "salvo", "tomador": _tomador_out(salvo), "aviso": None}
    if len(doc) == 11:
        return {"origem": "manual", "tomador": {"documento": doc}, "aviso": "CPF não é consultado: preencha os dados."}
    try:
        dados = brasilapi.consultar(doc)
    except brasilapi.BrasilApiErro as ex:
        return {"origem": "manual", "tomador": {"documento": doc}, "aviso": str(ex)}
    aviso = None
    if dados.get("situacao_cadastral") and dados["situacao_cadastral"] != "ATIVA":
        aviso = f"A situação cadastral na Receita é {dados['situacao_cadastral']}."
    return {"origem": "brasilapi", "tomador": {"documento": doc, **tomador_da_brasilapi(dados["bruto"])}, "aviso": aviso}


@router.post("/tomadores", status_code=201)
def salvar_tomador(dados: TomadorIn, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    """Cria ou atualiza pelo CNPJ/CPF."""
    campos = _validar_tomador(dados)
    t = db.scalar(select(Tomador).where(Tomador.escritorio_id == esc, Tomador.documento == campos["documento"]))
    if t is None:
        t = Tomador(escritorio_id=esc)
        db.add(t)
    for k, v in campos.items():
        setattr(t, k, v)
    db.commit()
    return _tomador_out(t)


def _tomador(db: Session, tomador_id: int, esc: int) -> Tomador:
    t = db.get(Tomador, tomador_id)
    if t is None or t.escritorio_id != esc:
        raise HTTPException(404, "Tomador não encontrado.")
    return t


@router.put("/tomadores/{tomador_id}")
def editar_tomador(tomador_id: int, dados: TomadorIn, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    t = _tomador(db, tomador_id, esc)
    campos = _validar_tomador(dados)
    outro = db.scalar(select(Tomador).where(Tomador.escritorio_id == esc, Tomador.documento == campos["documento"],
                                            Tomador.id != t.id))
    if outro:
        raise HTTPException(409, "Já existe um tomador salvo com esse CNPJ/CPF.")
    for k, v in campos.items():
        setattr(t, k, v)
    db.commit()
    return _tomador_out(t)


@router.delete("/tomadores/{tomador_id}", status_code=204)
def excluir_tomador(tomador_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    db.delete(_tomador(db, tomador_id, esc))
    db.commit()


# ---------------------------------------------------------------------------
# Emissão
# ---------------------------------------------------------------------------

class EmissaoIn(BaseModel):
    empresa_id: int
    servico_id: int
    descricao: str | None = None
    competencia: date
    valor: Decimal = Field(gt=0)
    tomador: TomadorIn | None = None
    salvar_tomador: bool = True
    desconto: Decimal = Field(Decimal("0"), ge=0)
    iss_retido: bool = False
    aliquota_iss: Decimal | None = Field(None, gt=0, le=5)
    ret_pis: Decimal = Field(Decimal("0"), ge=0)
    ret_cofins: Decimal = Field(Decimal("0"), ge=0)
    ret_csll: Decimal = Field(Decimal("0"), ge=0)
    ret_irrf: Decimal = Field(Decimal("0"), ge=0)
    ret_cp: Decimal = Field(Decimal("0"), ge=0)
    cod_municipio_prestacao: str | None = None
    info_complementar: str | None = Field(None, max_length=2000)


class CancelamentoIn(BaseModel):
    motivo: str
    justificativa: str


def _entrada(d: EmissaoIn):
    from app.emissor.motor import Entrada
    mun = _dig(d.cod_municipio_prestacao)
    if mun and len(mun) != 7:
        raise HTTPException(422, "O código IBGE do local da prestação deve ter 7 dígitos.")
    return Entrada(
        empresa_id=d.empresa_id, servico_id=d.servico_id, descricao=d.descricao, competencia=d.competencia,
        valor=d.valor, tomador=_validar_tomador(d.tomador) if d.tomador else None, salvar_tomador=d.salvar_tomador,
        desconto=d.desconto, iss_retido=d.iss_retido, aliquota_iss=d.aliquota_iss, ret_pis=d.ret_pis,
        ret_cofins=d.ret_cofins, ret_csll=d.ret_csll, ret_irrf=d.ret_irrf, ret_cp=d.ret_cp,
        cod_municipio_prestacao=mun or None, info_complementar=d.info_complementar,
    )


def _nota_out(db: Session, n: NotaEmitida) -> dict:
    e = db.get(Empresa, n.empresa_id)
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    return {
        "id": n.id, "empresa_id": n.empresa_id, "empresa_nome": e.apelido or e.nome_fantasia or e.razao_social,
        "empresa_cnpj": e.cnpj, "servico_id": n.servico_id, "ambiente": n.ambiente,
        "homologacao": n.ambiente == 2, "serie": n.serie, "numero": n.numero, "id_dps": n.id_dps,
        "situacao": n.situacao, "competencia": n.competencia, "tomador": n.tomador, "descricao": n.descricao,
        "ctribnac": n.ctribnac, "ctribnac_formatado": tabelas.formatar_ctribnac(n.ctribnac),
        "cnbs": n.cnbs, "cnbs_formatado": tabelas.formatar_nbs(n.cnbs), "ctribmun": n.ctribmun,
        "cod_municipio_prestacao": n.cod_municipio_prestacao,
        "valor_servico": f(n.valor_servico), "desconto": f(n.desconto), "iss_retido": n.iss_retido,
        "aliquota_iss": f(n.aliquota_iss), "ret_pis": f(n.ret_pis), "ret_cofins": f(n.ret_cofins),
        "ret_csll": f(n.ret_csll), "ret_irrf": f(n.ret_irrf), "ret_cp": f(n.ret_cp),
        "info_complementar": n.info_complementar, "chave": n.chave, "numero_nfse": n.numero_nfse,
        "valor_iss": f(n.valor_iss), "valor_liquido": f(n.valor_liquido), "erros": n.erros or [],
        "mensagem": n.mensagem, "motivo_cancelamento": n.motivo_cancelamento,
        "criado_em": n.criado_em, "enviado_em": n.enviado_em, "autorizado_em": n.autorizado_em,
        "cancelado_em": n.cancelado_em,
    }


def _erro_emissao(ex) -> HTTPException:
    return HTTPException(ex.status, str(ex))


@router.get("/ambiente")
def ambiente_emissor():
    from app.emissor.motor import ambiente
    a = ambiente()
    return {"ambiente": a, "producao": a == 1,
            "descricao": "Produção" if a == 1 else "Homologação (produção restrita, sem valor fiscal)"}


@router.post("/notas", status_code=201)
def emitir_nota(dados: EmissaoIn, request: Request, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    from app.emissor import motor
    u = getattr(request.state, "usuario", None)
    try:
        n = motor.emitir(db, esc, u.id if u else None, _entrada(dados))
    except motor.ErroEmissao as ex:
        raise _erro_emissao(ex) from None
    return _nota_out(db, n)


@router.get("/notas")
def listar_notas(empresa_id: int | None = None, situacao: str | None = None, limite: int = Query(100, ge=1, le=500),
                 db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    stmt = select(NotaEmitida).where(NotaEmitida.escritorio_id == esc)
    if empresa_id:
        stmt = stmt.where(NotaEmitida.empresa_id == empresa_id)
    if situacao:
        stmt = stmt.where(NotaEmitida.situacao == situacao)
    return [_nota_out(db, n) for n in db.scalars(stmt.order_by(NotaEmitida.id.desc()).limit(limite))]


def _nota(db: Session, nota_id: int, esc: int) -> NotaEmitida:
    n = db.get(NotaEmitida, nota_id)
    if n is None or n.escritorio_id != esc:
        raise HTTPException(404, "Nota não encontrada.")
    return n


@router.get("/notas/{nota_id}")
def obter_nota(nota_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    return _nota_out(db, _nota(db, nota_id, esc))


@router.post("/notas/{nota_id}/reenviar")
def reenviar_nota(nota_id: int, dados: EmissaoIn | None = None, db: Session = Depends(sessao),
                  esc: int = Depends(escritorio_atual)):
    from app.emissor import motor
    try:
        n = motor.reenviar(db, esc, nota_id, _entrada(dados) if dados else None)
    except motor.ErroEmissao as ex:
        raise _erro_emissao(ex) from None
    return _nota_out(db, n)


@router.post("/notas/{nota_id}/cancelar")
def cancelar_nota(nota_id: int, dados: CancelamentoIn, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    from app.emissor import motor
    try:
        n = motor.cancelar(db, esc, nota_id, dados.motivo, dados.justificativa)
    except motor.ErroEmissao as ex:
        raise _erro_emissao(ex) from None
    return _nota_out(db, n)


@router.get("/notas/{nota_id}/xml")
def xml_nota(nota_id: int, tipo: str = Query("nfse", pattern="^(nfse|dps|cancelamento)$"),
             db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    from app.core.config import config
    n = _nota(db, nota_id, esc)
    rel = {"nfse": n.xml_nfse_path, "dps": n.xml_dps_path, "cancelamento": n.xml_cancelamento_path}[tipo]
    if not rel or not (config().dados_dir / rel).is_file():
        raise HTTPException(404, "Arquivo não disponível para esta nota.")
    nome = (config().dados_dir / rel).name
    return Response((config().dados_dir / rel).read_bytes(), media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.get("/notas/{nota_id}/danfse")
def danfse_nota(nota_id: int, download: int = 0, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    from app.core.config import config
    from app.fiscal.danfse import gerar_danfse
    n = _nota(db, nota_id, esc)
    if not n.xml_nfse_path or not (config().dados_dir / n.xml_nfse_path).is_file():
        raise HTTPException(404, "A nota ainda não foi autorizada.")
    marca = "CANCELADA" if n.situacao == "cancelada" else None
    pdf = gerar_danfse((config().dados_dir / n.xml_nfse_path).read_bytes(), marca_dagua=marca)
    disp = "attachment" if download else "inline"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'{disp}; filename="DANFSe_{n.numero_nfse or n.id}_{n.chave}.pdf"',
                             "Cache-Control": "no-cache"})
