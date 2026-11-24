"""Prévia da nota (PDF no leiaute do DANFSe, sem valor fiscal): não assina, não numera, não grava, não envia."""
import io

from pypdf import PdfReader

from tests.test_emissor_issnet import TOMADOR_COM_ENDERECO
from tests.test_emissor_motor import _emissao, _pronta, sefin  # noqa: F401


def _texto(pdf: bytes) -> str:
    return " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages)


def test_previa_gera_pdf_sem_tocar_na_sefin(cliente, sefin):
    e, s = _pronta(cliente)
    antes = cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]["proximo_numero"]
    r = cliente.post("/api/emissor/notas/previa", json=_emissao(e, s, valor="1500.00", descricao="Consulta de outubro"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    texto = _texto(r.content)
    assert "PRÉVIA - SEM VALOR FISCAL" in texto and "Prévia, não transmitida" in texto
    assert "Consulta de outubro" in texto and "R$ 1.500,00" in texto
    assert sefin.recebidas == []
    assert cliente.get("/api/emissor/notas").json() == [] or all(
        n["situacao"] != "previa" for n in cliente.get("/api/emissor/notas").json())
    assert cliente.get(f"/api/emissor/empresas/{e['id']}").json()["config"]["proximo_numero"] == antes


def test_previa_nao_optante_e_mesmas_validacoes_da_emissao(cliente, sefin):
    e, s = _pronta(cliente)
    r = cliente.put(f"/api/emissor/empresas/{e['id']}/config", json={
        "op_simples": "1", "regime_tributario": "presumido", "cod_municipio": "3147006"})
    assert r.status_code == 200, r.text
    # a prévia barra o que a emissão barraria, com a mesma mensagem
    r = cliente.post("/api/emissor/notas/previa", json=_emissao(e, s))
    assert r.status_code == 422 and "cClassTrib" in r.json()["detail"]
    s = cliente.post(f"/api/emissor/empresas/{e['id']}/servicos", json={
        "descricao": "Medicina", "ctribnac": "040101", "cnbs": "123012100", "cindop": "100301", "cclasstrib": "000001"}).json()
    r = cliente.post("/api/emissor/notas/previa", json=_emissao(e, s, tomador=TOMADOR_COM_ENDERECO))
    assert r.status_code == 200, r.text
    texto = _texto(r.content)
    assert "Não Optante" in texto and "Paracatu" in texto and "Medicina" in texto
    r = cliente.post("/api/emissor/notas/previa", json={**_emissao(e, s), "descricao": " ", "servico_id": None})
    assert r.status_code == 422 and "serviço" in r.json()["detail"]
    assert sefin.recebidas == []


def test_previa_de_empresa_de_outro_escritorio(cliente, sefin):
    e, s = _pronta(cliente)
    r = cliente.post("/api/emissor/notas/previa", json={**_emissao(e, s), "empresa_id": 99999})
    assert r.status_code == 404
