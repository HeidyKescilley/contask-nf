"""Nota emitida pelo Contask e cancelada fora dele (portal nacional): a situação acompanha os eventos."""
from app.core.config import config
from app.core.db import nova_sessao
from app.jobs.sincronizador import recalcular_status
from app.models import DocumentoDfe, EventoNota, Nota, NotaEmitida
from tests.adn_simulado import evento_xml
from tests.test_emissor_motor import _emissao, _pronta, sefin  # noqa: F401 (fixture)

MOTIVO = "<xMotivo>Valor   lançado errado</xMotivo>"


def _em_producao(nota_id: int) -> str:
    with nova_sessao() as db:
        n = db.get(NotaEmitida, nota_id)
        n.ambiente = 1  # o ADN só traz notas de produção
        db.commit()
        return n.chave


def _evento_adn(empresa_id: int, chave: str, nsu: int = 500) -> None:
    xml = evento_xml(chave, "101101", dh="2026-11-12T15:20:00-03:00").replace(b"</xDesc>", b"</xDesc>" + MOTIVO.encode())
    rel = f"empresas/teste/eventos/{chave}_101101_{nsu}.xml"
    arq = config().dados_dir / rel
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_bytes(xml)
    with nova_sessao() as db:
        if db.query(Nota).filter_by(empresa_id=empresa_id, chave=chave).first() is None:
            db.add(Nota(empresa_id=empresa_id, chave=chave, papel="prestada", status="autorizada"))
        doc = DocumentoDfe(empresa_id=empresa_id, nsu=nsu, chave=chave, tipo_documento="EVENTO", xml_path=rel, processado=True)
        db.add(doc)
        db.flush()
        from datetime import datetime, timezone
        db.add(EventoNota(empresa_id=empresa_id, chave=chave, codigo="101101", descricao="Cancelamento",
                          data_evento=datetime(2026, 11, 12, 18, 20, tzinfo=timezone.utc), nsu=nsu, documento_id=doc.id))
        db.flush()
        recalcular_status(db, empresa_id, {chave})
        db.commit()


def test_cancelamento_no_portal_chega_pela_busca_do_adn(cliente, sefin):
    e, s = _pronta(cliente)
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    chave = _em_producao(n["id"])
    _evento_adn(e["id"], chave)
    out = cliente.get(f"/api/emissor/notas/{n['id']}").json()
    assert out["situacao"] == "cancelada"
    assert out["motivo_cancelamento"] == "Valor lançado errado"
    assert out["cancelado_em"].startswith("2026-11-12")
    assert cliente.get(f"/api/emissor/notas/{n['id']}/xml", params={"tipo": "cancelamento"}).status_code == 200
    # já cancelada: o Contask não tenta cancelar de novo
    r = cliente.post(f"/api/emissor/notas/{n['id']}/cancelar", json={"motivo": "1", "justificativa": "Valor informado errado na nota"})
    assert r.status_code == 409 and sefin.eventos == 0


def test_nota_ja_cancelada_no_adn_e_corrigida_ao_listar(cliente, sefin):
    """Caso visto em produção: o ADN já tinha o evento, mas o emissor continuava mostrando autorizada."""
    e, s = _pronta(cliente)
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    chave = _em_producao(n["id"])
    with nova_sessao() as db:
        db.add(Nota(empresa_id=e["id"], chave=chave, papel="prestada", status="cancelada"))
        db.add(EventoNota(empresa_id=e["id"], chave=chave, codigo="101101", nsu=900))
        db.commit()
    lista = cliente.get("/api/emissor/notas", params={"empresa_id": e["id"]}).json()
    assert [x["situacao"] for x in lista] == ["cancelada"]
    assert "fora do Contask" in lista[0]["motivo_cancelamento"]


def test_verificar_situacao_consulta_a_sefin(cliente, sefin):
    e, s = _pronta(cliente)
    n = cliente.post("/api/emissor/notas", json=_emissao(e, s)).json()
    url = f"/api/emissor/notas/{n['id']}/verificar-situacao"
    r = cliente.post(url).json()
    assert r["nota"]["situacao"] == "autorizada" and "continua autorizada" in r["mensagem"]

    sefin.eventos_fora.add((n["chave"], "101101"))
    r = cliente.post(url).json()
    assert r["nota"]["situacao"] == "cancelada" and "cancelada fora do Contask" in r["mensagem"]
    assert cliente.get(f"/api/emissor/notas/{n['id']}/xml", params={"tipo": "cancelamento"}).status_code == 200
    assert sefin.eventos == 0  # só leitura: nenhum evento registrado pelo Contask
    assert "Só as notas autorizadas" in cliente.post(url).json()["mensagem"]
