"""DANFSe pelo gerador oficial da Receita (contêiner interno), com o gerador próprio como reserva."""
import httpx
import pytest

from app.core import config as cfgmod
from app.fiscal import danfse_receita
from tests.test_notas import com_notas, empresa  # noqa: F401

PDF_RECEITA = b"%PDF-1.7 gerado pela Receita"


@pytest.fixture()
def receita(monkeypatch):
    """Liga o gerador da Receita e grava as chamadas feitas a ele."""
    monkeypatch.setenv("CONTASK_DANFSE_URL", "http://contask-danfse:8080/")
    cfgmod.config.cache_clear()
    chamadas, resposta = [], {"r": lambda: httpx.Response(200, content=PDF_RECEITA)}

    def post(url, *, content, params, headers, timeout):
        chamadas.append({"url": url, "params": params, "xml": content, "tipo": headers["Content-Type"]})
        r = resposta["r"]()
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(danfse_receita.httpx, "post", post)
    yield chamadas, resposta
    cfgmod.config.cache_clear()


def test_sem_url_usa_o_gerador_proprio(cliente, com_notas):
    _, ids, _ = com_notas
    assert not danfse_receita.receita_ativa()
    r = cliente.get(f"/api/notas/{ids[1]}/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.content != PDF_RECEITA


def test_usa_o_gerador_da_receita_e_guarda(cliente, com_notas, receita, tmp_path):
    _, ids, _ = com_notas
    chamadas, _ = receita
    r = cliente.get(f"/api/notas/{ids[1]}/pdf")
    assert r.status_code == 200 and r.content == PDF_RECEITA
    assert chamadas[0]["url"] == "http://contask-danfse:8080/api/danfse"
    assert chamadas[0]["params"] == {"stc": "0", "canhoto": "false"}
    assert chamadas[0]["xml"].lstrip().startswith(b"<") and chamadas[0]["tipo"] == "application/xml"
    assert [p.name.endswith(".receita.pdf") for p in (tmp_path / "dados").rglob("*.pdf")] == [True]
    # guardado: a segunda abertura não chama de novo
    assert cliente.get(f"/api/notas/{ids[1]}/pdf").content == PDF_RECEITA and len(chamadas) == 1
    # cancelada: stc=2 (a Receita imprime a marca d'água)
    cliente.get(f"/api/notas/{ids[2]}/pdf")
    assert chamadas[-1]["params"]["stc"] == "2"


def test_pdf_antigo_do_gerador_proprio_nao_vale_com_a_receita(cliente, com_notas, monkeypatch, tmp_path):
    _, ids, _ = com_notas
    antigo = cliente.get(f"/api/notas/{ids[1]}/pdf").content  # guardado pelo gerador próprio
    monkeypatch.setenv("CONTASK_DANFSE_URL", "http://contask-danfse:8080")
    cfgmod.config.cache_clear()
    monkeypatch.setattr(danfse_receita.httpx, "post", lambda *a, **k: httpx.Response(200, content=PDF_RECEITA))
    assert antigo != PDF_RECEITA and cliente.get(f"/api/notas/{ids[1]}/pdf").content == PDF_RECEITA


@pytest.mark.parametrize("falha", [
    lambda: httpx.ConnectError("recusada"),
    lambda: httpx.ReadTimeout("demorou"),
    lambda: httpx.Response(400, json={"erro": "XML inválido"}),
    lambda: httpx.Response(200, content=b"<html>proxy</html>"),
])
def test_falha_da_receita_cai_no_gerador_proprio(cliente, com_notas, receita, falha, tmp_path):
    _, ids, _ = com_notas
    chamadas, resposta = receita
    resposta["r"] = falha
    r = cliente.get(f"/api/notas/{ids[1]}/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.content != PDF_RECEITA
    # o próprio não fica guardado como se fosse o oficial: a próxima abertura tenta a Receita de novo
    assert not list((tmp_path / "dados").rglob("*.receita.pdf"))
    resposta["r"] = lambda: httpx.Response(200, content=PDF_RECEITA)
    assert cliente.get(f"/api/notas/{ids[1]}/pdf").content == PDF_RECEITA and len(chamadas) == 2


def test_marca_dagua_vira_stc():
    assert danfse_receita.STC == {None: "0", "SUBSTITUÍDA": "1", "CANCELADA": "2"}
