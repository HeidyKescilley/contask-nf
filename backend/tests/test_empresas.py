import logging
import sqlite3

import pytest

from app.core import brasilapi
from app.fiscal.documentos import cnpj_valido, cpf_valido
from tests.certs import criar_pfx, dv_cnpj

SENHA = "S3nh@-Teste!"
CONTAB = dv_cnpj("112223330001")
CLIENTE = dv_cnpj("114447770001")
OUTRA_RAIZ = dv_cnpj("998887770001")
ALFANUM = dv_cnpj("12ABC34501DE")
CPF = "52998224725"


def _pfx(nome="CONTAB TESTE LTDA", **kw):
    if "cnpj" not in kw and "cpf" not in kw:
        kw["cnpj"] = CONTAB
    return criar_pfx(nome, **kw)


def _contabilidade(cliente, pfx=None, senha=SENHA, cnpj=CONTAB):
    return cliente.post("/api/contabilidade",
                        data={"cnpj": cnpj, "razao_social": "Contab Teste Ltda", "senha": senha, "uf": "DF"},
                        files={"arquivo": ("c.pfx", pfx or _pfx(), "application/x-pkcs12")})


def _empresa(cliente, cnpj=CLIENTE, **extra):
    data = {"cnpj": cnpj, "razao_social": "Cliente Teste Ltda", "modo_certificado": "contabilidade", **extra}
    files = extra.pop("files", None)
    data.pop("files", None)
    return cliente.post("/api/empresas", data=data, files=files)


# --- Documentos ---------------------------------------------------------------

def test_cnpj_numerico_e_alfanumerico():
    assert cnpj_valido("11.222.333/0001-81")
    assert not cnpj_valido("11.222.333/0001-82")
    assert cnpj_valido(ALFANUM) and ALFANUM[:5] == "12ABC"
    assert cnpj_valido(ALFANUM.lower())
    assert not cnpj_valido("00000000000000")
    assert cpf_valido(CPF) and not cpf_valido("52998224726")


# --- Certificado ----------------------------------------------------------------

def test_senha_errada_recusada_com_mensagem_clara(cliente):
    r = cliente.post("/api/certificados/validar", data={"senha": "errada"},
                     files={"arquivo": ("c.pfx", _pfx(), "application/x-pkcs12")})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("Senha do certificado incorreta")
    r = _contabilidade(cliente, senha="errada")
    assert r.status_code == 422 and "Senha do certificado incorreta" in r.json()["detail"]
    assert cliente.get("/api/contabilidade").json() is None


def test_arquivo_que_nao_e_pfx(cliente):
    r = cliente.post("/api/certificados/validar", data={"senha": "x"},
                     files={"arquivo": ("c.pfx", b"nao sou um certificado", "application/x-pkcs12")})
    assert r.status_code == 422 and "não é um certificado" in r.json()["detail"]


def test_validar_le_metadados_ecnpj_e_ecpf(cliente):
    r = cliente.post("/api/certificados/validar", data={"senha": SENHA},
                     files={"arquivo": ("c.pfx", _pfx(dias=10), "application/x-pkcs12")})
    d = r.json()
    assert r.status_code == 200 and d["tipo"] == "e-CNPJ" and d["titular_doc"] == CONTAB
    assert d["situacao"] == "vence_15" and d["responsavel"] == "RESPONSAVEL TESTE"
    assert "senha" not in r.text.lower()
    r = cliente.post("/api/certificados/validar", data={"senha": SENHA},
                     files={"arquivo": ("c.pfx", criar_pfx("FULANO DE TAL", cpf=CPF), "application/x-pkcs12")})
    assert r.json()["tipo"] == "e-CPF" and r.json()["titular_doc"] == CPF


@pytest.mark.parametrize("dias,esperado", [(40, "ok"), (25, "vence_30"), (12, "vence_15"), (3, "vence_7")])
def test_alertas_de_vencimento(cliente, dias, esperado):
    r = cliente.post("/api/certificados/validar", data={"senha": SENHA},
                     files={"arquivo": ("c.pfx", _pfx(dias=dias), "application/x-pkcs12")})
    assert r.json()["situacao"] == esperado


def test_certificado_vencido_bloqueado(cliente):
    r = _contabilidade(cliente, pfx=_pfx(dias=-1, inicio_dias=-400))
    assert r.status_code == 422 and "vencido" in r.json()["detail"]


# --- Segredos não ficam legíveis -------------------------------------------------

def test_pfx_e_senha_nao_ficam_legiveis_em_disco_nem_em_log(cliente, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    pfx = _pfx()
    r = _contabilidade(cliente, pfx=pfx)
    assert r.status_code == 200, r.text
    assert SENHA not in r.text

    dados = tmp_path / "dados"
    arquivos = [p for p in dados.rglob("*") if p.is_file()]
    assert any(p.name.endswith(".pfx.enc") for p in arquivos)
    trecho_pfx = pfx[100:140]
    for p in arquivos:
        conteudo = p.read_bytes()
        assert SENHA.encode() not in conteudo, p
        assert trecho_pfx not in conteudo, p
    # Nada de senha nos logs (aplicação, uvicorn, httpx...)
    assert SENHA not in caplog.text
    # Erros de validação não ecoam o valor enviado
    r = cliente.post("/api/contabilidade", data={"senha": SENHA})
    assert r.status_code == 422 and SENHA not in r.text


# --- Contabilidade e empresas ------------------------------------------------------

def test_fluxo_completo(cliente, tmp_path):
    assert cliente.get("/api/saude").json()["tem_contabilidade"] is False
    # Empresa antes da contabilidade: recusado
    assert _empresa(cliente).status_code == 409

    r = _contabilidade(cliente)
    assert r.status_code == 200
    contab = r.json()["empresa"]
    assert contab["is_contabilidade"] and contab["acesso"] == "proprio"
    assert contab["busca"]["job_pendente"] is True  # busca inicial agendada

    r = _empresa(cliente, situacao_cadastral="BAIXADA")
    assert r.status_code == 201, r.text
    emp = r.json()["empresa"]
    assert emp["acesso"] == "procuracao" and emp["certificado"]["titular_doc"] == CONTAB
    assert emp["busca"]["situacao"] == "nunca_buscada" and emp["busca"]["job_pendente"]
    assert any("BAIXADA" in a for a in r.json()["avisos"])

    assert _empresa(cliente).status_code == 409                      # duplicado
    assert _empresa(cliente, cnpj="11222333000182").status_code == 422  # DV errado
    assert _empresa(cliente, cnpj=ALFANUM).status_code == 201         # alfanumérico

    lista = cliente.get("/api/empresas").json()
    assert [e["is_contabilidade"] for e in lista][0] is True and len(lista) == 3
    assert len(cliente.get("/api/empresas", params={"q": "114447"}).json()) == 1
    assert cliente.get("/api/empresas", params={"filtro": "procuracao_pendente"}).json() == []

    # Segunda contabilidade com outro CNPJ: recusado
    assert _contabilidade(cliente, pfx=_pfx(cnpj=OUTRA_RAIZ), cnpj=OUTRA_RAIZ).status_code == 409

    # Certificado próprio de outra raiz: aceito com aviso
    r = cliente.put(f"/api/empresas/{emp['id']}/certificado", data={"modo_certificado": "proprio", "senha": SENHA},
                    files={"arquivo": ("o.pfx", _pfx("OUTRA LTDA", cnpj=OUTRA_RAIZ), "application/x-pkcs12")})
    assert r.status_code == 200 and "outra raiz" in r.json()["avisos"][0]
    assert r.json()["empresa"]["modo_certificado"] == "proprio"

    # Voltar para a contabilidade remove o certificado órfão
    r = cliente.put(f"/api/empresas/{emp['id']}/certificado", data={"modo_certificado": "contabilidade"})
    assert r.status_code == 200
    con = sqlite3.connect(tmp_path / "dados" / "contask.db")
    assert con.execute("select count(*) from certificado").fetchone()[0] == 1
    con.close()

    # Edição
    r = cliente.patch(f"/api/empresas/{emp['id']}", json={"apelido": "  Cliente  ", "ativa": False})
    assert r.json()["apelido"] == "Cliente" and r.json()["ativa"] is False
    assert cliente.patch(f"/api/empresas/{contab['id']}", json={"ativa": False}).status_code == 409

    # Exclusão exige o CNPJ digitado; contabilidade não pode ser excluída
    assert cliente.delete(f"/api/empresas/{emp['id']}", params={"confirmacao": "123"}).status_code == 422
    assert cliente.delete(f"/api/empresas/{contab['id']}", params={"confirmacao": CONTAB}).status_code == 409
    assert cliente.delete(f"/api/empresas/{emp['id']}", params={"confirmacao": "11.444.777/0001-61"}).status_code == 204
    assert cliente.get(f"/api/empresas/{emp['id']}").status_code == 404


def test_brasilapi_fora_do_ar_nao_impede_cadastro(cliente, monkeypatch):
    def fora(*_a, **_k):
        raise brasilapi.BrasilApiErro("A BrasilAPI não respondeu. Preencha os dados manualmente.")
    monkeypatch.setattr(brasilapi, "consultar", fora)
    r = cliente.get(f"/api/cnpj/{CLIENTE}")
    assert r.status_code == 200 and r.json()["encontrado"] is False and "manualmente" in r.json()["erro"]
    assert _contabilidade(cliente).status_code == 200
    assert _empresa(cliente).status_code == 201


def test_consulta_cnpj_normaliza_brasilapi(cliente, monkeypatch):
    import httpx

    def resposta(req):
        assert req.url.path.endswith(CLIENTE)
        return httpx.Response(200, json={"razao_social": "CLIENTE TESTE LTDA", "nome_fantasia": "",
                                         "uf": "DF", "municipio": "BRASILIA",
                                         "descricao_situacao_cadastral": "INAPTA"})
    original = brasilapi.consultar
    monkeypatch.setattr(brasilapi, "consultar",
                        lambda c: original(c, cliente=httpx.Client(transport=httpx.MockTransport(resposta))))
    d = cliente.get(f"/api/cnpj/{CLIENTE}").json()
    assert d["encontrado"] and d["municipio"] == "Brasilia" and d["nome_fantasia"] is None
    assert "INAPTA" in d["aviso"]
    assert cliente.get("/api/cnpj/123").status_code == 422
