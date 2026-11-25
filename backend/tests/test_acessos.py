"""Acessos do site: registro de visitas sem cookie/IP e o painel de canais x leads."""
import pytest

from app.api.acessos import canal_do_dominio, canal_do_lead
from app.core.db import nova_sessao
from app.models import Visita

SITE = "https://contasknf.com.br"
NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0 Safari/537.36"
CELULAR = "Mozilla/5.0 (Linux; Android 14) Chrome/131.0 Mobile Safari/537.36"


@pytest.fixture()
def site(monkeypatch):
    monkeypatch.setenv("CONTASK_SITE_URL", SITE)


def _visita(cliente, pagina, referencia=None, navegador=NAVEGADOR, ip="10.1.1.1", largura=1280):
    cliente.cookies.clear()
    return cliente.post("/api/publico/visita", json={"pagina": pagina, "referencia": referencia, "largura": largura},
                        headers={"Origin": SITE, "User-Agent": navegador, "X-Forwarded-For": ip})


def _admin(cliente):
    from app.tools import usuarios
    from tests.conftest import SENHA_TESTE
    cliente.cookies.clear()
    assert cliente.post("/api/auth/entrar", json={"email": "teste@contask.local", "senha": SENHA_TESTE}).status_code == 200
    from tests.conftest import entrar_admin; entrar_admin(cliente)


def test_registra_visita_com_canal_sem_guardar_ip(site, cliente):
    assert _visita(cliente, "/black-friday/?utm_source=LinkedIn&utm_medium=social&utm_campaign=bf26").status_code == 204
    assert _visita(cliente, "/", referencia="https://l.instagram.com/?u=x", navegador=CELULAR, largura=390).status_code == 204
    assert _visita(cliente, "/30-dias-gratis/", referencia=SITE + "/").status_code == 204  # navegação interna
    assert _visita(cliente, "/", navegador="Googlebot/2.1").status_code == 204  # robô: ignorado
    with nova_sessao() as db:
        v = db.query(Visita).order_by(Visita.id).all()
        assert [(x.pagina, x.canal, x.dispositivo) for x in v] == [
            ("/black-friday/", "linkedin", "computador"), ("/", "instagram", "celular"), ("/30-dias-gratis/", "direto", "computador")]
        assert (v[0].meio, v[0].campanha) == ("social", "bf26")
        assert all(len(x.visitante) == 16 and "10.1.1.1" not in x.visitante for x in v)


def test_visita_de_outra_origem_e_recusada(site, cliente):
    cliente.cookies.clear()
    r = cliente.post("/api/publico/visita", json={"pagina": "/"}, headers={"Origin": "https://outro.com"})
    assert r.status_code == 403


def test_canais():
    assert canal_do_dominio("www.google.com.br") == "google"
    assert canal_do_dominio("t.co") == "twitter"
    assert canal_do_dominio("lm.facebook.com") == "facebook"
    assert canal_do_lead("/30-dias-gratis/?utm_source=whatsapp") == "whatsapp"
    assert canal_do_lead("/30-dias-gratis/ (de www.google.com)") == "google"
    assert canal_do_lead(None) == "direto"


def test_painel_cruza_visitas_e_leads_por_canal(site, cliente, monkeypatch):
    from datetime import datetime
    from app.api import leads
    from app.core import escritorios
    monkeypatch.setattr(leads, "BLACK_FRIDAY_ATE", datetime(2999, 1, 1, tzinfo=escritorios.BRASILIA))
    # No TestClient o IP é sempre o mesmo: pessoas diferentes = navegadores diferentes
    for n in (1, 2):
        _visita(cliente, "/black-friday/?utm_source=linkedin", navegador=f"{NAVEGADOR} v{n}")
    _visita(cliente, "/", navegador=f"{NAVEGADOR} v3")
    cliente.cookies.clear()
    r = cliente.post("/api/publico/black-friday", headers={"Origin": SITE}, json={
        "nome": "Ana", "escritorio": "Contábil Aurora", "email": "ana@aurora.com.br", "telefone": "61988887777",
        "notas_mes": "ate_100", "origem": "/black-friday/?utm_source=linkedin"})
    assert r.status_code == 201, r.text
    assert cliente.get("/api/admin/acessos").status_code in (401, 403)
    _admin(cliente)
    dados = cliente.get("/api/admin/acessos?dias=7").json()
    assert dados["totais"] == {"visitas": 3, "pessoas": 3, "leads": 1, "black_friday": 1, "taxa": 33.3}
    linkedin = next(c for c in dados["canais"] if c["canal"] == "linkedin")
    assert (linkedin["pessoas"], linkedin["leads"], linkedin["taxa"]) == (2, 1, 50.0)
    assert len(dados["por_dia"]) == 7 and dados["por_dia"][-1]["visitas"] == 3
    assert dados["paginas"][0] == {"pagina": "/black-friday/", "visitas": 2, "pessoas": 2, "leads": 1, "taxa": 50.0}
