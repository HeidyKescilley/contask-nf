"""Contabilidade com dois certificados de procurador (e-CNPJ do escritório e e-CPF do contador): a busca
testa os dois e o que tem a procuração vira o padrão da empresa (busca e emissão)."""
from sqlalchemy import select

from app.core.db import nova_sessao
from app.jobs.fila import enfileirar
from app.jobs.sincronizador import Contexto, executar_job
from app.models import BuscaJob, BuscaLog, Empresa, SyncEstado
from tests.adn_simulado import ADNSimulado, chave_fake
from tests.certs import criar_pfx
from tests.test_busca import C1, C2, CONTAB, SENHA, base  # noqa: F401 (fixture)

CPF = "52998224725"


def _enviar_cpf(cliente, pfx: bytes):
    return cliente.put("/api/contabilidade/certificado-extra", data={"senha": SENHA},
                       files={"arquivo": ("cpf.pfx", pfx, "application/x-pkcs12")})


def _rodar(adn, empresa_id):
    with nova_sessao() as db:
        jid = db.scalar(select(BuscaJob.id).where(BuscaJob.empresa_id == empresa_id, BuscaJob.status == "fila"))
        if jid is None:
            jid = enfileirar(db, empresa_id, "incremental").id
            db.commit()
    return executar_job(jid, nova_sessao, Contexto(fabrica=adn.fabrica, pausa=0, dormir=lambda s: None, publicar=lambda e: None))


def _cert_principal_pfx() -> bytes:
    from app.core.certificados import carregar_pfx
    from app.models import Certificado
    with nova_sessao() as db:
        c = db.scalar(select(Empresa).where(Empresa.is_contabilidade))
        pfx, _ = carregar_pfx(db.get(Certificado, c.certificado_id))
        return pfx


def test_segundo_certificado_com_a_procuracao_vira_padrao(base, cliente):
    pfx_cpf = criar_pfx("CONTADOR", cpf=CPF)
    r = _enviar_cpf(cliente, pfx_cpf)
    assert r.status_code == 200, r.text
    contab = r.json()["empresa"]
    assert contab["certificado_extra"]["tipo"] == "e-CPF" and contab["certificado"]["tipo"] == "e-CNPJ"

    adn = ADNSimulado()
    adn.adicionar_nota(C1, chave_fake(1, C1), numero=1)
    adn.procuracao_so_de[C1] = {ADNSimulado.cert_id(pfx_cpf)}  # C1 deu procuração só ao CPF
    assert _rodar(adn, base[C1]) == "concluido"
    e = cliente.get(f"/api/empresas/{base[C1]}").json()
    assert e["certificado"]["titular_doc"] == CPF and e["procuracao_confirmada"] is True
    with nova_sessao() as db:
        logs = [l.mensagem for l in db.scalars(select(BuscaLog).order_by(BuscaLog.id))]
    assert any("não tem procuração desta empresa. Tentando o de CONTADOR" in m for m in logs)
    assert any("fica como padrão" in m for m in logs)

    # próxima busca já começa pelo CPF: nenhuma tentativa com o CNPJ
    adn.chamadas.clear()
    adn.procuracao_so_de[C1] = {ADNSimulado.cert_id(pfx_cpf)}
    n_antes = len(adn.max_por_cert)
    assert _rodar(adn, base[C1]) == "concluido"
    assert len(adn.max_por_cert) == n_antes

    # o emissor usa o mesmo certificado
    from app.api.emissor import certificado_procuracao
    with nova_sessao() as db:
        assert certificado_procuracao(db, db.get(Empresa, base[C1])).titular_doc == CPF


def test_principal_continua_padrao_quando_tem_a_procuracao(base, cliente):
    assert _enviar_cpf(cliente, criar_pfx("CONTADOR", cpf=CPF)).status_code == 200
    adn = ADNSimulado()
    adn.adicionar_nota(C2, chave_fake(1, C2), numero=1)
    assert _rodar(adn, base[C2]) == "concluido"
    e = cliente.get(f"/api/empresas/{base[C2]}").json()
    assert e["certificado"]["titular_doc"] == CONTAB and e["procuracao_confirmada"] is True


def test_nenhum_dos_dois_tem_procuracao(base, cliente):
    assert _enviar_cpf(cliente, criar_pfx("CONTADOR", cpf=CPF)).status_code == 200
    adn = ADNSimulado(sem_procuracao={C1})
    assert _rodar(adn, base[C1]) == "erro"
    with nova_sessao() as db:
        s = db.get(SyncEstado, base[C1])
        assert s.situacao == "sem_procuracao" and "Nenhum dos certificados da contabilidade" in s.ultimo_erro
        assert db.get(Empresa, base[C1]).certificado_procurador_id is None


def test_enviar_o_segundo_rebusca_quem_estava_sem_procuracao(base, cliente):
    adn = ADNSimulado(sem_procuracao={C1})
    assert _rodar(adn, base[C1]) == "erro"
    r = _enviar_cpf(cliente, criar_pfx("CONTADOR", cpf=CPF))
    assert r.status_code == 200 and any("buscadas de novo" in a for a in r.json()["avisos"])
    with nova_sessao() as db:
        assert db.get(SyncEstado, base[C1]).situacao != "sem_procuracao"
        assert db.scalar(select(BuscaJob).where(BuscaJob.empresa_id == base[C1], BuscaJob.status == "fila")) is not None


def test_mesmo_certificado_recusado_e_remocao_volta_ao_principal(base, cliente):
    r = _enviar_cpf(cliente, _cert_principal_pfx())
    assert r.status_code == 409 and "mesmo certificado principal" in r.json()["detail"]
    pfx_cpf = criar_pfx("CONTADOR", cpf=CPF)
    assert _enviar_cpf(cliente, pfx_cpf).status_code == 200
    adn = ADNSimulado()
    adn.procuracao_so_de[C1] = {ADNSimulado.cert_id(pfx_cpf)}
    assert _rodar(adn, base[C1]) == "concluido"
    r = cliente.delete("/api/contabilidade/certificado-extra")
    assert r.status_code == 200 and r.json()["certificado_extra"] is None
    e = cliente.get(f"/api/empresas/{base[C1]}").json()
    assert e["certificado"]["titular_doc"] == CONTAB and e["procuracao_confirmada"] is False
    assert cliente.delete("/api/contabilidade/certificado-extra").status_code == 404
