"""Contask NF: API local em 127.0.0.1 que também serve o frontend compilado."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, buscas, dashboard, emissor, emissor_notas, empresas, exportacoes, importacao, notas, sistema
from app.core import cripto
from app.core.config import config
from app.core.migracao import migrar
from app.core.seguranca import ProtecaoLocalMiddleware

log = logging.getLogger("contask")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    cfg = config()
    if cfg.host not in ("127.0.0.1", "localhost") and not cfg.lista_hosts:
        raise RuntimeError("Fora de 127.0.0.1 é obrigatório definir CONTASK_HOSTS.")
    migrar()
    if not cripto.chave_disponivel():
        raise RuntimeError(
            "Defina CONTASK_CHAVE_MESTRA (chave Fernet em base64) no ambiente ou no .env. Sem ela a API não sobe."
        )
    cfg = config()
    g = None
    if cfg.fila_ativa:
        from app.adn.cliente import ClienteADN
        from app.core.db import nova_sessao
        from app.jobs import definir_gerenciador
        from app.jobs.fila import Gerenciador

        g = Gerenciador(nova_sessao, lambda pfx, senha: ClienteADN(pfx=pfx, senha=senha, base_url=cfg.adn_url),
                        max_total=cfg.max_buscas, pausa=cfg.pausa_paginas, intervalo_h=cfg.intervalo_busca_h,
                        buscar_ao_abrir=cfg.buscar_ao_abrir)
        definir_gerenciador(g)
        g.iniciar()
    exp = None
    if cfg.fila_ativa:
        from app.core.db import nova_sessao
        from app.jobs import definir_exportador
        from app.jobs.exportador import Exportador

        exp = Exportador(nova_sessao)
        definir_exportador(exp)
        exp.retomar_pendentes()
    rec = None
    if cfg.fila_ativa:
        from app.core.db import nova_sessao
        from app.emissor.recorrencia import Agendador

        rec = Agendador(nova_sessao)
        rec.iniciar()
    try:
        yield
    finally:
        if rec is not None:
            rec.parar()
        if exp is not None:
            exp.parar()
            from app.jobs import definir_exportador
            definir_exportador(None)
        if g is not None:
            g.parar()
            from app.jobs import definir_gerenciador
            definir_gerenciador(None)


def criar_app() -> FastAPI:
    app = FastAPI(title="Contask NF", lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json")
    app.add_middleware(ProtecaoLocalMiddleware)
    app.include_router(auth.router)
    app.include_router(sistema.router)
    app.include_router(empresas.router)
    app.include_router(buscas.router)
    app.include_router(notas.router)
    app.include_router(dashboard.router)
    app.include_router(exportacoes.router)
    app.include_router(importacao.router)
    app.include_router(emissor.router)
    app.include_router(emissor_notas.router)

    @app.exception_handler(RequestValidationError)
    async def validacao(_req: Request, exc: RequestValidationError):
        # Mensagem em pt-BR e sem ecoar valores enviados (podem conter senha)
        campos = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
        return JSONResponse({"detail": f"Dados inválidos ou ausentes: {', '.join(campos)}."}, status_code=422)

    @app.api_route("/api/{_resto:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def api_inexistente(_resto: str):
        raise HTTPException(404, "Rota da API não encontrada.")

    dist = config().frontend_dist
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{caminho:path}", include_in_schema=False)
    def spa(caminho: str):
        alvo = (dist / caminho).resolve()
        if caminho and alvo.is_file() and dist.resolve() in alvo.parents:
            return FileResponse(alvo)
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return HTMLResponse("<h1>Contask NF</h1><p>Frontend não compilado. Rode <code>npm run build</code> em "
                            "<code>frontend/</code> ou use o <code>iniciar.bat</code>.</p>", status_code=503)

    return app


app = criar_app()
