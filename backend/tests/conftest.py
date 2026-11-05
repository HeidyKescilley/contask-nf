import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture()
def app_teste(tmp_path, monkeypatch):
    """App com pasta de dados temporária e chave-mestra de teste (não toca no keyring real)."""
    monkeypatch.setenv("CONTASK_DADOS_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv("CONTASK_FRONTEND_DIST", str(tmp_path / "dist"))
    monkeypatch.setenv("CONTASK_FILA_ATIVA", "false")
    from app.core import config as cfgmod, cripto, db
    cfgmod.config.cache_clear()
    db.reiniciar_para_testes()
    cripto.definir_chave_para_testes(Fernet.generate_key())
    from app.main import criar_app
    yield criar_app()
    db.reiniciar_para_testes()
    cripto.definir_chave_para_testes(None)
    cfgmod.config.cache_clear()


@pytest.fixture()
def cliente(app_teste):
    with TestClient(app_teste, base_url="http://127.0.0.1:8765") as c:
        yield c
