"""Métricas do painel de Monitoramento (só o administrador do sistema vê).

Fontes:
- tabelas que já existiam (usuário, empresa, busca, exportação, nota emitida, certificado): servem para a
  ativação e valem desde o primeiro cliente;
- uso_evento (páginas, tempo ativo, cliques, rolagem, erros e ações), que só existe a partir da
  implantação do monitoramento (19/11/2026).
O usuário administrador do sistema (suporte do Contask) fica fora de todas as contas.
Datas e horas em Brasília.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BuscaJob, Certificado, Empresa, Escritorio, Exportacao, NotaEmitida, PedidoSuporte, PesquisaResposta,
    UsoEvento, Usuario,
)

BRASILIA = timezone(timedelta(hours=-3))
META_ATIVACAO, META_RETORNO, META_DECEPCAO = 80, 70, 40

# id, rótulo, rotas (prefixo exato ou com /...), ações do servidor
FUNCOES = [
    ("dashboard", "Dashboard", ["/dashboard"], []),
    ("notas", "Notas tomadas e prestadas", ["/tomados", "/prestados"], ["danfse", "xml"]),
    ("busca", "Busca de notas", [], ["busca"]),
    ("exportacao", "Exportação e relatórios", ["/exportacoes"], ["exportacao", "exportacao_baixada"]),
    ("emissor", "Emissor de notas", ["/emissor", "/emissor/emitir", "/emissor/empresas", "/emissor/tomadores"],
     ["emissao", "cancelamento"]),
    ("recorrentes", "Notas recorrentes", ["/emissor/recorrentes"], ["recorrente"]),
    ("empresas", "Empresas", ["/empresas", "/contabilidade", "/minha-empresa"], ["empresa_cadastrada", "contabilidade_cadastrada"]),
]


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _br(dt: datetime) -> datetime:
    return _utc(dt).astimezone(BRASILIA)


def funcao_da_rota(rota: str) -> str | None:
    # recorrentes antes do emissor (mais específico)
    for fid, _, rotas, _ in sorted(FUNCOES, key=lambda f: -max((len(r) for r in f[2]), default=0)):
        for r in rotas:
            if rota == r or rota.startswith(r + "/"):
                return fid
    return None


def funcao_da_acao(acao: str) -> str | None:
    for fid, _, _, acoes in FUNCOES:
        if acao in acoes:
            return fid
    return None


def _horas(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return max(0.0, (_utc(b) - _utc(a)).total_seconds() / 3600)


def _mediana(v: list[float]) -> float | None:
    return round(statistics.median(v), 1) if v else None


def _pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


class Base:
    """Carrega uma vez o que as seções usam."""

    def __init__(self, db: Session, dias: int = 30, agora: datetime | None = None):
        self.db = db
        self.agora = agora or datetime.now(timezone.utc)
        self.dias = dias
        self.inicio = self.agora - timedelta(days=dias)
        self.usuarios = [u for u in db.scalars(select(Usuario).where(Usuario.admin_sistema.is_(False)))]
        self.ids = {u.id for u in self.usuarios}
        esc_ids = {u.escritorio_id for u in self.usuarios}
        self.escritorios = {e.id: e for e in db.scalars(select(Escritorio).where(Escritorio.id.in_(esc_ids or {0})))}
        self.eventos = [e for e in db.scalars(select(UsoEvento).where(UsoEvento.usuario_id.in_(self.ids or {0}))
                                               .order_by(UsoEvento.momento))]
        self.periodo = [e for e in self.eventos if _utc(e.momento) >= self.inicio]

    def usuario(self, uid: int) -> Usuario | None:
        return next((u for u in self.usuarios if u.id == uid), None)

    def nome_esc(self, eid: int) -> str:
        e = self.escritorios.get(eid)
        return e.nome if e else f"Escritório {eid}"


# ---------------------------------------------------------------------------
# Ativação
# ---------------------------------------------------------------------------

def _primeiros_por_escritorio(db: Session) -> dict[int, dict]:
    """Primeira busca, emissão, exportação, empresa e certificado de cada escritório."""
    def por_empresa(col, *where):
        modelo = col.class_
        q = select(Empresa.escritorio_id, func.min(col)).join(Empresa, Empresa.id == modelo.empresa_id)
        for w in where:
            q = q.where(w)
        return {eid: _utc(m) for eid, m in db.execute(q.group_by(Empresa.escritorio_id))}

    busca = por_empresa(BuscaJob.criado_em)
    busca_ok = por_empresa(BuscaJob.finalizado_em, BuscaJob.status == "concluido")
    exportacao = por_empresa(Exportacao.criado_em)
    emissao = {eid: _utc(m) for eid, m in db.execute(
        select(NotaEmitida.escritorio_id, func.min(NotaEmitida.criado_em)).group_by(NotaEmitida.escritorio_id))}
    empresa = {eid: _utc(m) for eid, m in db.execute(
        select(Empresa.escritorio_id, func.min(Empresa.criado_em)).where(Empresa.is_contabilidade.is_(False))
        .group_by(Empresa.escritorio_id))}
    contab = {eid: _utc(m) for eid, m in db.execute(
        select(Empresa.escritorio_id, func.min(Empresa.criado_em)).where(Empresa.is_contabilidade.is_(True))
        .group_by(Empresa.escritorio_id))}
    cert = {eid: _utc(m) for eid, m in db.execute(
        select(Certificado.escritorio_id, func.min(Certificado.criado_em)).group_by(Certificado.escritorio_id))}
    saida: dict[int, dict] = defaultdict(dict)
    for nome, d in (("busca", busca), ("busca_ok", busca_ok), ("exportacao", exportacao), ("emissao", emissao),
                    ("empresa", empresa), ("contabilidade", contab), ("certificado", cert)):
        for eid, m in d.items():
            saida[eid][nome] = m
    return saida


ETAPAS = [
    ("conta", "Conta criada"),
    ("login", "Primeiro acesso"),
    ("certificado", "Certificado cadastrado"),
    ("empresa", "Empresa cadastrada"),
    ("busca_ok", "Primeira busca concluída"),
    ("valor", "Exportou ou emitiu nota"),
]


def ativacao(b: Base) -> dict:
    db = b.db
    primeiros = _primeiros_por_escritorio(db)
    primeiro_evento = {}
    for e in b.eventos:
        primeiro_evento.setdefault(e.usuario_id, _utc(e.momento))

    def entrou(u: Usuario) -> datetime | None:
        return primeiro_evento.get(u.id) or (_utc(u.ultimo_acesso_em) if u.ultimo_acesso_em else None)

    # % de usuários que entraram e começaram a usar em 7 dias (só quem tem 7 dias de conta)
    elegiveis, ativados = 0, 0
    for u in b.usuarios:
        criado = _utc(u.criado_em)
        if b.agora - criado < timedelta(days=7):
            continue
        elegiveis += 1
        p = primeiros.get(u.escritorio_id, {})
        uso = [m for m in (p.get("busca"), p.get("emissao"), p.get("exportacao")) if m]
        if entrou(u) and uso and min(uso) <= criado + timedelta(days=7):
            ativados += 1

    escritorios = []
    tempos = {"busca": [], "emissao": [], "exportacao": []}
    funil = Counter()
    for eid, esc in b.escritorios.items():
        usuarios = [u for u in b.usuarios if u.escritorio_id == eid]
        criado = min((_utc(u.criado_em) for u in usuarios), default=_utc(esc.criado_em))
        p = primeiros.get(eid, {})
        empresas = list(db.scalars(select(Empresa).where(Empresa.escritorio_id == eid, Empresa.is_contabilidade.is_(False),
                                                         Empresa.ativa.is_(True))))
        conectadas = {i for (i,) in db.execute(select(BuscaJob.empresa_id).where(
            BuscaJob.empresa_id.in_([e.id for e in empresas] or [0]), BuscaJob.status == "concluido").distinct())}
        h = {k: _horas(criado, p.get(k)) for k in tempos}
        for k, v in h.items():
            if v is not None:
                tempos[k].append(v)
        logou = any(entrou(u) for u in usuarios)
        etapas = {"conta": True, "login": logou, "certificado": bool(p.get("certificado")),
                  "empresa": bool(p.get("empresa") or (esc.tipo == "empresa" and p.get("contabilidade"))),
                  "busca_ok": bool(p.get("busca_ok")), "valor": bool(p.get("exportacao") or p.get("emissao"))}
        parou = next((rot for k, rot in ETAPAS if not etapas[k]), None)
        for k, _ in ETAPAS:
            if etapas[k]:
                funil[k] += 1
            else:
                break
        escritorios.append({
            "id": eid, "nome": esc.nome, "tipo": esc.tipo, "situacao": esc.situacao, "criado_em": criado,
            "usuarios": len(usuarios), "empresas": len(empresas), "conectadas": len(conectadas),
            "pct_conectadas": _pct(len(conectadas), len(empresas)),
            "horas_ate_busca": h["busca"], "horas_ate_emissao": h["emissao"], "horas_ate_exportacao": h["exportacao"],
            "parou_em": parou,
        })
    escritorios.sort(key=lambda x: x["criado_em"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    total = len(b.escritorios)
    sem_uso = [u for u in b.usuarios if not entrou(u)]
    return {
        "pct_ativados_7d": _pct(ativados, elegiveis), "meta_ativacao": META_ATIVACAO, "elegiveis_7d": elegiveis,
        "mediana_horas": {k: _mediana(v) for k, v in tempos.items()},
        "funil": [{"etapa": k, "rotulo": rot, "escritorios": funil[k], "pct": _pct(funil[k], total)} for k, rot in ETAPAS],
        "usuarios_sem_acesso": len(sem_uso), "usuarios": len(b.usuarios),
        "escritorios": escritorios,
    }


# ---------------------------------------------------------------------------
# Uso das funcionalidades
# ---------------------------------------------------------------------------

def _uso_por_usuario(eventos: list[UsoEvento]) -> dict[int, Counter]:
    uso: dict[int, Counter] = defaultdict(Counter)
    for e in eventos:
        f = funcao_da_rota(e.nome) if e.tipo == "pagina" else funcao_da_acao(e.nome) if e.tipo == "acao" else None
        if f:
            uso[e.usuario_id][f] += 1
    return uso


def uso(b: Base) -> dict:
    por_usuario = _uso_por_usuario(b.periodo)
    linhas = []
    for uid, c in por_usuario.items():
        u = b.usuario(uid)
        if u is None:
            continue
        linhas.append({"usuario_id": uid, "nome": u.nome, "escritorio": b.nome_esc(u.escritorio_id),
                       "funcoes": {fid: c.get(fid, 0) for fid, *_ in FUNCOES},
                       "nao_usa": [rot for fid, rot, *_ in FUNCOES if not c.get(fid)]})
    linhas.sort(key=lambda x: -sum(x["funcoes"].values()))
    totais = {fid: {"rotulo": rot, "usos": sum(l["funcoes"][fid] for l in linhas),
                    "usuarios": sum(1 for l in linhas if l["funcoes"][fid])} for fid, rot, *_ in FUNCOES}
    # notas baixadas por mês (documentos recebidos do ADN), últimos 6 meses
    meses = []
    m = b.agora.astimezone(BRASILIA).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for _ in range(6):
        meses.append(m)
        m = (m - timedelta(days=1)).replace(day=1)
    meses.reverse()
    q = (select(Empresa.escritorio_id, BuscaJob.iniciado_em, BuscaJob.docs_recebidos)
         .join(Empresa, Empresa.id == BuscaJob.empresa_id).where(BuscaJob.iniciado_em >= meses[0].astimezone(timezone.utc)))
    soma: dict[int, Counter] = defaultdict(Counter)
    for eid, ini, docs in b.db.execute(q):
        if eid in b.escritorios and ini is not None:
            soma[eid][_br(ini).strftime("%Y-%m")] += docs or 0
    rotulos = [x.strftime("%Y-%m") for x in meses]
    notas = [{"escritorio": b.nome_esc(eid), "meses": [soma[eid].get(r, 0) for r in rotulos]}
             for eid in sorted(soma, key=lambda i: -sum(soma[i].values()))]
    return {"funcoes": [{"id": fid, "rotulo": rot} for fid, rot, *_ in FUNCOES], "por_usuario": linhas,
            "totais": totais, "sem_uso": [t["rotulo"] for t in totais.values() if not t["usuarios"]],
            "notas_por_mes": {"meses": rotulos, "escritorios": notas}}


# ---------------------------------------------------------------------------
# Frequência
# ---------------------------------------------------------------------------

def frequencia(b: Base) -> dict:
    dias_usuario: dict[int, set[date]] = defaultdict(set)
    horas = Counter()
    for e in b.periodo:
        if e.tipo != "pagina":
            continue
        t = _br(e.momento)
        dias_usuario[e.usuario_id].add(t.date())
        horas[t.hour] += 1
    periodos = {"Madrugada (0h–6h)": range(0, 6), "Manhã (6h–12h)": range(6, 12),
                "Tarde (12h–18h)": range(12, 18), "Noite (18h–24h)": range(18, 24)}
    sessoes: dict[str, float] = defaultdict(float)
    for e in b.periodo:
        if e.tipo == "tempo" and e.dados:
            sessoes[e.sessao] += e.dados.get("s") or 0
    duracoes = [s / 60 for s in sessoes.values() if s > 0]
    todos_dias = [d for ds in dias_usuario.values() for d in ds]
    no_fechamento = sum(1 for d in todos_dias if d.day <= 10)
    por_escritorio: dict[int, set[int]] = defaultdict(set)
    for uid in dias_usuario:
        u = b.usuario(uid)
        if u:
            por_escritorio[u.escritorio_id].add(uid)
    usuarios = []
    for uid, ds in sorted(dias_usuario.items(), key=lambda x: -len(x[1])):
        u = b.usuario(uid)
        if u:
            usuarios.append({"nome": u.nome, "escritorio": b.nome_esc(u.escritorio_id), "dias": len(ds)})
    return {
        "dias_periodo": b.dias,
        "media_dias_acesso": round(statistics.mean(len(d) for d in dias_usuario.values()), 1) if dias_usuario else None,
        "usuarios": usuarios,
        "horas": [horas.get(h, 0) for h in range(24)],
        "periodos": [{"rotulo": r, "acessos": sum(horas.get(h, 0) for h in hs)} for r, hs in periodos.items()],
        "sessao_media_min": round(statistics.mean(duracoes), 1) if duracoes else None,
        "sessao_mediana_min": _mediana(duracoes), "sessoes": len(duracoes),
        "pct_dias_fechamento": _pct(no_fechamento, len(todos_dias)),
        "pct_esperado_fechamento": round(100 * 10 / 30.4, 1),
        "pessoas_por_escritorio": sorted(({"escritorio": b.nome_esc(eid), "pessoas": len(us),
                                            "cadastradas": sum(1 for u in b.usuarios if u.escritorio_id == eid)}
                                           for eid, us in por_escritorio.items()), key=lambda x: -x["pessoas"]),
    }


# ---------------------------------------------------------------------------
# Retenção
# ---------------------------------------------------------------------------

def retencao(b: Base) -> dict:
    dias: dict[int, set[date]] = defaultdict(set)
    for e in b.eventos:
        if e.tipo in ("pagina", "login"):
            dias[e.usuario_id].add(_br(e.momento).date())
    usaram = [uid for uid, ds in dias.items() if ds]
    voltaram = [uid for uid in usaram if len(dias[uid]) >= 2]
    logaram = {u.id for u in b.usuarios if u.ultimo_acesso_em or u.id in dias}
    ativos = {e.usuario_id for e in b.periodo if e.tipo in ("pagina", "login")}
    uso_ativos = _uso_por_usuario([e for e in b.periodo if e.usuario_id in ativos])
    return {
        "pct_voltaram": _pct(len(voltaram), len(usaram)), "meta_retorno": META_RETORNO,
        "usaram": len(usaram), "voltaram": len(voltaram),
        "pct_ativos": _pct(len(ativos & logaram), len(logaram)), "ativos": len(ativos), "logaram": len(logaram),
        "funcoes_ativos": [{"rotulo": rot, "usuarios": sum(1 for c in uso_ativos.values() if c.get(fid)),
                            "pct": _pct(sum(1 for c in uso_ativos.values() if c.get(fid)), len(ativos))}
                           for fid, rot, *_ in FUNCOES],
    }


# ---------------------------------------------------------------------------
# Pesquisa
# ---------------------------------------------------------------------------

def pesquisa(b: Base) -> dict:
    rs = [r for r in b.db.scalars(select(PesquisaResposta).where(PesquisaResposta.adiada.is_(False))
                                  .order_by(PesquisaResposta.momento.desc())) if r.usuario_id in b.ids]
    # a resposta mais recente de cada pessoa
    ultimas = {}
    for r in rs:
        ultimas.setdefault(r.usuario_id, r)
    us = list(ultimas.values())
    dec = Counter(r.decepcao for r in us if r.decepcao)
    notas = [r.nps for r in us if r.nps is not None]
    nps = round(100 * (sum(1 for n in notas if n >= 9) - sum(1 for n in notas if n <= 6)) / len(notas)) if notas else None
    horas = [r.horas for r in us if r.horas is not None]
    return {
        "respostas": len(us), "meta_decepcao": META_DECEPCAO,
        "decepcao": {k: dec.get(k, 0) for k in ("muito", "pouco", "nada")},
        "pct_muito": _pct(dec.get("muito", 0), sum(dec.values())),
        "nps": nps, "nps_respostas": len(notas),
        "nps_distribuicao": [sum(1 for n in notas if n == i) for i in range(11)],
        "horas_media": round(statistics.mean(horas), 1) if horas else None, "horas_mediana": _mediana([float(h) for h in horas]),
        "comentarios": [{"momento": _utc(r.momento), "nome": (b.usuario(r.usuario_id) or Usuario(nome="?")).nome,
                         "escritorio": b.nome_esc(r.escritorio_id), "texto": r.comentario, "nps": r.nps, "decepcao": r.decepcao}
                        for r in rs if r.comentario][:50],
    }


# ---------------------------------------------------------------------------
# Mapa de experiência
# ---------------------------------------------------------------------------

def paginas(b: Base) -> list[dict]:
    c = Counter(e.nome for e in b.periodo if e.tipo == "pagina")
    return [{"rota": r, "acessos": n} for r, n in c.most_common()]


def experiencia(b: Base, rota: str | None = None) -> dict:
    por_sessao: dict[str, list[str]] = defaultdict(list)
    for e in b.periodo:
        if e.tipo == "pagina" and (not por_sessao[e.sessao] or por_sessao[e.sessao][-1] != e.nome):
            por_sessao[e.sessao].append(e.nome)
    transicoes = Counter()
    caminhos = Counter()
    abandono = Counter()
    for seq in por_sessao.values():
        if not seq:
            continue
        for a, c in zip(seq, seq[1:]):
            transicoes[(a, c)] += 1
        caminhos[" → ".join(seq[:4])] += 1
        abandono[seq[-1]] += 1
    acessos = Counter(e.nome for e in b.periodo if e.tipo == "pagina")
    mortos = Counter((e.nome, (e.dados or {}).get("alvo") or "?") for e in b.periodo
                     if e.tipo == "clique" and (e.dados or {}).get("morto"))
    saida = {
        "paginas": paginas(b),
        "transicoes": [{"de": a, "para": c, "vezes": n} for (a, c), n in transicoes.most_common(30)],
        "caminhos": [{"caminho": k, "sessoes": n} for k, n in caminhos.most_common(15)],
        "abandono": [{"rota": r, "sessoes": n, "pct_saidas": _pct(n, acessos.get(r, 0))} for r, n in abandono.most_common(15)],
        "cliques_mortos": [{"rota": r, "alvo": a, "vezes": n} for (r, a), n in mortos.most_common(30)],
    }
    if rota:
        cliques = [e.dados for e in b.periodo if e.tipo == "clique" and e.nome == rota and e.dados]
        rol = [((e.dados or {}).get("p") or 0) for e in b.periodo if e.tipo == "rolagem" and e.nome == rota]
        alvos = Counter((d.get("alvo") or "?") for d in cliques)
        saida["rota"] = {
            "rota": rota,
            "cliques": [{"x": d.get("x"), "y": d.get("y"), "w": d.get("w"), "morto": d.get("morto")} for d in cliques][-3000:],
            "alvos": [{"alvo": a, "vezes": n} for a, n in alvos.most_common(20)],
            # % das visitas que chegaram a cada profundidade
            "rolagem": [{"ate": p, "pct": _pct(sum(1 for x in rol if x >= p), len(rol))} for p in range(0, 101, 10)],
            "visitas_rolagem": len(rol),
        }
    return saida


# ---------------------------------------------------------------------------
# Erros e suporte
# ---------------------------------------------------------------------------

def _categoria(msg: str) -> str:
    m = (msg or "").lower()
    if "procura" in m:
        return "Procuração"
    if "certificado" in m or "pfx" in m or "tls" in m or "ssl" in m:
        return "Certificado"
    if "cnpjconsulta" in m or "adn" in m or "http" in m or "sefin" in m:
        return "Comunicação com o ADN"
    return "Outros"


def erros(b: Base) -> dict:
    db = b.db
    falhas = list(db.execute(
        select(BuscaJob, Empresa.escritorio_id).join(Empresa, Empresa.id == BuscaJob.empresa_id)
        .where(BuscaJob.status == "erro", BuscaJob.criado_em >= b.inicio).order_by(BuscaJob.criado_em.desc())))
    cats = Counter(_categoria(j.mensagem or "") for j, _ in falhas)
    hoje = b.agora
    certs = list(db.scalars(select(Certificado).where(Certificado.escritorio_id.in_(list(b.escritorios) or [0]))))
    vencidos = [c for c in certs if _utc(c.validade) < hoje]
    vencendo = [c for c in certs if hoje <= _utc(c.validade) < hoje + timedelta(days=30)]
    front = Counter(((e.dados or {}).get("msg") or e.nome)[:160] for e in b.periodo if e.tipo == "erro")
    rejeitadas = int(db.scalar(select(func.count()).select_from(NotaEmitida).where(
        NotaEmitida.situacao == "rejeitada", NotaEmitida.criado_em >= b.inicio)) or 0)
    return {
        "buscas_com_erro": len(falhas),
        "buscas_por_categoria": [{"categoria": k, "vezes": n} for k, n in cats.most_common()],
        "ultimas_falhas": [{"momento": _utc(j.finalizado_em or j.criado_em), "escritorio": b.nome_esc(eid),
                            "categoria": _categoria(j.mensagem or ""), "mensagem": (j.mensagem or "")[:300]}
                           for j, eid in falhas[:20]],
        "certificados_vencidos": [{"escritorio": b.nome_esc(c.escritorio_id), "titular": c.titular_nome,
                                   "validade": _utc(c.validade)} for c in vencidos],
        "certificados_vencendo": len(vencendo),
        "notas_rejeitadas": rejeitadas,
        "erros_tela": [{"mensagem": k, "vezes": n} for k, n in front.most_common(20)],
    }


def suporte(b: Base) -> dict:
    from app.api.uso import ASSUNTOS
    ps = list(b.db.scalars(select(PedidoSuporte).order_by(PedidoSuporte.momento.desc()).limit(200)))
    c = Counter(p.assunto for p in ps if _utc(p.momento) >= b.inicio)
    return {
        "abertos": sum(1 for p in ps if p.situacao == "aberto"),
        "por_assunto": [{"assunto": ASSUNTOS.get(k, k), "vezes": n} for k, n in c.most_common()],
        "pedidos": [{"id": p.id, "momento": _utc(p.momento), "assunto": ASSUNTOS.get(p.assunto, p.assunto),
                     "mensagem": p.mensagem, "pagina": p.pagina, "situacao": p.situacao,
                     "escritorio": b.nome_esc(p.escritorio_id),
                     "usuario": (b.db.get(Usuario, p.usuario_id).nome if p.usuario_id and b.db.get(Usuario, p.usuario_id) else None)}
                    for p in ps],
    }
