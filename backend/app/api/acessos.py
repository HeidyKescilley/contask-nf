"""Acessos do site de vendas: registro próprio de visitas e o painel de canais x leads.

- POST /api/publico/visita é público (ROTAS_PUBLICAS) e só aceita a origem do site (ROTAS_SITE).
  Não usa cookie e não guarda IP: o visitante vira um HMAC de IP + navegador + dia, que não deixa
  seguir a pessoa de um dia para o outro. Robôs conhecidos são ignorados.
- GET /api/admin/acessos (admin do sistema): visitas por dia, canal, página e dispositivo, cruzadas
  com os leads dos formulários (canal tirado do utm_source ou do site de onde a pessoa veio).
"""
from __future__ import annotations

import hashlib
import hmac
import re
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone  # noqa: F401
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import exigir_admin
from app.api.auth import ip_cliente
from app.core import autenticacao as auth
from app.core import escritorios as regras
from app.core.config import config
from app.core.db import sessao
from app.models import Lead, Usuario, Visita

publico = APIRouter(prefix="/api/publico", tags=["site"])
painel = APIRouter(prefix="/api/admin/acessos", tags=["admin"])

# Uma página aberta várias vezes seguidas não deve inflar os números: até 120 registros por IP por hora
limitador_visitas = auth.Limitador(maximo=120, janela=60 * 60)
ROBOS = re.compile(r"bot|crawl|spider|slurp|headless|lighthouse|preview|facebookexternalhit|whatsapp|curl|python|wget", re.I)
# Domínios conhecidos viram nomes curtos de canal
APELIDOS = {"t.co": "twitter", "x.com": "twitter", "wa.me": "whatsapp", "chat.whatsapp.com": "whatsapp",
            "api.whatsapp.com": "whatsapp", "web.whatsapp.com": "whatsapp", "lnkd.in": "linkedin", "youtu.be": "youtube"}


class NovaVisita(BaseModel):
    pagina: str = Field(max_length=300)
    referencia: str | None = Field(None, max_length=500)
    largura: int | None = None


def _limpo(v: str | None, tam: int) -> str | None:
    v = re.sub(r"[^\w .\-/]", "", (v or "").strip().lower())[:tam]
    return v or None


def canal_do_dominio(host: str) -> str:
    host = host.lower().split(":")[0]
    if host in APELIDOS:
        return APELIDOS[host]
    partes = [p for p in host.split(".") if p not in ("www", "l", "m", "lm", "mobile", "com", "br", "co", "net", "org")]
    return partes[-1] if partes else host


def canal(utm_source: str | None, referencia_host: str | None) -> str:
    if utm_source:
        return _limpo(utm_source, 60) or "direto"
    if referencia_host:
        return canal_do_dominio(referencia_host)
    return "direto"


def _visitante(ip: str, navegador: str, dia) -> str:
    chave = config().chave_mestra.get_secret_value().encode() if config().chave_mestra else b"contask"
    return hmac.new(chave, f"{dia}|{ip}|{navegador}".encode(), hashlib.sha256).hexdigest()[:16]


@publico.post("/visita", status_code=204)
def registrar(d: NovaVisita, request: Request, db: Session = Depends(sessao)):
    navegador = request.headers.get("user-agent", "")
    ip = ip_cliente(request)
    if not navegador or ROBOS.search(navegador) or limitador_visitas.bloqueado(ip):
        return Response(status_code=204)
    limitador_visitas.falhou(ip)
    url = urlsplit(d.pagina if d.pagina.startswith("/") else "/")
    q = parse_qs(url.query)
    site = (config().site_url or "").lower()
    ref_host = urlsplit(d.referencia).hostname if d.referencia else None
    if ref_host and site and ref_host in site:  # navegação dentro do próprio site
        ref_host = None
    hoje = regras.hoje()
    db.add(Visita(dia=hoje, pagina=(url.path or "/")[:120], canal=canal((q.get("utm_source") or [None])[0], ref_host),
                  meio=_limpo((q.get("utm_medium") or [None])[0], 60), campanha=_limpo((q.get("utm_campaign") or [None])[0], 100),
                  referencia=ref_host[:120] if ref_host else None,
                  dispositivo="celular" if (d.largura or 1024) < 768 or "Mobi" in navegador else "computador",
                  visitante=_visitante(ip, navegador, hoje)))
    db.commit()
    return Response(status_code=204)


def canal_do_lead(origem: str | None) -> str:
    """Lead.origem é "caminho?utm... (de dominio)", gravado pelos formulários."""
    if not origem:
        return "direto"
    m = re.search(r"\(de ([^)]+)\)\s*$", origem)
    q = parse_qs(urlsplit(origem.split(" (de ")[0]).query)
    return canal((q.get("utm_source") or [None])[0], m.group(1) if m else None)


def pagina_do_lead(origem: str | None) -> str:
    return urlsplit((origem or "/").split(" (de ")[0]).path or "/"


@painel.get("")
def resumo(dias: int = 30, db: Session = Depends(sessao), _adm: Usuario = Depends(exigir_admin)):
    dias = max(1, min(dias, 365))
    fim = regras.hoje()
    inicio = fim - timedelta(days=dias - 1)
    visitas = db.execute(select(Visita.dia, Visita.pagina, Visita.canal, Visita.dispositivo, Visita.visitante)
                         .where(Visita.dia >= inicio)).all()
    # Tabela pequena: o recorte por dia (horário de Brasília) é feito em _montar
    desde = datetime.combine(inicio - timedelta(days=1), time.min)
    leads = list(db.scalars(select(Lead).where(Lead.criado_em >= desde)))
    return _montar(visitas, leads, inicio, fim)


def _dia_lead(l: Lead):
    dt = l.criado_em if l.criado_em.tzinfo else l.criado_em.replace(tzinfo=timezone.utc)
    return dt.astimezone(regras.BRASILIA).date()


def _montar(visitas, leads, inicio, fim) -> dict:
    leads = [l for l in leads if inicio <= _dia_lead(l) <= fim]
    pessoas_dia = defaultdict(set)
    por_dia_visitas, por_dia_leads = Counter(), Counter()
    canais = defaultdict(lambda: {"visitas": 0, "pessoas": set(), "leads": 0, "black_friday": 0})
    paginas = defaultdict(lambda: {"visitas": 0, "pessoas": set(), "leads": 0})
    dispositivos = Counter()
    for dia, pagina, can, disp, vis in visitas:
        por_dia_visitas[dia] += 1
        pessoas_dia[dia].add(vis)
        c = canais[can]
        c["visitas"] += 1
        c["pessoas"].add((dia, vis))
        p = paginas[pagina]
        p["visitas"] += 1
        p["pessoas"].add((dia, vis))
        dispositivos[(dia, vis, disp)] += 1
    for l in leads:
        por_dia_leads[_dia_lead(l)] += 1
        c = canais[canal_do_lead(l.origem)]
        c["leads"] += 1
        c["black_friday"] += l.campanha == "black_friday"
        paginas[pagina_do_lead(l.origem)]["leads"] += 1

    def taxa(leads_, pessoas):
        return round(100 * leads_ / pessoas, 1) if pessoas else None

    serie = []
    d = inicio
    while d <= fim:
        serie.append({"dia": d, "visitas": por_dia_visitas[d], "pessoas": len(pessoas_dia[d]), "leads": por_dia_leads[d]})
        d += timedelta(days=1)
    pessoas_total = sum(len(s) for s in pessoas_dia.values())
    disp = Counter(k[2] for k in dispositivos)
    return {
        "inicio": inicio, "fim": fim,
        "totais": {"visitas": len(visitas), "pessoas": pessoas_total, "leads": len(leads),
                   "black_friday": sum(l.campanha == "black_friday" for l in leads), "taxa": taxa(len(leads), pessoas_total)},
        "por_dia": serie,
        "canais": sorted(({"canal": k, "visitas": v["visitas"], "pessoas": len(v["pessoas"]), "leads": v["leads"],
                           "black_friday": v["black_friday"], "taxa": taxa(v["leads"], len(v["pessoas"]))}
                          for k, v in canais.items()), key=lambda x: (-x["pessoas"], -x["leads"], x["canal"])),
        "paginas": sorted(({"pagina": k, "visitas": v["visitas"], "pessoas": len(v["pessoas"]), "leads": v["leads"],
                            "taxa": taxa(v["leads"], len(v["pessoas"]))} for k, v in paginas.items()),
                          key=lambda x: (-x["visitas"], x["pagina"])),
        "dispositivos": {"celular": disp["celular"], "computador": disp["computador"]},
    }
