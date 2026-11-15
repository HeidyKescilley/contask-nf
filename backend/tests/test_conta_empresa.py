"""Conta de empresa: a própria empresa emite as notas; um CNPJ só, sem cadastrar outros."""
from app.core.db import nova_sessao
from app.models import Empresa, Escritorio
from tests.test_empresas import CLIENTE, _contabilidade, _empresa


def _virar_empresa(cliente):
    esc = cliente.get("/api/auth/eu").json()["escritorio"]["id"]
    with nova_sessao() as db:
        db.get(Escritorio, esc).tipo = "empresa"
        db.commit()
    return esc


def test_conta_nova_e_de_contador_por_padrao(cliente):
    assert cliente.get("/api/auth/eu").json()["escritorio"]["tipo"] == "contador"


def test_conta_empresa_cadastra_so_a_propria_empresa(cliente):
    esc = _virar_empresa(cliente)
    assert cliente.get("/api/auth/eu").json()["escritorio"]["tipo"] == "empresa"
    r = _contabilidade(cliente)
    assert r.status_code == 200, r.text
    propria = r.json()["empresa"]
    # A empresa principal já nasce emissora, com os dados de prestador criados
    assert propria["emite_nfse"] is True
    assert cliente.get(f"/api/emissor/empresas/{propria['id']}").json()["config"]["producao_liberada"] is True
    # Outro CNPJ: bloqueado no cadastro e na importação
    r = _empresa(cliente)
    assert r.status_code == 403 and "um CNPJ só" in r.json()["detail"]
    r = cliente.post("/api/importacao/empresas", json={"linhas": [{"cnpj": CLIENTE}]})
    assert r.status_code == 403
    with nova_sessao() as db:
        assert db.query(Empresa).filter(Empresa.escritorio_id == esc).count() == 1


def test_conta_de_contador_continua_com_varias_empresas(cliente):
    assert _contabilidade(cliente).status_code == 200
    assert cliente.get("/api/contabilidade").json()["emite_nfse"] is False
    assert _empresa(cliente).status_code == 201


def test_admin_cria_e_muda_o_tipo_de_conta(cliente):
    from app.tools import usuarios
    usuarios.main(["admin", "teste@contask.local"])
    r = cliente.post("/api/admin/escritorios", json={"nome": "Clínica X", "email": "bia@clinicax.com", "tipo": "empresa"})
    assert r.status_code == 201, r.text
    esc_id = r.json()["usuario"]["escritorio_id"]
    lista = {e["id"]: e for e in cliente.get("/api/admin/escritorios").json()}
    assert lista[esc_id]["tipo"] == "empresa"
    assert cliente.post("/api/admin/escritorios", json={"nome": "Y", "email": "y@y.com", "tipo": "outro"}).status_code == 422
    # Conta de contador com duas empresas não vira conta de empresa
    meu = cliente.get("/api/auth/eu").json()["escritorio"]["id"]
    assert _contabilidade(cliente).status_code == 200 and _empresa(cliente).status_code == 201
    r = cliente.put(f"/api/admin/escritorios/{meu}", json={"nome": "Meu", "tipo": "empresa"})
    assert r.status_code == 409 and "um CNPJ só" in r.json()["detail"]
    r = cliente.put(f"/api/admin/escritorios/{esc_id}", json={"nome": "Clínica X", "tipo": "contador"})
    assert r.status_code == 200 and r.json()["tipo"] == "contador"


def test_cli_cria_conta_de_empresa(cliente, capsys):
    from app.tools import usuarios
    usuarios.main(["novo-escritorio", "Clínica Y", "c@clinicay.com", "Cris", "--tipo", "empresa"])
    with nova_sessao() as db:
        assert db.query(Escritorio).filter(Escritorio.nome == "Clínica Y").one().tipo == "empresa"
