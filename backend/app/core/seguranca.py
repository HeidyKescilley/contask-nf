"""Proteção da API.

- Host: só 127.0.0.1/localhost ou o domínio configurado (bloqueia DNS rebinding).
- Origin: quando presente, só a própria aplicação (bloqueia sites abertos no mesmo navegador). O site de
  vendas (CONTASK_SITE_URL) só alcança as rotas do formulário de teste grátis (ROTAS_SITE).
- Sec-Fetch-Site cross-site em requisições que mudam estado também é recusado.
- Toda rota /api exige sessão válida, exceto as públicas; quem precisa trocar a senha só acessa
  as rotas de login até trocar.
"""
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import config

METODOS_ESCRITA = {"POST", "PUT", "PATCH", "DELETE"}
ROTAS_PUBLICAS = {
    "/api/auth/eu", "/api/auth/entrar", "/api/auth/sair", "/api/auth/cadastrar", "/api/ping", "/api/saude",
    "/api/publico/teste", "/api/publico/black-friday", "/api/publico/visita",
}
ROTAS_SITE = {"/api/publico/teste", "/api/publico/black-friday", "/api/publico/visita"}
ROTAS_TROCA_SENHA = ROTAS_PUBLICAS | {"/api/auth/senha"}


def _usuario(token: str | None):
    from app.core import autenticacao
    from app.core.db import nova_sessao

    with nova_sessao() as db:
        u = autenticacao.usuario_da_sessao(db, token)
        if u is not None:
            db.expunge(u)
        return u


class ProtecaoLocalMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cfg = config()
        host = (request.headers.get("host") or "").lower()
        if host not in cfg.hosts_permitidos:
            return JSONResponse({"detail": "Host não permitido."}, status_code=400)

        origin = request.headers.get("origin")
        do_site = (origin is not None and cfg.origem_site is not None and origin.lower() == cfg.origem_site
                   and request.url.path in ROTAS_SITE)
        if origin is not None and origin.lower() not in cfg.origens_permitidas and not do_site:
            return JSONResponse({"detail": "Origem não permitida."}, status_code=403)

        if request.method in METODOS_ESCRITA and request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Origem não permitida."}, status_code=403)

        caminho = request.url.path
        if caminho.startswith("/api/") and caminho not in ROTAS_PUBLICAS:
            from app.core.autenticacao import COOKIE

            u = await run_in_threadpool(_usuario, request.cookies.get(COOKIE))
            if u is None:
                return JSONResponse({"detail": "Entre com seu e-mail e senha."}, status_code=401)
            if u.trocar_senha and caminho not in ROTAS_TROCA_SENHA:
                return JSONResponse({"detail": "Troque a senha para continuar."}, status_code=403)
            request.state.usuario = u

        resposta = await call_next(request)
        u = getattr(request.state, "usuario", None)
        if u is not None and resposta.status_code < 400:
            from app.api.uso import acao_da_rota, gravar_acao
            acao = acao_da_rota(request.method, caminho)
            if acao:
                await run_in_threadpool(gravar_acao, u, acao)
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        # Telas: SAMEORIGIN (o mapa de calor do Monitoramento abre a própria tela num iframe); API: DENY
        resposta.headers.setdefault("X-Frame-Options", "DENY" if caminho.startswith("/api/") else "SAMEORIGIN")
        resposta.headers.setdefault("Referrer-Policy", "no-referrer")
        if cfg.cookie_secure:
            resposta.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if caminho.startswith("/api/"):
            resposta.headers.setdefault("Cache-Control", "no-store")
        return resposta
