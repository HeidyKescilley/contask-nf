"""Formulário de teste grátis do site: lead, conta de teste de 30 dias e e-mail de acesso."""
import re
from datetime import timedelta

import pytest

from app.core import escritorios
from app.core.db import nova_sessao
from app.models import Escritorio, Lead, Usuario

SITE = "https://contasknf.com.br"
PEDIDO = {"nome": "Contábil Exemplo Ltda", "segmento": "contabilidade", "email": "Contato@Exemplo.com.br",
          "telefone": "(61) 99999-8888", "origem": "/30-dias-gratis/?utm_source=google"}


@pytest.fixture()
def site(monkeypatch):
    """Antes do app subir: site de vendas e e-mail do sistema configurados (o envio é simulado)."""
    monkeypatch.setenv("CONTASK_SITE_URL", SITE)
    monkeypatch.setenv("CONTASK_APP_URL", "https://app.contasknf.com.br")
    monkeypatch.setenv("CONTASK_SMTP_HOST", "smtp.exemplo")
    monkeypatch.setenv("CONTASK_SMTP_SENHA", "senha-da-caixa")
    monkeypatch.setenv("CONTASK_EMAIL_REMETENTE", "notas@contasknf.com.br")
    enviados = []
    from app.core import email as correio
    monkeypatch.setattr(correio, "enviar", lambda para, assunto, texto, html=None: enviados.append(
        {"para": para, "assunto": assunto, "texto": texto, "html": html}))
    return enviados


def _pedir(cliente, origem=SITE, **extra):
    cliente.cookies.clear()
    return cliente.post("/api/publico/teste", json={**PEDIDO, **extra}, headers={"Origin": origem} if origem else {})


def _senha(texto: str) -> str:
    return re.search(r"Senha provisória: (\S+)", texto).group(1)


def test_formulario_cria_conta_de_teste_e_envia_o_acesso(site, cliente):
    r = _pedir(cliente)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["email"] == "contato@exemplo.com.br" and corpo["envio"] == "email"
    assert "senha" not in r.text.lower()  # a senha só vai por e-mail
    with nova_sessao() as db:
        lead = db.query(Lead).one()
        esc = db.get(Escritorio, lead.escritorio_id)
        u = db.get(Usuario, lead.usuario_id)
        assert (lead.segmento, lead.telefone, lead.resultado, lead.email_status) == ("contabilidade", "61999998888", "conta_criada", "enviado")
        assert lead.origem.startswith("/30-dias-gratis/")
        assert esc.nome == "Contábil Exemplo Ltda" and esc.tipo == "contador" and esc.situacao == "teste"
        assert esc.teste_ate == escritorios.hoje() + timedelta(days=29)
        assert u.trocar_senha
    (msg,) = site
    assert msg["para"] == "contato@exemplo.com.br" and "30 dias" in msg["assunto"]
    assert "https://app.contasknf.com.br/entrar" in msg["texto"] and esc.teste_ate.strftime("%d/%m/%Y") in msg["texto"]
    # a senha do e-mail entra e pede a troca
    entrada = cliente.post("/api/auth/entrar", json={"email": "contato@exemplo.com.br", "senha": _senha(msg["texto"])})
    assert entrada.status_code == 200 and entrada.json()["usuario"]["trocar_senha"] is True


def test_nenhum_dos_dois_vira_conta_da_empresa(site, cliente):
    assert _pedir(cliente, segmento="nenhum").status_code == 201
    with nova_sessao() as db:
        assert db.get(Escritorio, db.query(Lead).one().escritorio_id).tipo == "empresa"


def test_email_ja_cadastrado_guarda_o_lead_sem_criar_conta(site, cliente):
    r = _pedir(cliente, email="teste@contask.local")
    assert r.status_code == 409 and "Já existe uma conta" in r.json()["detail"]
    with nova_sessao() as db:
        lead = db.query(Lead).one()
        assert lead.resultado == "email_existente" and lead.escritorio_id is None
    assert site == []


@pytest.mark.parametrize("campo,valor", [("telefone", "9999"), ("email", "sem-arroba"), ("segmento", "outro")])
def test_dados_invalidos(site, cliente, campo, valor):
    assert _pedir(cliente, **{campo: valor}).status_code == 422


def test_robo_que_preenche_o_campo_escondido_nao_cria_nada(site, cliente):
    assert _pedir(cliente, site="http://spam").status_code == 201
    with nova_sessao() as db:
        assert db.query(Lead).count() == 0


def test_limite_de_pedidos_por_ip(site, cliente):
    for i in range(3):
        assert _pedir(cliente, email=f"p{i}@exemplo.com.br").status_code == 201
    assert _pedir(cliente, email="p4@exemplo.com.br").status_code == 429


def test_origem_do_site_so_alcanca_o_formulario(site, cliente):
    assert _pedir(cliente, origem="https://outro-site.com").status_code == 403
    cliente.cookies.clear()
    r = cliente.post("/api/auth/entrar", json={"email": "x@x.com", "senha": "x"}, headers={"Origin": SITE})
    assert r.status_code == 403


def test_sem_email_configurado_o_lead_fica_para_a_equipe(monkeypatch, cliente):
    monkeypatch.setenv("CONTASK_SITE_URL", SITE)
    from app.core import config as cfgmod
    cfgmod.config.cache_clear()
    r = _pedir(cliente)
    assert r.status_code == 201 and r.json()["envio"] == "equipe"
    with nova_sessao() as db:
        assert db.query(Lead).one().email_status == "sem_envio"


def _admin(cliente):
    from app.tools import usuarios
    usuarios.main(["admin", "teste@contask.local"])


def test_painel_lista_edita_exporta_e_reenvia(site, cliente):
    _pedir(cliente)
    cliente.cookies.clear()
    from tests.conftest import SENHA_TESTE
    assert cliente.post("/api/auth/entrar", json={"email": "teste@contask.local", "senha": SENHA_TESTE}).status_code == 200
    assert cliente.get("/api/admin/leads").status_code == 403  # só admin do sistema
    _admin(cliente)
    dados = cliente.get("/api/admin/leads").json()
    assert dados["email_configurado"] is True
    (lead,) = dados["leads"]
    assert lead["escritorio"]["situacao"] == "teste" and lead["primeiro_acesso_feito"] is False
    r = cliente.put(f"/api/admin/leads/{lead['id']}", json={"etapa": "em_contato", "observacoes": "Ligar segunda"})
    assert r.json() == {"id": lead["id"], "etapa": "em_contato", "observacoes": "Ligar segunda"}
    assert cliente.put(f"/api/admin/leads/{lead['id']}", json={"etapa": "xpto"}).status_code == 422
    csv = cliente.get("/api/admin/leads/exportar")
    assert csv.status_code == 200 and "Teste grátis;Contábil Exemplo Ltda;;Contabilidade;contato@exemplo.com.br;61999998888;;;Em contato;Em teste" in csv.content.decode("utf-8-sig")
    # reenviar: senha nova, a antiga deixa de valer
    antiga = _senha(site[0]["texto"])
    assert cliente.post(f"/api/admin/leads/{lead['id']}/reenviar").json() == {"email_status": "enviado"}
    nova = _senha(site[1]["texto"])
    assert nova != antiga
    cliente.cookies.clear()
    assert cliente.post("/api/auth/entrar", json={"email": "contato@exemplo.com.br", "senha": antiga}).status_code == 401
    assert cliente.post("/api/auth/entrar", json={"email": "contato@exemplo.com.br", "senha": nova}).status_code == 200


def test_fim_do_teste_trava_o_acesso(site, cliente):
    _pedir(cliente)
    with nova_sessao() as db:
        lead = db.query(Lead).one()
        db.get(Escritorio, lead.escritorio_id).teste_ate = escritorios.hoje() - timedelta(days=1)
        db.commit()
    texto = site[0]["texto"]
    r = cliente.post("/api/auth/entrar", json={"email": "contato@exemplo.com.br", "senha": _senha(texto)})
    assert r.status_code == 401 and "período de teste" in r.json()["detail"]


# --- Black Friday ---------------------------------------------------------------------------------

BF = {"nome": "Ana Souza", "escritorio": "Contábil Aurora", "email": "Ana@Aurora.com.br", "telefone": "(61) 98888-7777",
      "notas_mes": "100_500", "aceita_whatsapp": True, "origem": "/black-friday/?utm_source=linkedin"}


@pytest.fixture()
def oferta_aberta(monkeypatch):
    from datetime import datetime
    from app.api import leads
    monkeypatch.setattr(leads, "BLACK_FRIDAY_ATE", datetime(2999, 1, 1, tzinfo=escritorios.BRASILIA))
    return leads


def _bf(cliente, **extra):
    cliente.cookies.clear()
    return cliente.post("/api/publico/black-friday", json={**BF, **extra}, headers={"Origin": SITE})


def test_black_friday_grava_o_lead_sem_criar_conta_e_avisa_a_equipe(site, oferta_aberta, cliente):
    r = _bf(cliente)
    assert r.status_code == 201, r.text
    assert r.json() == {"situacao": "oferta"}
    with nova_sessao() as db:
        lead = db.query(Lead).one()
        assert (lead.campanha, lead.nome, lead.contato, lead.email, lead.telefone) == (
            "black_friday", "Contábil Aurora", "Ana Souza", "ana@aurora.com.br", "61988887777")
        assert (lead.notas_mes, lead.aceita_whatsapp, lead.resultado, lead.escritorio_id) == ("100_500", True, "oferta", None)
        assert db.query(Usuario).filter_by(email="ana@aurora.com.br").first() is None
    (aviso,) = site
    assert aviso["para"] == "notas@contasknf.com.br" and "Contábil Aurora" in aviso["assunto"]
    assert "61988887777" in aviso["texto"]


def test_black_friday_acima_de_mil_notas_vira_plano_personalizado(site, oferta_aberta, cliente):
    assert _bf(cliente, notas_mes="acima_1000").json() == {"situacao": "plano_personalizado"}
    assert "Plano personalizado" in site[0]["assunto"]


def test_black_friday_valida_os_campos(site, oferta_aberta, cliente):
    assert _bf(cliente, notas_mes="10_mil").status_code == 422
    assert _bf(cliente, email="sem-arroba").status_code == 422
    assert _bf(cliente, telefone="1234").status_code == 422


def test_black_friday_encerrada_recusa(site, cliente, monkeypatch):
    from datetime import datetime
    from app.api import leads
    monkeypatch.setattr(leads, "BLACK_FRIDAY_ATE", datetime(2000, 1, 1, tzinfo=escritorios.BRASILIA))
    assert _bf(cliente).status_code == 410


def test_black_friday_aparece_no_painel_e_na_exportacao(site, oferta_aberta, cliente):
    _bf(cliente, notas_mes="acima_1000")
    cliente.cookies.clear()
    from tests.conftest import SENHA_TESTE
    assert cliente.post("/api/auth/entrar", json={"email": "teste@contask.local", "senha": SENHA_TESTE}).status_code == 200
    _admin(cliente)
    (lead,) = cliente.get("/api/admin/leads").json()["leads"]
    assert (lead["campanha_rotulo"], lead["contato"], lead["notas_mes_rotulo"], lead["escritorio"]) == (
        "Black Friday", "Ana Souza", "Mais de 1.000 notas/mês", None)
    csv = cliente.get("/api/admin/leads/exportar").content.decode("utf-8")
    assert "Black Friday;Contábil Aurora;Ana Souza" in csv and "Plano personalizado" in csv
