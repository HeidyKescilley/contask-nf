"""Um escritório não vê empresa, nota, XML, DANFSe, job nem exportação de outro."""
from fastapi.testclient import TestClient

from app.core.db import nova_sessao
from app.jobs.barramento import barramento
from app.models import BuscaJob, Empresa, Escritorio, Exportacao, Nota
from tests.certs import criar_pfx, dv_cnpj

SENHA = "Senha-Forte-123"
CONTAB = dv_cnpj("112223330001")
EMP = dv_cnpj("114447770001")
CONTAB_B = dv_cnpj("223334440001")
EMP_B = dv_cnpj("334445550001")


def _cadastrar(c, email, nome="Pessoa"):
    r = c.post("/api/auth/cadastrar", json={"nome": nome, "email": email, "senha": SENHA})
    assert r.status_code == 201, r.text
    return r.json()


def _contabilidade(c, cnpj, nome):
    r = c.post("/api/contabilidade", data={"cnpj": cnpj, "razao_social": nome, "senha": "S3nh@-Teste!"},
               files={"arquivo": ("c.pfx", criar_pfx(nome, cnpj=cnpj), "application/x-pkcs12")})
    assert r.status_code == 200, r.text
    return r.json()["empresa"]["id"]


def _empresa(c, cnpj, nome):
    r = c.post("/api/empresas", data={"cnpj": cnpj, "razao_social": nome, "modo_certificado": "contabilidade"})
    assert r.status_code == 201, r.text
    return r.json()["empresa"]["id"]


def test_cadastro_assume_escritorio_orfao_e_o_seguinte_cria_outro(app_teste):
    with TestClient(app_teste, base_url="http://127.0.0.1:8765"):
        pass
    with nova_sessao() as db:
        esc = Escritorio(nome="Legado")
        db.add(esc)
        db.flush()
        db.add(Empresa(escritorio_id=esc.id, cnpj=EMP, razao_social="Antiga", is_contabilidade=False))
        db.commit()
        legado = esc.id
    with TestClient(app_teste, base_url="http://127.0.0.1:8765") as c:
        eu = _cadastrar(c, "primeiro@contask.local", "Primeiro")
        assert eu["escritorio"]["id"] == legado
        assert eu["escritorio"]["nome"] == "Primeiro"
        lista = c.get("/api/empresas").json()
        assert [e["razao_social"] for e in lista] == ["Antiga"]
        eid = lista[0]["id"]
    with TestClient(app_teste, base_url="http://127.0.0.1:8765") as c:
        eu = _cadastrar(c, "segundo@contask.local", "Segundo")
        assert eu["escritorio"]["id"] != legado
        assert c.get("/api/empresas").json() == []
        assert c.get(f"/api/empresas/{eid}").status_code == 404


def test_outro_escritorio_recebe_404_e_exportacao_todas_fica_no_seu(app_teste):
    with TestClient(app_teste, base_url="http://127.0.0.1:8765") as a:
        _cadastrar(a, "a@contask.local", "Escritório A")
        _contabilidade(a, CONTAB, "Contab A")
        emp = _empresa(a, EMP, "Empresa A")
        with nova_sessao() as db:
            nota = Nota(empresa_id=emp, chave="1" * 44, papel="prestada", status="autorizada")
            job = BuscaJob(empresa_id=emp, tipo="incremental", status="fila")
            exp = Exportacao(empresa_id=emp, filtros={"escopo": "todas"}, status="concluido", zip_path="x.zip")
            db.add_all([nota, job, exp])
            db.commit()
            nota_id, job_id, exp_id = nota.id, job.id, exp.id

    with TestClient(app_teste, base_url="http://127.0.0.1:8765") as b:
        _cadastrar(b, "b@contask.local", "Escritório B")
        assert b.get(f"/api/empresas/{emp}").status_code == 404
        assert b.get(f"/api/empresas/{emp}/notas").status_code == 404
        assert b.get(f"/api/empresas/{emp}/dashboard").status_code == 404
        assert b.get(f"/api/notas/{nota_id}").status_code == 404
        assert b.get(f"/api/notas/{nota_id}/xml").status_code == 404
        assert b.get(f"/api/notas/{nota_id}/pdf").status_code == 404
        assert b.get(f"/api/buscas/{job_id}/log").status_code == 404
        assert b.get(f"/api/exportacoes/{exp_id}/arquivo").status_code == 404
        assert b.get("/api/empresas").json() == []

        _contabilidade(b, CONTAB_B, "Contab B")
        emp_b = _empresa(b, EMP_B, "Empresa B")
        previa = b.post(f"/api/empresas/{emp_b}/exportacoes/previa", json={"escopo": "todas", "status": "todas"})
        assert previa.status_code == 200, previa.text
        ids = [e["id"] for e in previa.json()["empresas"]]
        assert emp not in ids and emp_b in ids
        assert previa.json()["total"] == 0


def test_sse_entrega_so_o_escritorio_da_conexao(app_teste):
    with TestClient(app_teste, base_url="http://127.0.0.1:8765") as a:
        esc_a = _cadastrar(a, "sse-a@contask.local")["escritorio"]["id"]
    with TestClient(app_teste, base_url="http://127.0.0.1:8765") as b:
        esc_b = _cadastrar(b, "sse-b@contask.local")["escritorio"]["id"]
        with b.stream("GET", "/api/eventos/stream") as resp:
            linhas = resp.iter_lines()
            assert "retry" in next(linhas)
            barramento.publicar({"tipo": "job", "id": 9, "escritorio_id": esc_a, "status": "fila",
                                 "mensagem": "segredo-alheio"})
            barramento.publicar({"tipo": "job", "id": 8, "escritorio_id": esc_b, "status": "fila",
                                 "mensagem": "evento-proprio"})
            texto = ""
            for linha in linhas:
                texto += linha + "\n"
                if "evento-proprio" in texto:
                    break
        assert "segredo-alheio" not in texto
        assert "evento-proprio" in texto
