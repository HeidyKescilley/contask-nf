"""Lista de notas, busca por valor em formato brasileiro, desempenho, XML e DANFSe."""
import io
import random
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import insert

from app.api.notas import interpretar_valor
from app.core.db import engine, nova_sessao
from app.fiscal.danfse import gerar_danfse
from app.jobs.sincronizador import Contexto, executar_job
from app.models import BuscaJob, Nota
from tests.adn_simulado import ADNSimulado, chave_fake, nfse_xml
from tests.certs import criar_pfx, dv_cnpj

SENHA = "S3nh@-Teste!"
CONTAB = dv_cnpj("112223330001")
EMP = dv_cnpj("114447770001")
OUTRA = "33000167000101"


@pytest.fixture()
def empresa(cliente):
    cliente.post("/api/contabilidade", data={"cnpj": CONTAB, "razao_social": "Contab", "senha": SENHA},
                 files={"arquivo": ("c.pfx", criar_pfx("CONTAB", cnpj=CONTAB), "application/x-pkcs12")})
    r = cliente.post("/api/empresas", data={"cnpj": EMP, "razao_social": "Empresa", "modo_certificado": "contabilidade"})
    return r.json()["empresa"]["id"]


def _sincronizar(adn, empresa_id):
    with nova_sessao() as db:
        jid = db.query(BuscaJob.id).filter(BuscaJob.empresa_id == empresa_id, BuscaJob.status == "fila").scalar()
    executar_job(jid, nova_sessao, Contexto(fabrica=adn.fabrica, pausa=0, dormir=lambda s: None, publicar=lambda e: None))


@pytest.fixture()
def com_notas(empresa):
    """Notas reais do fluxo (ADN simulado): prestadas, tomadas, canceladas, valores variados."""
    adn = ADNSimulado()
    c = lambda i: chave_fake(i, EMP)  # noqa: E731
    adn.adicionar(EMP, "NFSE", c(1), nfse_xml(c(1), prest=EMP, toma=OUTRA, valor="1234.56", numero=101, dh="2026-10-05T10:00:00-03:00"))
    adn.adicionar(EMP, "NFSE", c(2), nfse_xml(c(2), prest=EMP, toma=OUTRA, valor="500.00", numero=102, dh="2026-10-20T23:30:00-03:00"))
    adn.adicionar(EMP, "NFSE", c(3), nfse_xml(c(3), prest=OUTRA, toma=EMP, valor="89.90", numero=7, dh="2026-09-30T08:00:00-03:00",
                                             nome_emit="FORNECEDOR ALFA LTDA"))
    adn.adicionar(EMP, "NFSE", c(4), nfse_xml(c(4), prest=EMP, toma=None, valor="1234.56", numero=104, dh="2026-11-01T09:00:00-03:00"))
    adn.adicionar_evento(EMP, c(2), "101101")
    _sincronizar(adn, empresa)
    with nova_sessao() as db:
        ids = {n.chave: n.id for n in db.query(Nota).filter(Nota.empresa_id == empresa)}
    return empresa, {i: ids[c(i)] for i in range(1, 5)}, c


def _lista(cliente, empresa_id, **params):
    r = cliente.get(f"/api/empresas/{empresa_id}/notas", params=params)
    assert r.status_code == 200, r.text
    return r.json()


# --- Valor em formato brasileiro -------------------------------------------------------------------

@pytest.mark.parametrize("entrada,esperado", [
    ("1.234,56", "1234.56"), ("1234,56", "1234.56"), ("R$ 1.234,56", "1234.56"), ("1234.56", "1234.56"),
    ("1234", "1234.00"), ("1.234", "1234.00"), ("0,5", "0.50"), ("89,9", "89.90"),
    ("abc", None), ("1,2,3", None), ("12.34.56", None), ("", None),
])
def test_interpretar_valor(entrada, esperado):
    v = interpretar_valor(entrada)
    assert (str(v) if v is not None else None) == esperado


def test_busca_por_valor_numero_chave_e_nome(cliente, com_notas):
    emp, ids, c = com_notas
    assert {n["id"] for n in _lista(cliente, emp, q="1.234,56")["itens"]} == {ids[1], ids[4]}
    assert {n["id"] for n in _lista(cliente, emp, q="R$ 1234,56", papel="prestada")["itens"]} == {ids[1], ids[4]}
    assert [n["id"] for n in _lista(cliente, emp, q="89,90")["itens"]] == [ids[3]]
    assert [n["id"] for n in _lista(cliente, emp, q="102")["itens"]] == [ids[2]]
    assert [n["id"] for n in _lista(cliente, emp, q=c(3))["itens"]] == [ids[3]]
    assert [n["id"] for n in _lista(cliente, emp, q="alfa")["itens"]] == [ids[3]]
    assert _lista(cliente, emp, q="nada-a-ver")["total"] == 0


def test_filtros_papel_status_periodo(cliente, com_notas):
    emp, ids, _ = com_notas
    pres = _lista(cliente, emp, papel="prestada")
    assert pres["total"] == 3 and _lista(cliente, emp, papel="tomada")["total"] == 1
    assert pres["totais"] == {"valor_autorizado": 2469.12, "autorizadas": 2, "canceladas": 1, "rejeitadas": 0}
    assert [n["id"] for n in _lista(cliente, emp, status="cancelada")["itens"]] == [ids[2]]
    # Período por emissão, incluindo o último dia inteiro (nota às 23:30)
    out = _lista(cliente, emp, inicio="2026-10-01", fim="2026-10-20")
    assert {n["id"] for n in out["itens"]} == {ids[1], ids[2]}
    out = _lista(cliente, emp, inicio="2026-10-01", fim="2026-10-31", campo_data="competencia")
    assert {n["id"] for n in out["itens"]} == {ids[1], ids[2]}
    # Ordem e paginação
    assert [n["id"] for n in _lista(cliente, emp, ordem="valor")["itens"]][0] == ids[3]
    p1 = _lista(cliente, emp, limite=2, page=1)
    p2 = _lista(cliente, emp, limite=2, page=2)
    assert p1["paginas"] == 2 and len({n["id"] for n in p1["itens"] + p2["itens"]}) == 4
    assert cliente.get(f"/api/empresas/{emp}/notas", params={"inicio": "2026-13-01"}).status_code == 422
    assert cliente.get(f"/api/empresas/{emp}/notas", params={"inicio": "2026-10-10", "fim": "2026-10-01"}).status_code == 422


def test_detalhe_com_eventos_e_xml(cliente, com_notas):
    emp, ids, c = com_notas
    d = cliente.get(f"/api/notas/{ids[2]}").json()
    assert d["status"] == "cancelada" and d["eventos"][0]["codigo"] == "101101" and d["eventos"][0]["conhecido"]
    r = cliente.get(f"/api/notas/{ids[1]}/xml")
    assert r.status_code == 200 and r.content.startswith(b"<?xml") and c(1) in r.headers["content-disposition"]
    assert cliente.get("/api/notas/999999").status_code == 404


def _texto_pdf(conteudo: bytes) -> tuple[int, str]:
    leitor = PdfReader(io.BytesIO(conteudo))
    return len(leitor.pages), " ".join(p.extract_text() for p in leitor.pages)


def test_danfse_gerado_guardado_e_com_marca_dagua(cliente, com_notas, tmp_path):
    emp, ids, c = com_notas
    r = cliente.get(f"/api/notas/{ids[1]}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert r.headers["content-disposition"].startswith("inline")
    paginas, texto = _texto_pdf(r.content)
    assert paginas == 1
    for esperado in ("DANFSe v2.0", c(1), "101", "R$ 1.234,56", "PRESTADOR FICTICIO LTDA", "TOMADOR FICTICIO",
                     "O DESTINATÁRIO É O PRÓPRIO TOMADOR/ADQUIRENTE DA OPERAÇÃO",
                     "INTERMEDIÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e", "Totais Aproximados dos Tributos"):
        assert esperado in texto, esperado
    assert "CANCELADA" not in texto
    pdfs = list((tmp_path / "dados").rglob("*.pdf"))
    assert len(pdfs) == 1  # guardado para os próximos acessos
    assert cliente.get(f"/api/notas/{ids[1]}/pdf", params={"download": 1}).headers["content-disposition"].startswith("attachment")

    _, texto = _texto_pdf(cliente.get(f"/api/notas/{ids[2]}/pdf").content)
    assert "CANCELADA" in texto
    _, texto = _texto_pdf(cliente.get(f"/api/notas/{ids[4]}/pdf").content)
    assert "TOMADOR/ADQUIRENTE DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e" in texto


def test_danfse_nao_imprime_o_que_nao_esta_no_xml():
    """Campos ausentes viram "-" (nota 12); nenhum valor inventado."""
    ch = chave_fake(1, EMP)
    xml = nfse_xml(ch, prest=EMP, toma=OUTRA, valor="10.00")
    _, texto = _texto_pdf(gerar_danfse(xml))
    assert "R$ 10,00" in texto and "Federais: -; Estaduais: -; Municipais: -" in texto
    assert "Código da NBS" in texto and "IRRF" in texto
    # Marca de substituição
    _, texto = _texto_pdf(gerar_danfse(xml, marca_dagua="SUBSTITUÍDA"))
    assert "SUBSTITUÍDA" in texto


# --- Desempenho: 12 mil notas ----------------------------------------------------------------------

def test_12_mil_notas_filtrar_e_paginar_em_menos_de_300ms(cliente, empresa):
    rnd = random.Random(42)
    base = datetime(2025, 1, 1, 8, 0)
    linhas = []
    for i in range(12_000):
        dt = base + timedelta(minutes=rnd.randint(0, 60 * 24 * 600))
        linhas.append({
            "empresa_id": empresa, "chave": chave_fake(i + 1, EMP), "papel": "prestada" if i % 4 else "tomada",
            "numero": str(i + 1), "serie": "1", "emitente_doc": EMP, "emitente_nome": f"Cliente {i % 300}",
            "tomador_doc": OUTRA, "tomador_nome": f"Tomador {i % 500}",
            "valor_servico": Decimal(rnd.randint(1000, 500000)) / 100, "valor_liquido": Decimal("1.00"),
            "data_emissao": dt, "competencia": dt.date(), "status": "cancelada" if i % 37 == 0 else "autorizada",
        })
    linhas[777]["valor_servico"] = Decimal("1234.56")
    with engine().begin() as con:
        con.execute(insert(Nota), linhas)

    consultas = [
        {"papel": "prestada"},
        {"papel": "prestada", "page": 120},
        {"papel": "tomada", "status": "cancelada"},
        {"papel": "prestada", "inicio": "2025-03-01", "fim": "2025-03-31"},
        {"papel": "prestada", "inicio": "2025-01-01", "fim": "2026-12-31", "campo_data": "competencia", "ordem": "valor_desc"},
        {"papel": "prestada", "q": "1.234,56"},
        {"papel": "prestada", "q": "Tomador 42"},
        {"papel": "prestada", "q": "9876"},
    ]
    _lista(cliente, empresa, **consultas[0])  # aquece
    tempos = []
    for p in consultas:
        t = time.perf_counter()
        d = _lista(cliente, empresa, **p)
        tempos.append((time.perf_counter() - t) * 1000)
        assert d["total"] >= 0
    assert _lista(cliente, empresa, q="1.234,56")["total"] >= 1
    print("tempos (ms):", [round(x) for x in tempos])
    assert max(tempos) < 300, [f"{x:.0f}ms" for x in tempos]
