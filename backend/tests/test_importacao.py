"""Importação de empresas por planilha: todas entram por procuração e com busca agendada."""
import io

import pytest
from openpyxl import Workbook, load_workbook

from app.core import brasilapi
from app.core.db import nova_sessao
from app.models import BuscaJob, Empresa
from tests.certs import criar_pfx, dv_cnpj

SENHA = "S3nh@-Teste!"
CONTAB = dv_cnpj("112223330001")
A, B, C = dv_cnpj("114447770001"), dv_cnpj("223334440001"), dv_cnpj("002223330001")  # C começa com zeros


def _xlsx(linhas) -> bytes:
    wb = Workbook()
    for l in linhas:
        wb.active.append(l)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def contab(cliente):
    r = cliente.post("/api/contabilidade", data={"cnpj": CONTAB, "razao_social": "Contab", "senha": SENHA},
                     files={"arquivo": ("c.pfx", criar_pfx("CONTAB", cnpj=CONTAB), "application/x-pkcs12")})
    assert r.status_code == 200


def _previa(cliente, nome, conteudo):
    return cliente.post("/api/importacao/empresas/previa", files={"arquivo": (nome, conteudo, "application/octet-stream")})


def test_exige_contabilidade(cliente):
    r = _previa(cliente, "e.xlsx", _xlsx([["CNPJ"], [A]]))
    assert r.status_code == 409 and "contabilidade" in r.json()["detail"]


def test_modelo(cliente):
    r = cliente.get("/api/importacao/empresas/modelo")
    assert r.status_code == 200 and "modelo_importacao_empresas.xlsx" in r.headers["content-disposition"]
    assert [c.value for c in load_workbook(io.BytesIO(r.content)).active[1]] == ["CNPJ", "Razão social", "Apelido"]


def test_previa_e_importacao_xlsx(cliente, contab, monkeypatch):
    monkeypatch.setattr(brasilapi, "consultar", lambda c: {"razao_social": "DA BRASILAPI LTDA", "nome_fantasia": None, "uf": "DF",
                                                         "municipio": "Brasilia", "situacao_cadastral": "ATIVA", "bruto": {}})
    planilha = _xlsx([
        ["Apelido", "CNPJ", "Razão Social"],               # cabeçalho em outra ordem
        ["Cliente A", A, "EMPRESA A LTDA"],
        [None, int(C), None],                               # numérico sem os zeros à esquerda; sem razão social
        ["Repetida", A, "EMPRESA A DE NOVO"],
        [None, "11.222.333/0001-82", "DV ERRADO"],
        [None, CONTAB, "JA EXISTE"],
        [None, None, None],                                 # linha vazia: ignorada
        [None, B, "EMPRESA B: LTDA"],
    ])
    r = _previa(cliente, "empresas.xlsx", planilha)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["resumo"] == {"criar": 3, "existente": 1, "repetida": 1, "erro": 1}
    linhas = {l["linha"]: l for l in p["linhas"]}
    assert linhas[2]["apelido"] == "Cliente A" and linhas[3]["cnpj"] == C and "BrasilAPI" in linhas[3]["mensagem"]
    assert linhas[4]["situacao"] == "repetida" and linhas[5]["situacao"] == "erro" and linhas[6]["situacao"] == "existente"

    validas = [{"cnpj": l["cnpj"], "razao_social": l["razao_social"], "apelido": l["apelido"]} for l in p["linhas"] if l["situacao"] == "criar"]
    r = cliente.post("/api/importacao/empresas", json={"linhas": validas})
    assert r.status_code == 200, r.text
    assert r.json()["resumo"] == {"criada": 3, "existente": 0, "erro": 0}
    with nova_sessao() as db:
        for cnpj in (A, B, C):
            e = db.query(Empresa).filter(Empresa.cnpj == cnpj).one()
            assert e.modo_certificado == "contabilidade" and e.ativa and not e.is_contabilidade
            assert db.query(BuscaJob).filter(BuscaJob.empresa_id == e.id, BuscaJob.status == "fila").count() == 1
        assert db.query(Empresa).filter(Empresa.cnpj == C).one().razao_social == "DA BRASILAPI LTDA"
    # Na lista, aparecem com acesso por procuração
    lista = {e["cnpj"]: e for e in cliente.get("/api/empresas").json()}
    assert lista[A]["acesso"] == "procuracao" and lista[A]["apelido"] == "Cliente A"
    # Importar de novo não duplica
    r = cliente.post("/api/importacao/empresas", json={"linhas": validas})
    assert r.json()["resumo"] == {"criada": 0, "existente": 3, "erro": 0}


def test_csv_ponto_e_virgula_sem_cabecalho(cliente, contab):
    conteudo = f"{A};EMPRESA A;A\n{B};EMPRESA B;B\n".encode("cp1252")
    p = _previa(cliente, "e.csv", conteudo).json()
    assert p["resumo"]["criar"] == 2 and p["linhas"][0]["linha"] == 1 and p["linhas"][0]["razao_social"] == "EMPRESA A"


def test_brasilapi_fora_sem_razao_social_vira_erro_da_linha(cliente, contab, monkeypatch):
    def fora(_):
        raise brasilapi.BrasilApiErro("A BrasilAPI não respondeu.")
    monkeypatch.setattr(brasilapi, "consultar", fora)
    r = cliente.post("/api/importacao/empresas", json={"linhas": [{"cnpj": A}, {"cnpj": B, "razao_social": "COM NOME"}]}).json()
    assert r["resumo"] == {"criada": 1, "existente": 0, "erro": 1}
    assert "BrasilAPI" in r["linhas"][0]["mensagem"]


def test_formato_invalido(cliente, contab):
    assert _previa(cliente, "e.pdf", b"%PDF").status_code == 422
    assert _previa(cliente, "e.xlsx", b"nao e xlsx").status_code == 422
