"""Exportação: o ZIP bate com a prévia e com o relatório; "Autorizadas" não leva cancelada nem rejeitada."""
import io
import zipfile

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from app.core.db import nova_sessao
from app.jobs.exportador import Exportador
from app.jobs.sincronizador import Contexto, executar_job
from app.models import BuscaJob, Exportacao, Nota
from tests.adn_simulado import ADNSimulado, chave_fake, evento_xml, nfse_xml
from tests.certs import criar_pfx, dv_cnpj

SENHA = "S3nh@-Teste!"
CONTAB = dv_cnpj("112223330001")
EMP = dv_cnpj("114447770001")
OUTRA = "33000167000101"


@pytest.fixture()
def emp(cliente):
    cliente.post("/api/contabilidade", data={"cnpj": CONTAB, "razao_social": "Contab", "senha": SENHA},
                 files={"arquivo": ("c.pfx", criar_pfx("CONTAB", cnpj=CONTAB), "application/x-pkcs12")})
    eid = cliente.post("/api/empresas", data={"cnpj": EMP, "razao_social": "Empresa Ação & Cia", "apelido": "Ação",
                                              "modo_certificado": "contabilidade"}).json()["empresa"]["id"]
    adn = ADNSimulado()
    seq = iter(range(1, 10_000))
    chaves = {}

    def nota(nome, prest, toma, valor, dh):
        ch = chave_fake(next(seq), EMP)
        adn.adicionar(EMP, "NFSE", ch, nfse_xml(ch, prest=prest, toma=toma, valor=valor, dh=dh))
        chaves[nome] = ch

    for i in range(30):
        nota(f"p{i}", EMP, OUTRA, f"{100 + i}.00", f"2026-10-{1 + i % 28:02d}T10:00:00-03:00")
    for i in range(12):
        nota(f"t{i}", OUTRA, EMP, f"{50 + i}.00", f"2026-10-{1 + i:02d}T10:00:00-03:00")
    nota("fora", EMP, OUTRA, "999.00", "2026-09-15T10:00:00-03:00")
    for nome, cod in (("p3", "101101"), ("p7", "105102"), ("t2", "101101"), ("p9", "203206"), ("p11", "101103")):
        adn.adicionar(EMP, "EVENTO", chaves[nome], evento_xml(chaves[nome], cod, dh="2026-10-29T10:00:00-03:00"), "X")
    with nova_sessao() as db:
        jid = db.query(BuscaJob.id).filter(BuscaJob.empresa_id == eid, BuscaJob.status == "fila").scalar()
    executar_job(jid, nova_sessao, Contexto(fabrica=adn.fabrica, pausa=0, dormir=lambda s: None, publicar=lambda e: None))
    return eid, chaves


OUTUBRO = {"inicio": "2026-10-01", "fim": "2026-10-31", "campo_data": "competencia"}


def _exportar(cliente, eid, **filtros):
    previa = cliente.post(f"/api/empresas/{eid}/exportacoes/previa", json=filtros)
    assert previa.status_code == 200, previa.text
    r = cliente.post(f"/api/empresas/{eid}/exportacoes", json=filtros)
    assert r.status_code == 201, r.text
    x = r.json()
    assert x["status"] == "concluido", x
    z = cliente.get(f"/api/exportacoes/{x['id']}/arquivo")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    return previa.json(), x, z, zipfile.ZipFile(io.BytesIO(z.content))


def _status_por_chave(eid):
    with nova_sessao() as db:
        return {n.chave: n.status for n in db.query(Nota).filter(Nota.empresa_id == eid)}


def test_zip_bate_com_previa_e_relatorio(cliente, emp):
    eid, chaves = emp
    previa, x, z, zf = _exportar(cliente, eid, tipo="ambos", status="todas", incluir_eventos=True, **OUTUBRO)
    nomes = zf.namelist()
    xml_notas = [n for n in nomes if n.endswith(".xml") and "/xml/" in n]
    xml_eventos = [n for n in nomes if n.startswith("eventos/")]
    assert previa["total"] == 42 and previa["prestadas"] == 30 and previa["tomadas"] == 12
    assert len(xml_notas) == previa["total"] and len(xml_eventos) == previa["eventos"] == 5
    assert previa["arquivos_xml"] == len(xml_notas) + len(xml_eventos)
    assert len([n for n in xml_notas if n.startswith("prestados/xml/")]) == 30
    assert len([n for n in xml_notas if n.startswith("tomados/xml/")]) == 12
    assert chaves["fora"] + ".xml" not in " ".join(nomes)
    wb = load_workbook(io.BytesIO(zf.read("relatorio.xlsx")))
    linhas = list(wb["Notas"].iter_rows(min_row=2, values_only=True))
    assert len(linhas) == previa["total"] == x["total_notas"]
    assert {l[3] for l in linhas} == {n.split("/")[-1][:-4] for n in xml_notas}
    resumo = {r[0]: r[1] for r in wb["Resumo"].iter_rows(values_only=True) if r and r[0]}
    assert resumo["Total"] == 42 and resumo["Arquivos XML no ZIP"] == 47
    assert resumo["Cancelada"] == 3 and resumo["Rejeitada"] == 1 and resumo["Autorizada"] == 38
    assert "Gerado em" in str(wb["Resumo"]["A3"].value)
    assert wb["Eventos"].max_row == 6
    # Nome do arquivo e histórico
    assert 'filename="Contask_NF_Acao_2026-10-01_a_2026-10-31.zip"' in z.headers["content-disposition"]
    hist = cliente.get(f"/api/empresas/{eid}/exportacoes").json()
    assert hist[0]["id"] == x["id"] and hist[0]["disponivel"] is True


def test_autorizadas_nao_leva_cancelada_nem_rejeitada(cliente, emp):
    eid, chaves = emp
    previa, _, _, zf = _exportar(cliente, eid, tipo="ambos", status="autorizada", **OUTUBRO)
    status = _status_por_chave(eid)
    no_zip = [n.split("/")[-1][:-4] for n in zf.namelist() if "/xml/" in n]
    assert len(no_zip) == previa["total"] == 38
    assert all(status[c] == "autorizada" for c in no_zip)
    for nome in ("p3", "p7", "t2", "p9"):
        assert chaves[nome] not in no_zip
    assert chaves["p11"] in no_zip  # só solicitação de análise fiscal: continua autorizada
    linhas = list(load_workbook(io.BytesIO(zf.read("relatorio.xlsx")))["Notas"].iter_rows(min_row=2, values_only=True))
    assert {l[13] for l in linhas} == {"Autorizada"}
    assert previa["por_status"]["cancelada"]["quantidade"] == 0 and previa["por_status"]["rejeitada"]["quantidade"] == 0


def test_so_prestados_e_relatorio_pdf(cliente, emp):
    eid, _ = emp
    previa, _, _, zf = _exportar(cliente, eid, tipo="prestados", status="cancelada", relatorio="pdf", **OUTUBRO)
    nomes = zf.namelist()
    assert "relatorio.pdf" in nomes and "relatorio.xlsx" not in nomes
    assert not any(n.startswith("tomados/") for n in nomes)
    assert len([n for n in nomes if n.endswith(".xml")]) == previa["total"] == 2
    texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(zf.read("relatorio.pdf"))).pages)
    assert "Relatório de NFS-e" in texto and "Arquivos XML no ZIP" in texto and "Canceladas" in texto


def test_so_relatorio_sem_xml(cliente, emp):
    eid, _ = emp
    previa, _, _, zf = _exportar(cliente, eid, tipo="tomados", status="todas", incluir_xml=False, **OUTUBRO)
    assert previa["arquivos_xml"] == 0 and zf.namelist() == ["relatorio.xlsx"]


def test_xml_ausente_aparece_no_relatorio(cliente, emp, tmp_path):
    eid, chaves = emp
    alvo = next((tmp_path / "dados").rglob(f"{chaves['p0']}.xml"))
    alvo.unlink()
    previa, x, _, zf = _exportar(cliente, eid, tipo="prestados", status="todas", **OUTUBRO)
    assert len([n for n in zf.namelist() if "/xml/" in n]) == previa["total"] - 1
    assert "1 XML(s) não encontrado(s)" in x["erro"]
    resumo = [r for r in load_workbook(io.BytesIO(zf.read("relatorio.xlsx")))["Resumo"].iter_rows(values_only=True)]
    assert any(r[1] == chaves["p0"] for r in resumo if r and len(r) > 1)


def test_validacoes(cliente, emp):
    eid, _ = emp
    r = cliente.post(f"/api/empresas/{eid}/exportacoes/previa", json={"inicio": "2026-10-10", "fim": "2026-10-01"})
    assert r.status_code == 422 and "data inicial" in r.json()["detail"]
    r = cliente.post(f"/api/empresas/{eid}/exportacoes", json={"inicio": "2030-01-01", "fim": "2030-01-31"})
    assert r.status_code == 422 and "Nenhuma nota" in r.json()["detail"]
    assert cliente.post(f"/api/empresas/{eid}/exportacoes/previa", json={"tipo": "x"}).status_code == 422
    assert cliente.get("/api/exportacoes/999/arquivo").status_code == 404


def test_geracao_em_segundo_plano(cliente, emp):
    eid, _ = emp
    with nova_sessao() as db:
        x = Exportacao(empresa_id=eid, filtros={"tipo": "ambos", "status": "autorizada", **OUTUBRO}, status="fila")
        db.add(x); db.commit(); xid = x.id
    ex = Exportador(nova_sessao)
    ex.enfileirar(xid).result(timeout=30)
    ex.parar()
    with nova_sessao() as db:
        x = db.get(Exportacao, xid)
        assert x.status == "concluido" and x.total_notas == 38
    assert cliente.get(f"/api/exportacoes/{xid}/arquivo").status_code == 200


# --- Todas as empresas num único ZIP ------------------------------------------------------------

def test_todas_as_empresas_num_unico_zip(cliente, emp):
    eid, _ = emp
    B, C, INATIVA = dv_cnpj("223334440001"), dv_cnpj("556667770001"), dv_cnpj("667778880001")
    ids = {}
    for cnpj, nome in ((B, "EMPRESA B: SERVIÇOS/LTDA."), (C, "EMPRESA C SEM NOTAS"), (INATIVA, "EMPRESA INATIVA")):
        ids[cnpj] = cliente.post("/api/empresas", data={"cnpj": cnpj, "razao_social": nome, "modo_certificado": "contabilidade"}).json()["empresa"]["id"]
    adn = ADNSimulado()
    for i in range(1, 8):
        ch = chave_fake(i, B)
        adn.adicionar(B, "NFSE", ch, nfse_xml(ch, prest=B, toma=OUTRA, valor="10.00", dh=f"2026-10-{i:02d}T10:00:00-03:00"))
    for cnpj in (B, INATIVA):
        with nova_sessao() as db:
            jid = db.query(BuscaJob.id).filter(BuscaJob.empresa_id == ids[cnpj], BuscaJob.status == "fila").scalar()
        executar_job(jid, nova_sessao, Contexto(fabrica=adn.fabrica, pausa=0, dormir=lambda s: None, publicar=lambda e: None))
    cliente.patch(f"/api/empresas/{ids[INATIVA]}", json={"ativa": False})

    previa, x, z, zf = _exportar(cliente, eid, escopo="todas", tipo="ambos", status="autorizada", **OUTUBRO)
    assert previa["total"] == 38 + 7 and previa["empresas_com_notas"] == 2
    assert {e["cnpj"] for e in previa["empresas"]} == {CONTAB, EMP, B, C}  # só ativas; a inativa fica fora
    nomes = zf.namelist()
    pasta_emp, pasta_b = f"{EMP} Empresa Ação & Cia/", f"{B} EMPRESA B SERVIÇOS LTDA/"
    assert any(n.startswith(pasta_emp + "prestados/xml/") for n in nomes)
    assert len([n for n in nomes if n.startswith(pasta_emp) and "/xml/" in n]) == 38
    assert len([n for n in nomes if n.startswith(pasta_b + "prestados/xml/")]) == 7
    assert pasta_emp + "relatorio.xlsx" in nomes and pasta_b + "relatorio.xlsx" in nomes
    assert not any(n.startswith(C) or n.startswith(INATIVA) or n.startswith(CONTAB) for n in nomes)  # sem notas: sem pasta
    assert len([n for n in nomes if n.endswith(".xml")]) == previa["arquivos_xml"] == x["total_notas"] == 45
    assert "resumo_empresas.xlsx" in nomes
    ws = load_workbook(io.BytesIO(zf.read("resumo_empresas.xlsx")))["Empresas"]
    linhas = [r for r in ws.iter_rows(values_only=True) if r and r[1] in (CONTAB, EMP, B, C)]
    assert len(linhas) == 4 and sum(r[3] for r in linhas) == 45
    assert [r for r in ws.iter_rows(values_only=True) if r and r[0] == "Total"][0][10] == 45
    assert 'filename="Contask_NF_Todas_as_empresas_2026-10-01_a_2026-10-31.zip"' in z.headers["content-disposition"]
    # Aparece no histórico de qualquer empresa
    assert x["id"] in [h["id"] for h in cliente.get(f"/api/empresas/{ids[B]}/exportacoes").json()]
    # Resumo em PDF quando o relatório escolhido é PDF
    _, _, _, zf2 = _exportar(cliente, eid, escopo="todas", relatorio="pdf", **OUTUBRO)
    assert "resumo_empresas.pdf" in zf2.namelist() and f"{pasta_b}relatorio.pdf" in zf2.namelist()
