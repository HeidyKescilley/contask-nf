import sqlite3

import pytest
from cryptography.fernet import Fernet

from app.core import cripto


def test_saude_e_wal(cliente):
    r = cliente.get("/api/saude")
    assert r.status_code == 200
    d = r.json()
    assert d["banco"]["journal_mode"] == "wal"
    assert d["chave_mestra"] is True
    assert "empresas" not in d and "tem_contabilidade" not in d


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765"])
def test_host_local_aceito(cliente, host):
    assert cliente.get("/api/saude", headers={"host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.com", "192.168.0.10:8765", "127.0.0.1.nip.io:8765", "attacker.localhost:8765"])
def test_host_externo_recusado(cliente, host):
    r = cliente.get("/api/saude", headers={"host": host})
    assert r.status_code == 400
    # Vale também para o frontend, não só para a API (DNS rebinding)
    assert cliente.get("/", headers={"host": host}).status_code == 400


@pytest.mark.parametrize("origin", ["http://127.0.0.1:8765", "http://localhost:8765", "http://localhost:5173"])
def test_origin_local_aceito(cliente, origin):
    assert cliente.get("/api/saude", headers={"origin": origin}).status_code == 200


@pytest.mark.parametrize("origin", ["https://evil.com", "http://127.0.0.1:9999", "null", "http://localhost.evil.com"])
def test_origin_externo_recusado(cliente, origin):
    assert cliente.get("/api/saude", headers={"origin": origin}).status_code == 403
    assert cliente.post("/api/qualquer", headers={"origin": origin}).status_code == 403


def test_escrita_cross_site_recusada(cliente):
    r = cliente.post("/api/qualquer", headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403


def test_cabecalhos_de_seguranca(cliente):
    r = cliente.get("/api/saude")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_api_inexistente_404(cliente):
    assert cliente.get("/api/nao-existe").status_code == 404


def test_frontend_ausente_explica(cliente):
    r = cliente.get("/")
    assert r.status_code == 503
    assert "npm run build" in r.text


def test_cripto_ida_e_volta(app_teste):
    token = cripto.cifrar_texto("senha-secreta-123")
    assert "senha-secreta-123" not in token
    assert cripto.decifrar_texto(token) == "senha-secreta-123"
    dados = b"\x30\x82PFX" * 100
    assert cripto.decifrar(cripto.cifrar(dados)) == dados


def test_cripto_chave_errada(app_teste):
    token = cripto.cifrar_texto("x")
    cripto.definir_chave_para_testes(Fernet.generate_key())
    with pytest.raises(cripto.ErroCripto):
        cripto.decifrar_texto(token)


def test_migracao_cria_tabelas_e_contabilidade_unica(cliente, tmp_path):
    con = sqlite3.connect(tmp_path / "dados" / "contask.db")
    tabelas = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"escritorio", "usuario", "sessao_usuario", "certificado", "empresa", "sync_estado",
            "documento_dfe", "nota", "evento_nota", "busca_job", "busca_log", "exportacao",
            "alembic_version"} <= tabelas
    eid = con.execute("select id from escritorio").fetchone()[0]
    con.execute("insert into escritorio (nome) values ('Outro')")
    eid2 = con.execute("select id from escritorio where nome = 'Outro'").fetchone()[0]
    ins = ("insert into empresa (cnpj, razao_social, is_contabilidade, modo_certificado, ativa, criado_em, escritorio_id) "
           "values (?, 'X', ?, 'contabilidade', 1, '2026-01-01', ?)")
    con.execute(ins, ("11111111000111", 1, eid))
    con.execute(ins, ("22222222000122", 0, eid))
    con.execute(ins, ("33333333000133", 0, eid))
    con.commit()
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(ins, ("44444444000144", 1, eid))
    con.rollback()
    con.execute(ins, ("55555555000155", 1, eid2))
    con.execute(ins, ("11111111000111", 0, eid2))
    con.commit()
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(ins, ("11111111000111", 0, eid))
    con.close()
