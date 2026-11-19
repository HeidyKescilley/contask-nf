"""Emissor de NFS-e: lista de notas da empresa (com filtros), duplicar, rascunhos e notas recorrentes."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from lxml import etree
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.emissor import EmissaoIn, _dig, _empresa, _entrada, _nota_out, config_prestador
from app.api.escopo import escritorio_atual
from app.core.config import config
from app.core.db import sessao
from app.emissor import tabelas, textos
from app.emissor.dps import BRASILIA, PRODUCAO
from app.emissor.motor import ambiente
from app.models import EmissorEmpresa, Empresa, Nota, NotaEmitida, NotaRascunho, NotaRecorrente, ServicoEmissor, Tomador

router = APIRouter(prefix="/api/emissor", tags=["emissor"])

SITUACOES = {"autorizada", "cancelada", "rejeitada", "pendente", "enviando"}


# ---------------------------------------------------------------------------
# Lista da empresa: notas do Contask + notas prestadas que vieram do ADN
# ---------------------------------------------------------------------------

def _com_fuso(dt: datetime | None, fuso) -> datetime | None:
    """O SQLite devolve sem fuso: as notas do Contask são gravadas em UTC; as do ADN, no horário do XML (Brasília)."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=fuso)


def _dia(dt: datetime | None) -> date | None:
    return dt.astimezone(BRASILIA).date() if dt else None


def _nota_adn(n: Nota) -> dict:
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    return {
        "origem": "adn", "id": n.id, "empresa_id": n.empresa_id, "data": _com_fuso(n.data_emissao, BRASILIA), "chave": n.chave,
        "numero_nfse": n.numero, "serie": n.serie, "numero": int(n.n_dps) if (n.n_dps or "").isdigit() else None,
        "competencia": n.competencia, "tomador": {"documento": n.tomador_doc, "nome": n.tomador_nome} if n.tomador_doc or n.tomador_nome else None,
        "valor_servico": f(n.valor_servico), "valor_liquido": f(n.valor_liquido), "situacao": n.status,
        "homologacao": False, "descricao": None, "mensagem": n.status_detalhe, "tem_xml": bool(n.xml_path),
    }


def _confere(item: dict, q: str, numero: str, situacao: str) -> bool:
    if situacao and item["situacao"] != situacao:
        return False
    if numero:
        alvos = {str(item.get("numero_nfse") or ""), str(item.get("numero") or "")}
        if not any(numero == a.lstrip("0") or numero == a for a in alvos if a):
            return False
    if q:
        t = item.get("tomador") or {}
        texto = " ".join(filter(None, [t.get("nome"), item.get("descricao")])).lower()
        dig = _dig(q)
        if q.lower() not in texto and not (dig and dig in (t.get("documento") or "")):
            return False
    return True


@router.get("/empresas/{empresa_id}/notas")
def notas_da_empresa(empresa_id: int, inicio: date | None = None, fim: date | None = None, q: str = "",
                     numero: str = "", situacao: str = "", db: Session = Depends(sessao),
                     esc: int = Depends(escritorio_atual)):
    """Notas do ambiente em que a empresa emite. Em produção, inclui as prestadas que vieram do ADN
    (emitidas fora do Contask), para consultar e duplicar."""
    e = _empresa(db, empresa_id, esc)
    cfg = config_prestador(db, e)
    amb = ambiente(cfg)
    if inicio and fim and inicio > fim:
        raise HTTPException(422, "A data inicial é maior que a final.")
    if situacao and situacao not in SITUACOES:
        raise HTTPException(422, "Situação inválida.")
    q, numero = q.strip(), _dig(numero).lstrip("0")

    def no_periodo(d: date | None) -> bool:
        return d is not None and (not inicio or d >= inicio) and (not fim or d <= fim)

    from app.emissor.situacao import conciliar_com_adn
    if conciliar_com_adn(db, e.id):
        db.commit()
    itens = []
    chaves = set()
    for n in db.scalars(select(NotaEmitida).where(NotaEmitida.empresa_id == e.id, NotaEmitida.ambiente == amb)):
        if n.chave:
            chaves.add(n.chave)
        item = _nota_out(db, n)
        item["data"] = _com_fuso(n.autorizado_em or n.criado_em, timezone.utc)
        if no_periodo(_dia(item["data"])) and _confere(item, q, numero, situacao):
            itens.append(item)
    if amb == PRODUCAO:
        stmt = select(Nota).where(Nota.empresa_id == e.id, Nota.papel == "prestada")
        if inicio:  # margem de um dia por causa do fuso; o filtro exato é feito abaixo
            stmt = stmt.where(Nota.data_emissao >= datetime.combine(inicio - timedelta(days=1), time.min))
        if fim:
            stmt = stmt.where(Nota.data_emissao < datetime.combine(fim + timedelta(days=2), time.min))
        for n in db.scalars(stmt):
            if n.chave in chaves:
                continue  # já está na lista como nota do Contask
            item = _nota_adn(n)
            if no_periodo(_dia(item["data"])) and _confere(item, q, numero, situacao):
                itens.append(item)

    itens.sort(key=lambda i: i["data"] or datetime.min.replace(tzinfo=BRASILIA), reverse=True)
    autorizadas = [i for i in itens if i["situacao"] == "autorizada"]
    return {
        "ambiente": amb,
        "notas": itens,
        "totais": {"quantidade": len(itens), "autorizadas": len(autorizadas),
                   "valor_autorizado": round(sum(i["valor_servico"] or 0 for i in autorizadas), 2)},
    }


# ---------------------------------------------------------------------------
# Duplicar nota do ADN: lê o XML e devolve os campos do formulário de emissão
# ---------------------------------------------------------------------------

N = {"n": "http://www.sped.fazenda.gov.br/nfse"}
PADRAO_PISCOFINS = {"pis": Decimal("0.65"), "cofins": Decimal("3"), "csll": Decimal("1")}
# tpRetPisCofins -> quais contribuições foram retidas (inverso de Retencoes.tp_ret_pis_cofins)
RETIDAS = {"3": ("pis", "cofins", "csll"), "4": ("pis", "cofins"), "5": ("pis",), "6": ("cofins",),
           "7": ("cofins", "csll"), "8": ("csll",), "9": ("pis", "csll")}


def _t(el, caminho: str) -> str | None:
    if el is None:
        return None
    x = el.find(caminho, N)
    return x.text.strip() if x is not None and x.text else None


def _num(v: str | None) -> float:
    try:
        return float(Decimal(v)) if v else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def modelo_do_xml(xml: bytes, fixo: str | None = None) -> dict:
    raiz = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    dps = raiz.find(".//n:infDPS", N)
    if dps is None:
        raise HTTPException(422, "O XML desta nota não tem a DPS.")
    toma = dps.find("n:toma", N)
    tomador = None
    if toma is not None:
        nac = toma.find("n:end/n:endNac", N)
        tomador = {
            "documento": _t(toma, "n:CNPJ") or _t(toma, "n:CPF") or "", "nome": _t(toma, "n:xNome") or "",
            "inscricao_municipal": _t(toma, "n:IM"), "cep": _t(nac, "n:CEP"), "cod_municipio": _t(nac, "n:cMun"),
            "logradouro": _t(toma, "n:end/n:xLgr"), "numero": _t(toma, "n:end/n:nro"),
            "complemento": _t(toma, "n:end/n:xCpl"), "bairro": _t(toma, "n:end/n:xBairro"),
            "telefone": _t(toma, "n:fone"), "email": _t(toma, "n:email"), "municipio": None, "uf": None,
        }
    cs = dps.find("n:serv/n:cServ", N)
    trib = dps.find("n:valores/n:trib", N)
    fed = trib.find("n:tribFed", N) if trib is not None else None
    ret = {"ret_pis": 0.0, "ret_cofins": 0.0, "ret_csll": 0.0}
    contrib = Decimal(str(_num(_t(fed, "n:vRetCSLL"))))
    retidas = RETIDAS.get(_t(fed, "n:piscofins/n:tpRetPisCofins") or "", ())
    vpis, vcofins = _t(fed, "n:piscofins/n:vPis"), _t(fed, "n:piscofins/n:vCofins")
    if retidas and contrib > 0:
        if vpis or vcofins:
            p = Decimal(vpis or "0") if "pis" in retidas else Decimal("0")
            c = Decimal(vcofins or "0") if "cofins" in retidas else Decimal("0")
            ret.update(ret_pis=float(p), ret_cofins=float(c), ret_csll=float(max(contrib - p - c, Decimal("0"))))
        else:  # só a soma: reparte pelas alíquotas padrão (0,65 / 3 / 1)
            peso = sum(PADRAO_PISCOFINS[k] for k in retidas)
            acum = Decimal("0")
            for i, k in enumerate(retidas):
                v = contrib - acum if i == len(retidas) - 1 else (contrib * PADRAO_PISCOFINS[k] / peso).quantize(Decimal("0.01"))
                acum += v
                ret[f"ret_{k}"] = float(v)
    elif contrib > 0:
        ret["ret_csll"] = float(contrib)
    info, tem_simples, tem_procon = textos.separar(_t(dps, "n:serv/n:infoCompl/n:xInfComp"), fixo)
    ibs = dps.find("n:IBSCBS", N)
    return {
        "tomador": tomador, "descricao": _t(cs, "n:xDescServ") or "", "ctribnac": _t(cs, "n:cTribNac"),
        "cnbs": _t(cs, "n:cNBS"), "ctribmun": _t(cs, "n:cTribMun"), "cindop": _t(ibs, "n:cIndOp"),
        # NT 004 (produção até a troca de leiaute): trib/gIBSCBS/cClassTrib; NT 009: trib/cClassTrib
        "cclasstrib": _t(ibs, "n:valores/n:trib/n:gIBSCBS/n:cClassTrib") or _t(ibs, "n:valores/n:trib/n:cClassTrib"),
        "cod_municipio_prestacao": _t(dps, "n:serv/n:locPrest/n:cLocPrestacao"),
        "valor_servico": _num(_t(dps, "n:valores/n:vServPrest/n:vServ")),
        "desconto": _num(_t(dps, "n:valores/n:vDescCondIncond/n:vDescIncond")),
        "iss_retido": _t(trib, "n:tribMun/n:tpRetISSQN") in ("2", "3"),
        "aliquota_iss": _num(_t(trib, "n:tribMun/n:pAliq")) or None,
        "ret_irrf": _num(_t(fed, "n:vRetIRRF")), "ret_cp": _num(_t(fed, "n:vRetCP")), **ret,
        "info_usuario": info, "texto_simples": tem_simples, "texto_procon": tem_procon,
        "texto_fixo": textos.tem_fixo(_t(dps, "n:serv/n:infoCompl/n:xInfComp"), fixo),
    }


@router.get("/empresas/{empresa_id}/notas/adn/{nota_id}/modelo")
def modelo_nota_adn(empresa_id: int, nota_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    e = _empresa(db, empresa_id, esc)
    n = db.get(Nota, nota_id)
    if n is None or n.empresa_id != e.id or n.papel != "prestada":
        raise HTTPException(404, "Nota não encontrada.")
    if not n.xml_path or not (config().dados_dir / n.xml_path).is_file():
        raise HTTPException(404, "O XML desta nota não está no computador: rode a busca de novo para baixá-lo.")
    cfg = db.get(EmissorEmpresa, e.id)
    m = modelo_do_xml((config().dados_dir / n.xml_path).read_bytes(), cfg.texto_fixo if cfg else None)
    if m["tomador"] and m["tomador"]["documento"]:
        salvo = db.scalar(select(Tomador).where(Tomador.escritorio_id == esc, Tomador.documento == m["tomador"]["documento"]))
        if salvo:  # completa município/UF e o que faltar com o cadastro salvo
            for k, v in m["tomador"].items():
                if not v and getattr(salvo, k, None):
                    m["tomador"][k] = getattr(salvo, k)
    serv = servico_igual(db, e.id, m)
    return {**m, **_rotulos(m), "servico_id": serv.id if serv else None, "numero_nfse": n.numero, "empresa_id": e.id,
            "competencia": n.competencia or m.get("competencia"), "chave": n.chave, "situacao": n.status}


def servico_igual(db: Session, empresa_id: int, m: dict) -> ServicoEmissor | None:
    """Serviço cadastrado com exatamente os mesmos códigos da nota (senão a nota duplicada usa os códigos dela)."""
    chave = lambda x: tuple((x.get(k) if isinstance(x, dict) else getattr(x, k)) or None  # noqa: E731
                            for k in ("ctribnac", "cnbs", "ctribmun", "cindop", "cclasstrib"))
    alvo = chave(m)
    for s in db.scalars(select(ServicoEmissor).where(ServicoEmissor.empresa_id == empresa_id, ServicoEmissor.ativo,
                                                     ServicoEmissor.ctribnac == m.get("ctribnac"))
                        .order_by(ServicoEmissor.id)):
        if chave(s) == alvo:
            return s
    return None


def _rotulos(m: dict) -> dict:
    serv = tabelas.servico(m.get("ctribnac") or "")
    return {"ctribnac_formatado": tabelas.formatar_ctribnac(m["ctribnac"]) if m.get("ctribnac") else None,
            "ctribnac_descricao": serv["descricao"] if serv else None,
            "cnbs_formatado": tabelas.formatar_nbs(m["cnbs"]) if m.get("cnbs") else None,
            "cnbs_descricao": tabelas.nbs_descricao(m["cnbs"]) if m.get("cnbs") else None}


# ---------------------------------------------------------------------------
# Última nota da empresa: dados do prestador e do serviço para pré-preencher a configuração do emissor
# ---------------------------------------------------------------------------

def prestador_do_xml(xml: bytes) -> dict:
    raiz = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    dps = raiz.find(".//n:infDPS", N)
    if dps is None:
        raise ValueError("XML sem DPS")
    rt = dps.find("n:prest/n:regTrib", N)
    numero = _t(dps, "n:nDPS")
    return {
        "inscricao_municipal": _t(dps, "n:prest/n:IM"), "op_simples": _t(rt, "n:opSimpNac"),
        "reg_ap_trib_sn": _t(rt, "n:regApTribSN"), "reg_esp_trib": _t(rt, "n:regEspTrib"),
        "cod_municipio": _t(dps, "n:cLocEmi"), "serie": (_t(dps, "n:serie") or "").lstrip("0") or None,
        "numero_dps": int(numero) if numero and numero.isdigit() else None,
    }


@router.get("/empresas/{empresa_id}/ultima-nota")
def ultima_nota(empresa_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    """Última NFS-e prestada que veio do ADN (com XML): regime, IM, município e serviço, para pré-preencher."""
    e = _empresa(db, empresa_id, esc)
    pasta = config().dados_dir
    notas = db.scalars(select(Nota).where(Nota.empresa_id == e.id, Nota.papel == "prestada", Nota.xml_path.is_not(None))
                       .order_by(Nota.data_emissao.desc(), Nota.id.desc()).limit(20))
    for n in notas:
        arq = pasta / n.xml_path
        if not arq.is_file():
            continue
        try:
            xml = arq.read_bytes()
            prest, m = prestador_do_xml(xml), modelo_do_xml(xml)
        except (ValueError, etree.XMLSyntaxError, HTTPException):
            continue
        servico = {k: m.get(k) for k in ("descricao", "ctribnac", "cnbs", "ctribmun", "cindop", "cclasstrib")}
        do_contask = db.scalar(select(NotaEmitida.id).where(NotaEmitida.chave == n.chave)) is not None if n.chave else False
        return {
            "nota_id": n.id, "numero_nfse": n.numero, "data": _com_fuso(n.data_emissao, BRASILIA), "chave": n.chave,
            "emitida_pelo_contask": do_contask, "prestador": prest,
            "servico": {**servico, **_rotulos(servico)} if servico["ctribnac"] and servico["cnbs"] else None,
            "servico_cadastrado": bool(servico["ctribnac"]) and servico_igual(db, e.id, servico) is not None,
        }
    return None


# ---------------------------------------------------------------------------
# Rascunhos
# ---------------------------------------------------------------------------

class RascunhoIn(BaseModel):
    empresa_id: int
    dados: dict


def _validar_dados(dados: dict) -> dict:
    if len(json.dumps(dados, ensure_ascii=False, default=str)) > 50_000:
        raise HTTPException(422, "Dados grandes demais para um rascunho.")
    return {k: v for k, v in dados.items() if k in EmissaoIn.model_fields and k not in ("empresa_id", "rascunho_id")}


def _rascunho_out(r: NotaRascunho) -> dict:
    d = r.dados or {}
    t = d.get("tomador") or {}
    return {"id": r.id, "empresa_id": r.empresa_id, "dados": d, "tomador_nome": t.get("nome") or None,
            "tomador_documento": t.get("documento") or None, "valor": d.get("valor"), "descricao": d.get("descricao") or "",
            "criado_em": _com_fuso(r.criado_em, timezone.utc), "atualizado_em": _com_fuso(r.atualizado_em, timezone.utc)}


def _rascunho(db: Session, rid: int, esc: int) -> NotaRascunho:
    r = db.get(NotaRascunho, rid)
    if r is None or r.escritorio_id != esc:
        raise HTTPException(404, "Rascunho não encontrado.")
    return r


@router.get("/empresas/{empresa_id}/rascunhos")
def listar_rascunhos(empresa_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    _empresa(db, empresa_id, esc)
    return [_rascunho_out(r) for r in db.scalars(select(NotaRascunho).where(NotaRascunho.empresa_id == empresa_id)
                                                 .order_by(NotaRascunho.atualizado_em.desc()))]


@router.get("/rascunhos/{rascunho_id}")
def obter_rascunho(rascunho_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    return _rascunho_out(_rascunho(db, rascunho_id, esc))


@router.post("/rascunhos", status_code=201)
def criar_rascunho(dados: RascunhoIn, request: Request, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    _empresa(db, dados.empresa_id, esc)
    u = getattr(request.state, "usuario", None)
    r = NotaRascunho(escritorio_id=esc, empresa_id=dados.empresa_id, usuario_id=u.id if u else None,
                     dados=_validar_dados(dados.dados))
    db.add(r)
    db.commit()
    return _rascunho_out(r)


@router.put("/rascunhos/{rascunho_id}")
def salvar_rascunho(rascunho_id: int, dados: RascunhoIn, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    r = _rascunho(db, rascunho_id, esc)
    if dados.empresa_id != r.empresa_id:
        raise HTTPException(422, "O rascunho é de outra empresa.")
    r.dados = _validar_dados(dados.dados)
    db.commit()
    return _rascunho_out(r)


@router.delete("/rascunhos/{rascunho_id}", status_code=204)
def excluir_rascunho(rascunho_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    db.delete(_rascunho(db, rascunho_id, esc))
    db.commit()


# ---------------------------------------------------------------------------
# Notas recorrentes
# ---------------------------------------------------------------------------

class RecorrenteIn(BaseModel):
    empresa_id: int
    nome: str = Field(min_length=1, max_length=120)
    dia: int = Field(ge=1, le=31)
    competencia: str = "atual"
    ativa: bool = True
    dados: dict


@router.get("/variaveis")
def variaveis():
    hoje = datetime.now(BRASILIA).date()
    ex = textos.valores(hoje)
    return [{"nome": k, "descricao": v, "exemplo": ex[k]} for k, v in textos.VARIAVEIS.items()]


def _validar_recorrente(db: Session, d: RecorrenteIn) -> dict:
    from app.emissor.recorrencia import hoje_brasilia
    if d.competencia not in ("atual", "anterior"):
        raise HTTPException(422, "Competência inválida: use o mês da emissão ou o mês anterior.")
    dados = _validar_dados(d.dados)
    for campo in ("descricao", "info_complementar"):
        x = textos.desconhecidas(dados.get(campo))
        if x:
            validas = ", ".join("{" + v + "}" for v in textos.VARIAVEIS)
            raise HTTPException(422, f"Variável desconhecida: {', '.join('{' + v + '}' for v in x)}. Use: {validas}.")
    hoje = hoje_brasilia()
    # Valida como uma emissão de hoje (tomador, valores, serviço da empresa)
    try:
        exemplo = {**dados, "descricao": textos.aplicar(dados.get("descricao"), hoje),
                   "info_complementar": textos.aplicar(dados.get("info_complementar"), hoje) or None}
        _entrada(EmissaoIn(**exemplo, empresa_id=d.empresa_id, competencia=hoje))
    except HTTPException:
        raise
    except ValueError as ex:
        raise HTTPException(422, f"Dados da nota incompletos: {ex}") from None
    serv = db.get(ServicoEmissor, dados.get("servico_id") or 0)
    if dados.get("servico_id") and (serv is None or serv.empresa_id != d.empresa_id):
        raise HTTPException(422, "Escolha um serviço desta empresa.")
    if serv is None and not dados.get("servico"):
        raise HTTPException(422, "Escolha um serviço desta empresa.")
    if not (dados.get("descricao") or "").strip():
        raise HTTPException(422, "Informe a descrição da nota.")
    return dados


def _recorrente_out(db: Session, r: NotaRecorrente) -> dict:
    from app.emissor.recorrencia import competencia_para
    d = r.dados or {}
    t = d.get("tomador") or {}
    ultima = db.get(NotaEmitida, r.ultima_nota_id) if r.ultima_nota_id else None
    prox = r.proxima_em
    return {
        "id": r.id, "empresa_id": r.empresa_id, "nome": r.nome, "dia": r.dia, "competencia": r.competencia,
        "ativa": r.ativa, "dados": d, "proxima_em": prox, "ultima_em": _com_fuso(r.ultima_em, timezone.utc), "ultimo_erro": r.ultimo_erro,
        "tomador_nome": t.get("nome") or None, "tomador_documento": t.get("documento") or None, "valor": d.get("valor"),
        "previa": None if prox is None else {
            "data": prox, "competencia": competencia_para(r, prox), "descricao": textos.aplicar(d.get("descricao"), prox),
        },
        "ultima_nota": None if ultima is None else {"id": ultima.id, "numero_nfse": ultima.numero_nfse,
                                                    "situacao": ultima.situacao, "mensagem": ultima.mensagem},
        "criado_em": _com_fuso(r.criado_em, timezone.utc),
    }


def _recorrente(db: Session, rid: int, esc: int) -> NotaRecorrente:
    r = db.get(NotaRecorrente, rid)
    if r is None or r.escritorio_id != esc:
        raise HTTPException(404, "Recorrência não encontrada.")
    return r


@router.get("/empresas/{empresa_id}/recorrentes")
def listar_recorrentes(empresa_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    _empresa(db, empresa_id, esc)
    return [_recorrente_out(db, r) for r in db.scalars(select(NotaRecorrente).where(NotaRecorrente.empresa_id == empresa_id)
                                                      .order_by(NotaRecorrente.ativa.desc(), NotaRecorrente.nome))]


@router.post("/recorrentes", status_code=201)
def criar_recorrente(d: RecorrenteIn, request: Request, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    from app.core.escritorios import exigir_plano
    from app.emissor.recorrencia import calcular_proxima, hoje_brasilia
    _empresa(db, d.empresa_id, esc)
    from app.core.escritorios import CONTRATE
    exigir_plano(db, esc, f"As notas recorrentes não fazem parte do teste grátis. {CONTRATE}")
    dados = _validar_recorrente(db, d)
    u = getattr(request.state, "usuario", None)
    r = NotaRecorrente(escritorio_id=esc, empresa_id=d.empresa_id, usuario_id=u.id if u else None, nome=d.nome.strip(),
                       dados=dados, dia=d.dia, competencia=d.competencia, ativa=d.ativa)
    r.proxima_em = calcular_proxima(r, hoje_brasilia()) if d.ativa else None
    db.add(r)
    db.commit()
    return _recorrente_out(db, r)


@router.put("/recorrentes/{recorrente_id}")
def editar_recorrente(recorrente_id: int, d: RecorrenteIn, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    from app.emissor.recorrencia import calcular_proxima, hoje_brasilia
    r = _recorrente(db, recorrente_id, esc)
    if d.empresa_id != r.empresa_id:
        raise HTTPException(422, "A recorrência é de outra empresa.")
    r.dados = _validar_recorrente(db, d)
    r.nome, r.dia, r.competencia, r.ativa = d.nome.strip(), d.dia, d.competencia, d.ativa
    r.proxima_em = calcular_proxima(r, hoje_brasilia()) if d.ativa else None
    r.ultimo_erro = None
    db.commit()
    return _recorrente_out(db, r)


@router.delete("/recorrentes/{recorrente_id}", status_code=204)
def excluir_recorrente(recorrente_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    db.delete(_recorrente(db, recorrente_id, esc))
    db.commit()
