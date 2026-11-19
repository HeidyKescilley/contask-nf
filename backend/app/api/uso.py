"""Coleta do uso da plataforma (para o painel de Monitoramento do administrador).

Tudo fica no próprio servidor. O navegador manda eventos curtos (página, tempo ativo, clique, rolagem,
erro, ação) e a gravação da sessão em rrweb com todo texto e campo mascarados: nada de CNPJ, nome ou
valor sai da tela. As rotas exigem login (middleware de core/seguranca.py); o escritório e o usuário vêm
da sessão, nunca do corpo.
"""
from __future__ import annotations

import gzip
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import config
from app.core.db import sessao
from app.models import Gravacao, PedidoSuporte, PesquisaResposta, UsoEvento, Usuario

router = APIRouter(prefix="/api/uso", tags=["uso"])

TIPOS_CLIENTE = {"pagina", "tempo", "clique", "rolagem", "erro", "acao"}
SESSAO = r"^[A-Za-z0-9_-]{8,40}$"
MAX_GRAVACAO = 8 * 1024 * 1024  # bytes comprimidos por sessão
DIAS_GRAVACAO = 30
DIAS_EVENTOS = 400
ASSUNTOS = {
    "buscas": "Busca de notas", "emissao": "Emissão de NFS-e", "certificado": "Certificado ou procuração",
    "exportacao": "Exportação e relatórios", "empresas": "Cadastro de empresas", "cobranca": "Plano e cobrança",
    "sugestao": "Sugestão", "outro": "Outro assunto",
}


def _usuario(request: Request) -> Usuario:
    u = getattr(request.state, "usuario", None)
    if u is None:
        raise HTTPException(401, "Entre com seu e-mail e senha.")
    return u


def rota_normalizada(caminho: str) -> str:
    """/empresas/123 -> /empresas/:id; sem query string; no máximo 120 caracteres."""
    c = (caminho or "/").split("?")[0].split("#")[0]
    c = re.sub(r"/\d+(?=/|$)", "/:id", c)
    return c[:120] or "/"


def registrar(db: Session, u: Usuario | None, tipo: str, nome: str, dados: dict | None = None, sessao_id: str = "servidor") -> None:
    """Evento gravado pelo próprio servidor (login, busca, exportação, emissão...). Não faz commit."""
    if u is None:
        return
    db.add(UsoEvento(escritorio_id=u.escritorio_id, usuario_id=u.id, sessao=sessao_id, tipo=tipo, nome=nome[:120], dados=dados))


# Ações gravadas pelo servidor quando a rota responde sem erro (middleware de core/seguranca.py)
ACOES = [
    ("POST", re.compile(r"^/api/empresas/\d+/buscas$"), "busca"),
    ("POST", re.compile(r"^/api/empresas/\d+/exportacoes$"), "exportacao"),
    ("GET", re.compile(r"^/api/exportacoes/\d+/arquivo$"), "exportacao_baixada"),
    ("POST", re.compile(r"^/api/emissor/notas$"), "emissao"),
    ("POST", re.compile(r"^/api/emissor/notas/\d+/reenviar$"), "emissao"),
    ("POST", re.compile(r"^/api/emissor/notas/\d+/cancelar$"), "cancelamento"),
    ("POST", re.compile(r"^/api/emissor/recorrentes$"), "recorrente"),
    ("POST", re.compile(r"^/api/empresas$"), "empresa_cadastrada"),
    ("POST", re.compile(r"^/api/empresas/importar"), "empresa_cadastrada"),
    ("POST", re.compile(r"^/api/contabilidade$"), "contabilidade_cadastrada"),
    ("GET", re.compile(r"^/api/(emissor/)?notas/\d+/(pdf|danfse)$"), "danfse"),
    ("GET", re.compile(r"^/api/(emissor/)?notas/\d+/xml$"), "xml"),
]


def acao_da_rota(metodo: str, caminho: str) -> str | None:
    for m, rx, nome in ACOES:
        if m == metodo and rx.match(caminho):
            return nome
    return None


def gravar_acao(u: Usuario, nome: str) -> None:
    from app.core.db import nova_sessao
    try:
        with nova_sessao() as db:
            registrar(db, u, "acao", nome)
            db.commit()
    except Exception:  # noqa: BLE001 - o monitoramento nunca derruba a requisição
        pass


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------

class EventoIn(BaseModel):
    tipo: str
    nome: str = Field(max_length=200)
    momento: datetime | None = None
    dados: dict | None = None


class LoteIn(BaseModel):
    sessao: str = Field(pattern=SESSAO)
    eventos: list[EventoIn] = Field(max_length=200)


def _dados_limpos(tipo: str, d: dict | None) -> dict | None:
    """Só os campos esperados de cada tipo, com tamanho limitado (o resto é descartado)."""
    if not d:
        return None
    num = lambda v, lo, hi: max(lo, min(hi, float(v))) if isinstance(v, (int, float)) else None  # noqa: E731
    txt = lambda v, n: str(v)[:n] if v is not None else None  # noqa: E731
    if tipo == "tempo":
        return {"s": num(d.get("s"), 0, 600)}
    if tipo == "clique":
        return {"x": num(d.get("x"), 0, 1), "y": num(d.get("y"), 0, 100000), "w": num(d.get("w"), 0, 10000),
                "h": num(d.get("h"), 0, 100000), "alvo": txt(d.get("alvo"), 80), "morto": bool(d.get("morto"))}
    if tipo == "rolagem":
        return {"p": num(d.get("p"), 0, 100)}
    if tipo == "erro":
        return {"msg": txt(d.get("msg"), 300), "rota": txt(d.get("rota"), 120), "status": num(d.get("status"), 0, 999)}
    if tipo == "acao":
        return {k: txt(v, 60) for k, v in list(d.items())[:5]}
    return None


@router.post("/eventos", status_code=204)
def receber_eventos(lote: LoteIn, request: Request, db: Session = Depends(sessao)):
    u = _usuario(request)
    agora = datetime.now(timezone.utc)
    for ev in lote.eventos:
        if ev.tipo not in TIPOS_CLIENTE:
            continue
        momento = ev.momento if ev.momento and abs((agora - ev.momento).total_seconds()) < 3600 else agora
        nome = rota_normalizada(ev.nome) if ev.tipo in ("pagina", "tempo", "clique", "rolagem") else ev.nome[:120]
        db.add(UsoEvento(escritorio_id=u.escritorio_id, usuario_id=u.id, sessao=lote.sessao, momento=momento,
                         tipo=ev.tipo, nome=nome, dados=_dados_limpos(ev.tipo, ev.dados)))
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Gravação da sessão
# ---------------------------------------------------------------------------

class TrechoIn(BaseModel):
    sessao: str = Field(pattern=SESSAO)
    pagina: str = Field("", max_length=200)
    eventos: list[dict] = Field(max_length=5000)


@router.post("/gravacao", status_code=204)
def receber_gravacao(t: TrechoIn, request: Request, db: Session = Depends(sessao)):
    u = _usuario(request)
    if u.admin_sistema:  # o suporte não é gravado
        return Response(status_code=204)
    g = db.scalar(select(Gravacao).where(Gravacao.sessao == t.sessao))
    rota = rota_normalizada(t.pagina)
    if g is None:
        rel = f"gravacoes/{datetime.now(timezone.utc):%Y%m}/{t.sessao}.jsonl.gz"
        g = Gravacao(escritorio_id=u.escritorio_id, usuario_id=u.id, sessao=t.sessao, arquivo=rel,
                     pagina_inicial=rota, paginas=[rota], tamanho=0)
        db.add(g)
    elif g.usuario_id != u.id:
        raise HTTPException(409, "Sessão de outra pessoa.")
    if g.tamanho >= MAX_GRAVACAO or not t.eventos:
        return Response(status_code=204)
    arq = config().dados_dir / g.arquivo
    arq.parent.mkdir(parents=True, exist_ok=True)
    bloco = gzip.compress((json.dumps(t.eventos, separators=(",", ":")) + "\n").encode())
    with open(arq, "ab") as f:  # membros gzip concatenados: gzip.open lê tudo em sequência
        f.write(bloco)
    g.tamanho += len(bloco)
    g.atualizado_em = datetime.now(timezone.utc)
    if rota and (not g.paginas or g.paginas[-1] != rota):
        g.paginas = [*(g.paginas or []), rota][-200:]
    db.commit()
    return Response(status_code=204)


def ler_gravacao(g: Gravacao) -> list[dict]:
    arq = config().dados_dir / g.arquivo
    if not arq.is_file():
        return []
    eventos: list[dict] = []
    with gzip.open(arq, "rt", encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                eventos.extend(json.loads(linha))
    return eventos


def limpar_antigos(db: Session) -> int:
    """Apaga gravações com mais de 30 dias e eventos com mais de 400. Roda junto das buscas periódicas."""
    agora = datetime.now(timezone.utc)
    n = 0
    for g in db.scalars(select(Gravacao).where(Gravacao.iniciado_em < agora - timedelta(days=DIAS_GRAVACAO))):
        (config().dados_dir / g.arquivo).unlink(missing_ok=True)
        db.delete(g)
        n += 1
    db.query(UsoEvento).filter(UsoEvento.momento < agora - timedelta(days=DIAS_EVENTOS)).delete()
    db.commit()
    return n


# ---------------------------------------------------------------------------
# Pesquisa no app
# ---------------------------------------------------------------------------

def _dias_de_acesso(db: Session, u: Usuario) -> int:
    return int(db.scalar(select(func.count(func.distinct(func.date(UsoEvento.momento))))
                         .where(UsoEvento.usuario_id == u.id, UsoEvento.tipo == "pagina")) or 0)


@router.get("/pesquisa")
def pesquisa_pendente(request: Request, db: Session = Depends(sessao)):
    """Mostra a pesquisa depois de 7 dias de conta e 3 dias de uso; repete a cada 90 dias (adiada: 14)."""
    u = _usuario(request)
    if u.admin_sistema:
        return {"mostrar": False}
    agora = datetime.now(timezone.utc)
    criado = u.criado_em if u.criado_em.tzinfo else u.criado_em.replace(tzinfo=timezone.utc)
    if agora - criado < timedelta(days=7) or _dias_de_acesso(db, u) < 3:
        return {"mostrar": False}
    ultima = db.scalar(select(PesquisaResposta).where(PesquisaResposta.usuario_id == u.id)
                       .order_by(PesquisaResposta.momento.desc()))
    if ultima is not None:
        quando = ultima.momento if ultima.momento.tzinfo else ultima.momento.replace(tzinfo=timezone.utc)
        if agora - quando < timedelta(days=14 if ultima.adiada else 90):
            return {"mostrar": False}
    return {"mostrar": True}


class PesquisaIn(BaseModel):
    adiada: bool = False
    decepcao: Literal["muito", "pouco", "nada"] | None = None
    horas: int | None = Field(None, ge=0, le=744)
    nps: int | None = Field(None, ge=0, le=10)
    comentario: str | None = Field(None, max_length=2000)


@router.post("/pesquisa", status_code=201)
def responder_pesquisa(d: PesquisaIn, request: Request, db: Session = Depends(sessao)):
    u = _usuario(request)
    if not d.adiada and d.decepcao is None and d.nps is None:
        raise HTTPException(422, "Responda pelo menos uma pergunta.")
    db.add(PesquisaResposta(escritorio_id=u.escritorio_id, usuario_id=u.id, adiada=d.adiada, decepcao=d.decepcao,
                            horas=d.horas, nps=d.nps, comentario=(d.comentario or "").strip() or None))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Suporte
# ---------------------------------------------------------------------------

class SuporteIn(BaseModel):
    assunto: str
    mensagem: str = Field(min_length=5, max_length=4000)
    pagina: str = Field("", max_length=200)


@router.get("/suporte/assuntos")
def assuntos():
    return [{"valor": k, "rotulo": v} for k, v in ASSUNTOS.items()]


@router.post("/suporte", status_code=201)
def pedir_suporte(d: SuporteIn, request: Request, db: Session = Depends(sessao)):
    u = _usuario(request)
    if d.assunto not in ASSUNTOS:
        raise HTTPException(422, "Escolha o assunto.")
    p = PedidoSuporte(escritorio_id=u.escritorio_id, usuario_id=u.id, assunto=d.assunto,
                      mensagem=d.mensagem.strip(), pagina=rota_normalizada(d.pagina) if d.pagina else None)
    db.add(p)
    db.commit()
    return {"id": p.id}
