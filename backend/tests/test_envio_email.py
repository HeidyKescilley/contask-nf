"""Envio da NFS-e por e-mail: manual (emitida pelo Contask ou vinda do ADN) e automático na recorrente."""
from datetime import date

import pytest

from tests.test_emissor_diferenciais import _recorrente
from tests.test_emissor_motor import _emissao, _pronta, sefin  # noqa: F401 (fixture)


@pytest.fixture
def caixa(monkeypatch):
    """Caixa de e-mail simulada: guarda o que seria enviado; `falhar` simula o servidor recusando."""
    from app.core import email

    class Caixa:
        enviados: list = []
        falhar = False
        configurada = True

    def enviar(para, assunto, texto, html=None, *, anexos=None, responder_para=None):
        if Caixa.falhar:
            raise email.ErroEmail("Falha ao enviar o e-mail (SMTPServerDisconnected).")
        Caixa.enviados.append({"para": para, "assunto": assunto, "texto": texto, "anexos": anexos,
                               "responder_para": responder_para})

    Caixa.enviados = []
    monkeypatch.setattr(email, "enviar", enviar)
    monkeypatch.setattr(email, "configurado", lambda: Caixa.configurada)
    return Caixa


def _emitida(cliente, **tomador):
    e, s = _pronta(cliente)
    corpo = _emissao(e, s)
    corpo["tomador"] = {**corpo["tomador"], **tomador}
    r = cliente.post("/api/emissor/notas", json=corpo)
    assert r.status_code == 201 and r.json()["situacao"] == "autorizada", r.text
    return e, s, r.json()


def test_envia_nota_emitida_com_pdf_e_xml(cliente, sefin, caixa):
    _, _, n = _emitida(cliente, email="financeiro@tomador.com.br")
    info = cliente.get(f"/api/emissor/notas/{n['id']}/email").json()
    assert info["sugestao"] == "financeiro@tomador.com.br" and info["configurado"] and info["envios"] == []

    r = cliente.post(f"/api/emissor/notas/{n['id']}/email",
                     json={"para": "Financeiro@Tomador.com.br; contato@tomador.com.br", "mensagem": "Boleto em seguida."})
    assert r.status_code == 200, r.text
    assert r.json()["situacao"] == "enviado" and r.json()["para"] == "financeiro@tomador.com.br, contato@tomador.com.br"
    m = caixa.enviados[0]
    assert m["para"] == ["financeiro@tomador.com.br", "contato@tomador.com.br"]
    assert "NFS-e nº 42" in m["assunto"] and "Boleto em seguida." in m["texto"] and n["chave"] in m["texto"]
    nomes = [a[0] for a in m["anexos"]]
    assert nomes[0].endswith(".pdf") and nomes[1].endswith(".xml")
    assert m["anexos"][0][1][:4] == b"%PDF" and b"<NFSe" in m["anexos"][1][1]
    assert m["responder_para"] == "teste@contask.local"  # resposta vai para quem enviou, não para a caixa do sistema
    assert len(cliente.get(f"/api/emissor/notas/{n['id']}/email").json()["envios"]) == 1


def test_destinatarios_validados_e_erros_registrados(cliente, sefin, caixa):
    _, _, n = _emitida(cliente)
    url = f"/api/emissor/notas/{n['id']}/email"
    assert cliente.get(url).json()["sugestao"] is None
    assert cliente.post(url, json={"para": ""}).status_code == 422
    r = cliente.post(url, json={"para": "sem-arroba"})
    assert r.status_code == 422 and "inválido" in r.json()["detail"]
    r = cliente.post(url, json={"para": ",".join(f"p{i}@x.com" for i in range(6))})
    assert r.status_code == 422 and "No máximo 5" in r.json()["detail"]
    caixa.falhar = True
    r = cliente.post(url, json={"para": "a@x.com"})
    assert r.status_code == 502
    envios = cliente.get(url).json()["envios"]
    assert envios[0]["situacao"] == "erro" and "SMTP" in envios[0]["erro"]
    caixa.falhar, caixa.configurada = False, False
    r = cliente.post(url, json={"para": "a@x.com"})
    assert r.status_code == 503 and "não está configurado" in r.json()["detail"]
    assert caixa.enviados == []


def test_envia_nota_que_veio_do_adn(cliente, sefin, caixa):
    """Nota que não foi emitida pelo Contask (chegou pela busca no ADN) também pode ser enviada."""
    from app.core.db import nova_sessao
    from app.models import Nota, NotaEmitida
    e, _, n = _emitida(cliente, email="fin@tomador.com.br")
    with nova_sessao() as db:
        em = db.get(NotaEmitida, n["id"])
        nota = Nota(empresa_id=e["id"], chave=em.chave, papel="prestada", numero="42", emitente_nome="Empresa Teste",
                    tomador_nome="Tomador Teste Ltda", status="autorizada", xml_path=em.xml_nfse_path)
        db.add(nota)
        db.commit()
        nid = nota.id
    assert cliente.get(f"/api/notas/{nid}/email").json()["envios"] == []
    r = cliente.post(f"/api/notas/{nid}/email", json={"para": "fin@tomador.com.br"})
    assert r.status_code == 200, r.text
    assert caixa.enviados[0]["anexos"][0][1][:4] == b"%PDF"
    # O histórico é da nota (pela chave), venha ela da emissão ou do ADN
    assert len(cliente.get(f"/api/emissor/notas/{n['id']}/email").json()["envios"]) == 1


def test_recorrente_envia_assim_que_transmite(cliente, sefin, caixa):
    from app.core.db import nova_sessao
    from app.emissor import recorrencia
    from app.models import NotaEnvio, NotaRecorrente
    e, s = _pronta(cliente)
    # Sem destinatário e sem e-mail do tomador: não salva
    r = cliente.post("/api/emissor/recorrentes", json=_recorrente(e, s, email_enviar=True))
    assert r.status_code == 422 and "destinatário" in r.json()["detail"]
    corpo = _recorrente(e, s, email_enviar=True, email_mensagem="Honorários do mês.")
    corpo["dados"]["tomador"]["email"] = "fin@tomador.com.br"
    r = cliente.post("/api/emissor/recorrentes", json=corpo)
    assert r.status_code == 201, r.text
    assert r.json()["email_enviar"] and r.json()["email_para"] is None and r.json()["email_tomador"] == "fin@tomador.com.br"
    rid = r.json()["id"]
    with nova_sessao() as db:
        db.get(NotaRecorrente, rid).proxima_em = date(2026, 11, 5)
        db.commit()
        criadas = recorrencia.executar_pendentes(db, date(2026, 11, 5))
        assert len(criadas) == 1
        env = db.query(NotaEnvio).one()
        assert env.automatico and env.recorrente_id == rid and env.situacao == "enviado"
    assert caixa.enviados[0]["para"] == ["fin@tomador.com.br"] and "Honorários do mês." in caixa.enviados[0]["texto"]


def test_recorrente_tenta_de_novo_e_avisa_se_o_email_falhar(cliente, sefin, caixa):
    from app.core.db import nova_sessao
    from app.emissor import recorrencia
    from app.models import NotaEmitida, NotaRecorrente
    e, s = _pronta(cliente)
    rid = cliente.post("/api/emissor/recorrentes",
                       json=_recorrente(e, s, email_enviar=True, email_para="fin@tomador.com.br")).json()["id"]
    caixa.falhar = True
    with nova_sessao() as db:
        db.get(NotaRecorrente, rid).proxima_em = date(2026, 11, 5)
        db.commit()
        nid = recorrencia.executar_pendentes(db, date(2026, 11, 5))[0]
        # A nota saiu; o e-mail fica pendente para a próxima verificação
        assert db.get(NotaEmitida, nid).email_pendente["tentativas"] == 2  # na hora e na varredura do fim
        assert db.get(NotaRecorrente, rid).ultimo_erro is None
        recorrencia.executar_pendentes(db, date(2026, 11, 5))
        db.expire_all()
        assert db.get(NotaEmitida, nid).email_pendente is None
        assert "e-mail não foi enviado" in db.get(NotaRecorrente, rid).ultimo_erro
    assert caixa.enviados == []


def test_sugestao_vem_do_email_do_tomador_no_xml():
    from app.fiscal.parser import email_tomador
    from tests.adn_simulado import nfse_xml
    xml = nfse_xml("5" * 50, prest="11222333000181", toma="44555666000199")
    assert email_tomador(xml) is None
    xml = xml.replace(b"</xNome></toma>", b"</xNome><email>fin@tomador.com.br</email></toma>") if isinstance(xml, bytes) \
        else xml.replace("</xNome></toma>", "</xNome><email>fin@tomador.com.br</email></toma>").encode()
    assert email_tomador(xml) == "fin@tomador.com.br"
    assert email_tomador(b"lixo") is None
