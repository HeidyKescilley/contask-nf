"""Empresas, contabilidade, certificados e consulta de CNPJ."""
from __future__ import annotations

import json
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.escopo import escritorio_atual
from app.core import brasilapi
from app.core.certificados import (
    CertificadoInvalido, InfoCertificado, dias_restantes, ler_pfx, remover_arquivo, salvar_certificado,
    situacao_validade, validar_para_uso,
)
from app.core.config import config
from app.core.uso import LimiteTeste, exigir_vaga_empresa
from app.core.db import sessao
from app.fiscal.documentos import cnpj_valido, formatar_cnpj, limpar_cnpj, raiz_cnpj
from app.jobs import acordar_fila
from app.jobs.fila import enfileirar
from app.models import (
    BuscaJob, Certificado, DocumentoDfe, Empresa, EventoNota, Nota, SyncEstado,
)
from app.schemas import BuscaResumo, CertificadoOut, EmpresaCriada, EmpresaOut, EmpresaPatch

router = APIRouter(prefix="/api", tags=["empresas"])


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def _contabilidade(db: Session, escritorio_id: int) -> Empresa | None:
    return db.scalar(select(Empresa).where(Empresa.escritorio_id == escritorio_id, Empresa.is_contabilidade))


def certificado_efetivo(db: Session, e: Empresa) -> Certificado | None:
    if e.modo_certificado == "contabilidade" and not e.is_contabilidade:
        c = _contabilidade(db, e.escritorio_id)
        return db.get(Certificado, c.certificado_id) if c and c.certificado_id else None
    return db.get(Certificado, e.certificado_id) if e.certificado_id else None


def _cert_out(c: Certificado | InfoCertificado | None) -> CertificadoOut | None:
    if c is None:
        return None
    return CertificadoOut(
        id=getattr(c, "id", None), titular_doc=c.titular_doc, titular_nome=c.titular_nome, tipo=c.tipo,
        validade=c.validade, dias_restantes=dias_restantes(c.validade), situacao=situacao_validade(c.validade),
        emissor=getattr(c, "emissor", None), responsavel=getattr(c, "responsavel", None),
    )


def _acesso(e: Empresa, cert: Certificado | None) -> str:
    if cert is None:
        return "sem_certificado"
    if cert.tipo == "e-CNPJ" and raiz_cnpj(cert.titular_doc) == raiz_cnpj(e.cnpj):
        return "proprio" if cert.titular_doc == e.cnpj else "mesma_raiz"
    return "procuracao"


def _serializar(db: Session, e: Empresa) -> EmpresaOut:
    cert = certificado_efetivo(db, e)
    sync = db.get(SyncEstado, e.id) or SyncEstado(empresa_id=e.id, ultimo_nsu=0, situacao="nunca_buscada")
    total = db.scalar(select(func.count()).select_from(Nota).where(Nota.empresa_id == e.id)) or 0
    outras = db.scalar(select(func.count()).select_from(Nota)
                       .where(Nota.empresa_id == e.id, Nota.papel == "outra")) or 0
    com_erro = db.scalar(select(func.count()).select_from(DocumentoDfe)
                         .where(DocumentoDfe.empresa_id == e.id, DocumentoDfe.erro_processamento.is_not(None))) or 0
    sem_nota = db.scalar(
        select(func.count()).select_from(EventoNota)
        .where(EventoNota.empresa_id == e.id,
               ~select(Nota.id).where(Nota.empresa_id == e.id, Nota.chave == EventoNota.chave).exists())) or 0
    pendente = db.scalar(select(func.count()).select_from(BuscaJob)
                         .where(BuscaJob.empresa_id == e.id, BuscaJob.status.in_(["fila", "rodando", "pausado"]))) or 0
    return EmpresaOut(
        id=e.id, cnpj=e.cnpj, razao_social=e.razao_social, nome_fantasia=e.nome_fantasia, apelido=e.apelido,
        uf=e.uf, municipio=e.municipio, situacao_cadastral=e.situacao_cadastral,
        is_contabilidade=e.is_contabilidade, ativa=e.ativa, emite_nfse=e.emite_nfse, modo_certificado=e.modo_certificado,
        acesso=_acesso(e, cert), certificado=_cert_out(cert),
        busca=BuscaResumo(situacao=sync.situacao, ultima_busca_em=sync.ultima_busca_em, ultimo_erro=sync.ultimo_erro,
                          tipo_consulta=sync.tipo_consulta, ultimo_nsu=sync.ultimo_nsu or 0, job_pendente=pendente > 0),
        total_notas=total, pendencias=outras + com_erro + sem_nota, criado_em=e.criado_em,
    )


def _obter(db: Session, empresa_id: int, escritorio_id: int) -> Empresa:
    e = db.get(Empresa, empresa_id)
    if e is None or e.escritorio_id != escritorio_id:
        raise HTTPException(404, "Empresa não encontrada.")
    return e


def _cnpj_ou_erro(cnpj: str) -> str:
    c = limpar_cnpj(cnpj)
    if not cnpj_valido(c):
        raise HTTPException(422, "CNPJ inválido: confira os dígitos verificadores.")
    return c


async def _ler_certificado(arquivo: UploadFile | None, senha: str | None) -> tuple[bytes, str, InfoCertificado]:
    if arquivo is None:
        raise HTTPException(422, "Selecione o arquivo do certificado (.pfx ou .p12).")
    if not senha:
        raise HTTPException(422, "Informe a senha do certificado.")
    pfx = await arquivo.read()
    try:
        info, _, _ = ler_pfx(pfx, senha)
        validar_para_uso(info)
    except CertificadoInvalido as ex:
        raise HTTPException(422, str(ex)) from None
    return pfx, senha, info


def _aviso_raiz(info: InfoCertificado, cnpj: str) -> str | None:
    if info.tipo == "e-CNPJ" and raiz_cnpj(info.titular_doc) != raiz_cnpj(cnpj):
        return (f"O certificado é de {info.titular_nome} ({formatar_cnpj(info.titular_doc)}), de outra raiz de CNPJ. "
                "A consulta só funciona se esta empresa tiver dado procuração a esse titular.")
    return None


def _aviso_situacao(situacao: str | None) -> str | None:
    if situacao and situacao != "ATIVA":
        return f"A situação cadastral na Receita é {situacao}."
    return None


def _agendar_busca_inicial(db: Session, e: Empresa) -> None:
    db.flush()
    if config().teste and e.is_contabilidade:
        return  # no teste, a contabilidade entra só pelo certificado
    enfileirar(db, e.id, "inicial" if not db.get(SyncEstado, e.id) or not db.get(SyncEstado, e.id).ultimo_nsu else "incremental")


def _remover_cert_orfao(db: Session, cert_id: int | None) -> None:
    if not cert_id:
        return
    em_uso = db.scalar(select(func.count()).select_from(Empresa).where(Empresa.certificado_id == cert_id))
    if not em_uso:
        c = db.get(Certificado, cert_id)
        if c:
            remover_arquivo(c)
            db.delete(c)


def _dados_brasilapi(valor: str | None) -> dict | None:
    if not valor:
        return None
    try:
        d = json.loads(valor)
        return d if isinstance(d, dict) else None
    except ValueError:
        return None


def _texto(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


# ---------------------------------------------------------------------------
# CNPJ e certificados
# ---------------------------------------------------------------------------

@router.get("/cnpj/{cnpj}")
def consultar_cnpj(cnpj: str, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    c = _cnpj_ou_erro(cnpj)
    ja = db.scalar(select(Empresa).where(Empresa.escritorio_id == esc, Empresa.cnpj == c))
    try:
        dados = brasilapi.consultar(c)
    except brasilapi.BrasilApiErro as ex:
        return {"cnpj": c, "encontrado": False, "erro": str(ex), "nao_encontrado": ex.nao_encontrado,
                "ja_cadastrada": ja.id if ja else None}
    return {**dados, "encontrado": True, "erro": None, "ja_cadastrada": ja.id if ja else None,
            "aviso": _aviso_situacao(dados["situacao_cadastral"])}


@router.post("/certificados/validar", response_model=CertificadoOut)
async def validar_certificado(arquivo: UploadFile | None = File(None), senha: str = Form("")):
    """Lê os metadados sem gravar nada."""
    if arquivo is None:
        raise HTTPException(422, "Selecione o arquivo do certificado (.pfx ou .p12).")
    try:
        info, _, _ = ler_pfx(await arquivo.read(), senha)
    except CertificadoInvalido as ex:
        raise HTTPException(422, str(ex)) from None
    return _cert_out(info)


# ---------------------------------------------------------------------------
# Contabilidade
# ---------------------------------------------------------------------------

@router.get("/contabilidade", response_model=EmpresaOut | None)
def obter_contabilidade(db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    c = _contabilidade(db, esc)
    return _serializar(db, c) if c else None


@router.post("/contabilidade", response_model=EmpresaCriada)
async def salvar_contabilidade(
    cnpj: str = Form(...), razao_social: str = Form(...), nome_fantasia: str | None = Form(None),
    apelido: str | None = Form(None), uf: str | None = Form(None), municipio: str | None = Form(None),
    situacao_cadastral: str | None = Form(None), dados_brasilapi: str | None = Form(None),
    arquivo: UploadFile | None = File(None), senha: str | None = Form(None), db: Session = Depends(sessao),
    esc: int = Depends(escritorio_atual),
):
    c = _cnpj_ou_erro(cnpj)
    if not razao_social.strip():
        raise HTTPException(422, "Informe a razão social.")
    atual = _contabilidade(db, esc)
    if atual and atual.cnpj != c:
        raise HTTPException(409, f"A contabilidade já é {atual.razao_social} ({formatar_cnpj(atual.cnpj)}).")
    pfx, senha_ok, info = await _ler_certificado(arquivo, senha)
    if info.tipo == "e-CNPJ" and raiz_cnpj(info.titular_doc) != raiz_cnpj(c):
        raise HTTPException(422, f"O certificado é de {info.titular_nome} ({formatar_cnpj(info.titular_doc)}), "
                                 f"não da contabilidade informada ({formatar_cnpj(c)}).")

    e = atual or db.scalar(select(Empresa).where(Empresa.escritorio_id == esc, Empresa.cnpj == c))
    if e is None:
        e = Empresa(cnpj=c, escritorio_id=esc)
    antigo_cert = e.certificado_id
    e.razao_social, e.nome_fantasia, e.apelido = razao_social.strip(), _texto(nome_fantasia), _texto(apelido)
    e.uf, e.municipio, e.situacao_cadastral = _texto(uf), _texto(municipio), _texto(situacao_cadastral)
    e.dados_brasilapi = _dados_brasilapi(dados_brasilapi) or e.dados_brasilapi
    e.is_contabilidade, e.modo_certificado, e.ativa = True, "proprio", True
    with db.no_autoflush:
        cert = salvar_certificado(db, pfx, senha_ok, info, escritorio_id=esc)
    e.certificado_id = cert.id
    db.add(e)
    db.flush()
    if antigo_cert != cert.id:
        _remover_cert_orfao(db, antigo_cert)
    _agendar_busca_inicial(db, e)
    db.commit()
    acordar_fila()
    avisos = [a for a in [_aviso_situacao(e.situacao_cadastral)] if a]
    if info.dias_restantes < 30:
        avisos.append(f"O certificado vence em {info.validade:%d/%m/%Y} ({info.dias_restantes} dias).")
    return EmpresaCriada(empresa=_serializar(db, e), avisos=avisos)


# ---------------------------------------------------------------------------
# Empresas
# ---------------------------------------------------------------------------

@router.get("/empresas", response_model=list[EmpresaOut])
def listar_empresas(q: str | None = None, filtro: str | None = Query(None, pattern="^(procuracao_pendente|certificado|pendencias|inativas)$"),
                    db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    stmt = select(Empresa).where(Empresa.escritorio_id == esc).order_by(Empresa.is_contabilidade.desc(), Empresa.razao_social)
    if q and q.strip():
        termo = f"%{q.strip()}%"
        doc = limpar_cnpj(q)
        conds = [Empresa.razao_social.ilike(termo), Empresa.nome_fantasia.ilike(termo), Empresa.apelido.ilike(termo)]
        if doc:
            conds.append(Empresa.cnpj.like(f"%{doc}%"))
        stmt = stmt.where(or_(*conds))
    itens = [_serializar(db, e) for e in db.scalars(stmt)]
    if filtro == "procuracao_pendente":
        itens = [i for i in itens if i.busca.situacao == "sem_procuracao"]
    elif filtro == "certificado":
        itens = [i for i in itens if i.certificado is None or i.certificado.situacao in ("vencido", "vence_7", "vence_15", "vence_30")
                 or i.busca.situacao == "erro_certificado"]
    elif filtro == "pendencias":
        itens = [i for i in itens if i.pendencias > 0]
    elif filtro == "inativas":
        itens = [i for i in itens if not i.ativa]
    return itens


@router.post("/empresas", response_model=EmpresaCriada, status_code=201)
async def criar_empresa(
    cnpj: str = Form(...), razao_social: str = Form(...), nome_fantasia: str | None = Form(None),
    apelido: str | None = Form(None), uf: str | None = Form(None), municipio: str | None = Form(None),
    situacao_cadastral: str | None = Form(None), dados_brasilapi: str | None = Form(None),
    modo_certificado: str = Form("contabilidade"), arquivo: UploadFile | None = File(None),
    senha: str | None = Form(None), emite_nfse: bool = Form(False), db: Session = Depends(sessao),
    esc: int = Depends(escritorio_atual),
):
    c = _cnpj_ou_erro(cnpj)
    if not razao_social.strip():
        raise HTTPException(422, "Informe a razão social.")
    if db.scalar(select(Empresa).where(Empresa.escritorio_id == esc, Empresa.cnpj == c)):
        raise HTTPException(409, f"O CNPJ {formatar_cnpj(c)} já está cadastrado.")
    try:
        exigir_vaga_empresa(db, esc)
    except LimiteTeste as erro:
        raise HTTPException(403, str(erro)) from None
    avisos: list[str] = []
    e = Empresa(cnpj=c, razao_social=razao_social.strip(), nome_fantasia=_texto(nome_fantasia),
                apelido=_texto(apelido), uf=_texto(uf), municipio=_texto(municipio),
                situacao_cadastral=_texto(situacao_cadastral), dados_brasilapi=_dados_brasilapi(dados_brasilapi),
                is_contabilidade=False, ativa=True, emite_nfse=emite_nfse, escritorio_id=esc)
    if modo_certificado == "contabilidade":
        contab = _contabilidade(db, esc)
        if contab is None or contab.certificado_id is None:
            raise HTTPException(409, "Cadastre primeiro a contabilidade e o certificado dela.")
        cc = db.get(Certificado, contab.certificado_id)
        if situacao_validade(cc.validade) == "vencido":
            avisos.append("O certificado da contabilidade está vencido: a busca só roda depois da renovação.")
        e.modo_certificado = "contabilidade"
    elif modo_certificado == "proprio":
        pfx, senha_ok, info = await _ler_certificado(arquivo, senha)
        e.modo_certificado = "proprio"
        e.certificado_id = salvar_certificado(db, pfx, senha_ok, info, escritorio_id=esc).id
        if aviso := _aviso_raiz(info, c):
            avisos.append(aviso)
    else:
        raise HTTPException(422, "Modo de certificado inválido.")
    if aviso := _aviso_situacao(e.situacao_cadastral):
        avisos.append(aviso)
    if emite_nfse and modo_certificado != "proprio":
        avisos.append("Para emitir NFS-e, envie o certificado A1 da própria empresa: a procuração não serve para emitir.")
    db.add(e)
    db.flush()
    if emite_nfse:
        from app.api.emissor import config_prestador
        config_prestador(db, e)
    _agendar_busca_inicial(db, e)
    db.commit()
    acordar_fila()
    return EmpresaCriada(empresa=_serializar(db, e), avisos=avisos)


@router.get("/empresas/{empresa_id}", response_model=EmpresaOut)
def obter_empresa(empresa_id: int, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    return _serializar(db, _obter(db, empresa_id, esc))


@router.patch("/empresas/{empresa_id}", response_model=EmpresaOut)
def editar_empresa(empresa_id: int, dados: EmpresaPatch, db: Session = Depends(sessao), esc: int = Depends(escritorio_atual)):
    e = _obter(db, empresa_id, esc)
    campos = dados.model_dump(exclude_unset=True)
    if "razao_social" in campos and not (campos["razao_social"] or "").strip():
        raise HTTPException(422, "Informe a razão social.")
    if campos.get("ativa") is False and e.is_contabilidade:
        raise HTTPException(409, "A contabilidade não pode ser desativada.")
    for k, v in campos.items():
        if isinstance(v, str):
            v = v.strip() if k == "razao_social" else _texto(v)
        setattr(e, k, v)
    if campos.get("emite_nfse"):
        from app.api.emissor import config_prestador
        config_prestador(db, e)
    db.commit()
    return _serializar(db, e)


@router.put("/empresas/{empresa_id}/certificado", response_model=EmpresaCriada)
async def trocar_certificado(
    empresa_id: int, modo_certificado: str = Form(...), arquivo: UploadFile | None = File(None),
    senha: str | None = Form(None), db: Session = Depends(sessao), esc: int = Depends(escritorio_atual),
):
    e = _obter(db, empresa_id, esc)
    if e.is_contabilidade:
        raise HTTPException(409, "Para trocar o certificado da contabilidade, use o assistente da contabilidade.")
    avisos: list[str] = []
    antigo = e.certificado_id
    if modo_certificado == "contabilidade":
        if _contabilidade(db, esc) is None:
            raise HTTPException(409, "Cadastre primeiro a contabilidade e o certificado dela.")
        e.modo_certificado, e.certificado_id = "contabilidade", None
    elif modo_certificado == "proprio":
        pfx, senha_ok, info = await _ler_certificado(arquivo, senha)
        e.modo_certificado = "proprio"
        e.certificado_id = salvar_certificado(db, pfx, senha_ok, info, escritorio_id=esc).id
        if aviso := _aviso_raiz(info, e.cnpj):
            avisos.append(aviso)
    else:
        raise HTTPException(422, "Modo de certificado inválido.")
    db.flush()
    if antigo != e.certificado_id:
        _remover_cert_orfao(db, antigo)
    sync = db.get(SyncEstado, e.id)
    if sync and sync.situacao in ("erro_certificado", "sem_procuracao"):
        sync.situacao, sync.ultimo_erro = "nunca_buscada" if not sync.ultimo_nsu else "em_dia", None
    if e.ativa:  # certificado novo: tenta buscar de novo
        _agendar_busca_inicial(db, e)
    db.commit()
    acordar_fila()
    return EmpresaCriada(empresa=_serializar(db, e), avisos=avisos)


@router.delete("/empresas/{empresa_id}", status_code=204)
def excluir_empresa(empresa_id: int, confirmacao: str = Query(...), db: Session = Depends(sessao),
                    esc: int = Depends(escritorio_atual)):
    e = _obter(db, empresa_id, esc)
    if limpar_cnpj(confirmacao) != e.cnpj:
        raise HTTPException(422, "Para excluir, digite o CNPJ da empresa exatamente.")
    if e.is_contabilidade:
        raise HTTPException(409, "A contabilidade não pode ser excluída.")
    if db.scalar(select(BuscaJob).where(BuscaJob.empresa_id == e.id, BuscaJob.status == "rodando")):
        raise HTTPException(409, "Há uma busca em andamento para esta empresa. Pause-a antes de excluir.")
    cert_id, cnpj = e.certificado_id, e.cnpj
    db.delete(e)
    db.flush()
    _remover_cert_orfao(db, cert_id)
    db.commit()
    pasta = config().dados_dir / "empresas" / cnpj
    if pasta.is_dir():
        shutil.rmtree(pasta, ignore_errors=True)
