"""Teste grátis pelo formulário do site: guarda o lead, cria a conta de teste e envia o acesso por e-mail.

- POST /api/publico/teste é público (ROTAS_PUBLICAS) e aceita a origem do site (CONTASK_SITE_URL); o Caddy
  repassa essa rota do domínio do site para o sistema, então o formulário não precisa de CORS.
- A senha inicial só existe na memória até o e-mail sair: não é gravada, não vai para log nem para a
  resposta. O usuário troca a senha no primeiro acesso.
- Painel (admin do sistema): lista, etapa comercial, anotações, exportação e reenvio do acesso.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import exigir_admin
from app.api.auth import ip_cliente
from app.core import autenticacao as auth
from app.core import email as correio
from app.core import escritorios as regras
from app.core.config import config
from app.core.db import nova_sessao, sessao
from app.models import Escritorio, EscritorioEvento, Lead, Usuario, agora

publico = APIRouter(prefix="/api/publico", tags=["site"])
painel = APIRouter(prefix="/api/admin/leads", tags=["admin"])

SEGMENTOS = {"contabilidade": "Contabilidade", "bpo": "BPO", "financeiro": "Financeiro", "nenhum": "Nenhum dos dois"}
# Contabilidade, BPO e financeiro cuidam de vários CNPJs: conta de contador. Os demais: conta da empresa.
TIPO_DA_CONTA = {"contabilidade": "contador", "bpo": "contador", "financeiro": "contador", "nenhum": "empresa"}
ETAPAS = {"novo": "Novo", "em_contato": "Em contato", "cliente": "Cliente", "perdido": "Perdido"}
CAMPANHAS = {"black_friday": "Black Friday"}
NOTAS_MES = {"ate_100": "Até 100 notas/mês", "100_500": "100 a 500 notas/mês", "500_1000": "500 a 1.000 notas/mês",
             "acima_1000": "Mais de 1.000 notas/mês"}
# Black Friday: 12 meses por R$ 29,90, até 1.000 notas/mês. Acima disso vira plano personalizado (contato manual).
BLACK_FRIDAY_ATE = datetime(2026, 11, 27, 23, 59, 59, tzinfo=regras.BRASILIA)
WHATSAPP_SUPORTE = "(61) 99654-3664"
# No máximo 3 pedidos de teste por IP a cada hora
limitador_leads = auth.Limitador(maximo=3, janela=60 * 60)


class PedidoTeste(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    segmento: str
    email: str = Field(max_length=200)
    telefone: str = Field(max_length=30)
    origem: str | None = Field(None, max_length=300)
    # Campo escondido no formulário: só robô preenche
    site: str | None = None


def _br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _app_url() -> str:
    c = config()
    if c.app_url:
        return c.app_url.rstrip("/")
    return f"https://{c.lista_hosts[0]}" if c.lista_hosts else f"http://127.0.0.1:{c.porta}"


def _texto_acesso(nome: str, email: str, senha: str, ate: date | None) -> tuple[str, str, str]:
    url = f"{_app_url()}/entrar"
    prazo = f"O teste vai até {_br(ate)}, com tudo liberado." if ate else "O teste tem tudo liberado."
    assunto = "Seu acesso ao Contask NF: 30 dias grátis"
    texto = (f"Olá, {nome}!\n\nSeu acesso ao Contask NF está pronto. {prazo}\n\n"
             f"Endereço: {url}\nE-mail: {email}\nSenha provisória: {senha}\n\n"
             "No primeiro acesso o sistema pede uma senha nova, só sua.\n\n"
             "Para começar, cadastre o certificado digital A1 (.pfx) e o sistema busca as notas no Ambiente Nacional.\n\n"
             f"Dúvidas? Responda este e-mail ou chame no WhatsApp {WHATSAPP_SUPORTE}.\n\nEquipe Contask NF")
    html = f"""<!doctype html><html lang="pt-BR"><body style="margin:0;background:#f6f7f7;font-family:Arial,Helvetica,sans-serif;color:#15191a">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border:1px solid #e3e6e6;border-radius:14px">
<tr><td style="padding:28px">
<p style="margin:0 0 4px;font-size:18px;font-weight:bold">Contask <span style="color:#1d4ed8">NF</span></p>
<h1 style="font-size:22px;margin:18px 0 8px">Olá, {_esc(nome)}!</h1>
<p style="margin:0 0 18px;color:#5f6a6c;font-size:15px">Seu acesso está pronto. {_esc(prazo)}</p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#f6f7f7;border-radius:10px;font-size:15px">
<tr><td style="padding:14px 16px 4px;color:#5f6a6c">E-mail</td></tr>
<tr><td style="padding:0 16px 10px;font-weight:bold">{_esc(email)}</td></tr>
<tr><td style="padding:4px 16px 4px;color:#5f6a6c">Senha provisória</td></tr>
<tr><td style="padding:0 16px 14px;font-weight:bold;font-family:Consolas,monospace;font-size:17px">{_esc(senha)}</td></tr>
</table>
<p style="margin:22px 0"><a href="{url}" style="display:inline-block;background:#1d4ed8;color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:10px;font-weight:bold">Entrar no Contask NF</a></p>
<p style="margin:0 0 10px;color:#5f6a6c;font-size:14px">No primeiro acesso o sistema pede uma senha nova, só sua. Para começar, cadastre o certificado digital A1 (.pfx) e o sistema busca as notas no Ambiente Nacional.</p>
<p style="margin:0;color:#5f6a6c;font-size:14px">Dúvidas? Responda este e-mail ou chame no WhatsApp {WHATSAPP_SUPORTE}.</p>
</td></tr></table></td></tr></table></body></html>"""
    return assunto, texto, html


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def enviar_acesso(lead_id: int, senha: str) -> str:
    """Envia o acesso e grava o resultado no lead. Devolve o status."""
    with nova_sessao() as db:
        lead = db.get(Lead, lead_id)
        if lead is None:
            return "erro"
        esc = db.get(Escritorio, lead.escritorio_id) if lead.escritorio_id else None
        assunto, texto, html = _texto_acesso(lead.nome, lead.email, senha, esc.teste_ate if esc else None)
        if not correio.configurado():
            lead.email_status, lead.email_erro = "sem_envio", "O e-mail do sistema não está configurado."
        else:
            try:
                correio.enviar(lead.email, assunto, texto, html)
                lead.email_status, lead.email_erro, lead.email_enviado_em = "enviado", None, agora()
            except correio.ErroEmail as e:
                lead.email_status, lead.email_erro = "erro", str(e)[:300]
        db.commit()
        return lead.email_status


def _telefone(v: str) -> str:
    d = re.sub(r"\D", "", v or "")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) not in (10, 11):
        raise HTTPException(422, "Informe o WhatsApp com DDD, por exemplo (61) 99999-9999.")
    return d


@publico.post("/teste", status_code=201)
def pedir_teste(d: PedidoTeste, request: Request, tarefas: BackgroundTasks, db: Session = Depends(sessao)):
    if d.site:  # robô
        return {"situacao": "conta_criada", "email": auth.normalizar_email(d.email), "teste_ate": None}
    ip = ip_cliente(request)
    if limitador_leads.bloqueado(ip):
        raise HTTPException(429, "Muitos pedidos feitos daqui na última hora. Tente de novo mais tarde ou chame no WhatsApp.")
    if d.segmento not in SEGMENTOS:
        raise HTTPException(422, "Escolha se é contabilidade, BPO, financeiro ou nenhum dos dois.")
    email = auth.normalizar_email(d.email)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "Informe um e-mail válido.")
    telefone = _telefone(d.telefone)
    nome = " ".join(d.nome.split())
    lead = Lead(nome=nome, segmento=d.segmento, email=email, telefone=telefone, ip=ip,
                origem=(d.origem or request.headers.get("referer") or "")[:300] or None,
                resultado="conta_criada", email_status="pendente")
    limitador_leads.falhou(ip)  # conta o pedido

    if db.scalar(select(Usuario.id).where(Usuario.email == email)):
        lead.resultado, lead.email_status = "email_existente", "sem_envio"
        db.add(lead)
        db.commit()
        raise HTTPException(409, "Já existe uma conta com esse e-mail. Entre no sistema ou, se esqueceu a senha, "
                                 f"chame no WhatsApp {WHATSAPP_SUPORTE}.")

    senha = auth.senha_aleatoria()
    try:
        u = auth.criar_usuario(db, email, nome, senha, trocar_senha=True, novo_escritorio=nome,
                               tipo=TIPO_DA_CONTA[d.segmento])
    except auth.ErroLogin as e:
        db.rollback()
        raise HTTPException(422, str(e)) from None
    esc = db.get(Escritorio, u.escritorio_id)
    regras.iniciar_teste(esc, config().lead_teste_dias)
    db.add(EscritorioEvento(escritorio_id=esc.id, tipo="criado",
                            descricao=f"Conta de {regras.TIPO_ROTULO[esc.tipo].lower()} criada pelo formulário do site "
                                      f"({SEGMENTOS[d.segmento]}), teste até {_br(esc.teste_ate)}, usuário {email}"))
    lead.escritorio_id, lead.usuario_id = esc.id, u.id
    db.add(lead)
    db.commit()
    tarefas.add_task(enviar_acesso, lead.id, senha)
    return {"situacao": "conta_criada", "email": email, "teste_ate": esc.teste_ate,
            "envio": "email" if correio.configurado() else "equipe"}


class PedidoBlackFriday(BaseModel):
    nome: str = Field(min_length=2, max_length=200)  # pessoa
    escritorio: str = Field(min_length=2, max_length=200)
    email: str = Field(max_length=200)
    telefone: str = Field(max_length=30)
    notas_mes: str
    aceita_whatsapp: bool = False
    origem: str | None = Field(None, max_length=300)
    site: str | None = None  # campo escondido: só robô preenche


def avisar_equipe(lead_id: int) -> None:
    """Avisa a caixa do sistema que chegou um lead da oferta, para a equipe chamar no WhatsApp."""
    if not correio.configurado():
        return
    with nova_sessao() as db:
        lead = db.get(Lead, lead_id)
        if lead is None:
            return
        destino = config().email_remetente
        personalizado = lead.resultado == "plano_personalizado"
        assunto = f"{'Plano personalizado' if personalizado else 'Black Friday'}: {lead.nome}"
        texto = "\n".join([
            f"Novo lead da Black Friday{' (plano personalizado)' if personalizado else ''}.", "",
            f"Nome: {lead.contato}", f"Escritório: {lead.nome}", f"WhatsApp: {lead.telefone}", f"E-mail: {lead.email}",
            f"Notas por mês: {NOTAS_MES.get(lead.notas_mes, lead.notas_mes)}",
            f"Aceita mensagens no WhatsApp: {'sim' if lead.aceita_whatsapp else 'não'}", f"Origem: {lead.origem or '-'}", "",
            f"Painel: {_app_url()}/admin/leads"])
        try:
            correio.enviar(destino, assunto, texto)
        except correio.ErroEmail:
            pass  # o lead já está salvo no painel


@publico.post("/black-friday", status_code=201)
def pedir_black_friday(d: PedidoBlackFriday, request: Request, tarefas: BackgroundTasks, db: Session = Depends(sessao)):
    if d.site:  # robô
        return {"situacao": "oferta"}
    if datetime.now(regras.BRASILIA) > BLACK_FRIDAY_ATE:
        raise HTTPException(410, f"A oferta de Black Friday terminou. Chame no WhatsApp {WHATSAPP_SUPORTE} para conhecer os planos.")
    ip = ip_cliente(request)
    if limitador_leads.bloqueado(ip):
        raise HTTPException(429, "Muitos pedidos feitos daqui na última hora. Tente de novo mais tarde ou chame no WhatsApp.")
    if d.notas_mes not in NOTAS_MES:
        raise HTTPException(422, "Escolha quantas notas o escritório emite por mês.")
    email = auth.normalizar_email(d.email)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "Informe um e-mail válido.")
    telefone = _telefone(d.telefone)
    personalizado = d.notas_mes == "acima_1000"
    lead = Lead(nome=" ".join(d.escritorio.split()), contato=" ".join(d.nome.split()), segmento="contabilidade",
                email=email, telefone=telefone, ip=ip, campanha="black_friday", notas_mes=d.notas_mes,
                aceita_whatsapp=d.aceita_whatsapp,
                origem=(d.origem or request.headers.get("referer") or "")[:300] or None,
                resultado="plano_personalizado" if personalizado else "oferta", email_status="sem_envio")
    limitador_leads.falhou(ip)
    db.add(lead)
    db.commit()
    tarefas.add_task(avisar_equipe, lead.id)
    return {"situacao": lead.resultado}


# --- painel ---------------------------------------------------------------------------------------

def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def _lead_out(lead: Lead, esc: Escritorio | None, u: Usuario | None) -> dict:
    return {
        "id": lead.id, "criado_em": _utc(lead.criado_em), "nome": lead.nome, "segmento": lead.segmento,
        "segmento_rotulo": SEGMENTOS.get(lead.segmento, lead.segmento), "email": lead.email, "telefone": lead.telefone,
        "origem": lead.origem, "resultado": lead.resultado, "etapa": lead.etapa, "observacoes": lead.observacoes,
        "email_status": lead.email_status, "email_enviado_em": _utc(lead.email_enviado_em), "email_erro": lead.email_erro,
        "escritorio_id": lead.escritorio_id, "campanha": lead.campanha,
        "campanha_rotulo": CAMPANHAS.get(lead.campanha) if lead.campanha else None, "contato": lead.contato,
        "notas_mes": lead.notas_mes, "notas_mes_rotulo": NOTAS_MES.get(lead.notas_mes) if lead.notas_mes else None,
        "aceita_whatsapp": lead.aceita_whatsapp,
        "escritorio": None if esc is None else {"nome": esc.nome, "tipo": esc.tipo, "situacao": esc.situacao,
                                                "teste_ate": esc.teste_ate, "bloqueio": regras.motivo_bloqueio(esc)},
        "primeiro_acesso_feito": None if u is None else not u.trocar_senha,
        "ultimo_acesso_em": None if u is None else _utc(u.ultimo_acesso_em),
    }


def _todos(db: Session) -> list[dict]:
    leads = list(db.scalars(select(Lead).order_by(Lead.criado_em.desc(), Lead.id.desc())))
    escs = {e.id: e for e in db.scalars(select(Escritorio).where(Escritorio.id.in_({l.escritorio_id for l in leads if l.escritorio_id})))}
    us = {u.id: u for u in db.scalars(select(Usuario).where(Usuario.id.in_({l.usuario_id for l in leads if l.usuario_id})))}
    return [_lead_out(l, escs.get(l.escritorio_id), us.get(l.usuario_id)) for l in leads]


@painel.get("")
def listar(db: Session = Depends(sessao), _adm: Usuario = Depends(exigir_admin)):
    return {"leads": _todos(db), "email_configurado": correio.configurado()}


@painel.get("/exportar")
def exportar(db: Session = Depends(sessao), _adm: Usuario = Depends(exigir_admin)):
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";")
    w.writerow(["Data", "Campanha", "Nome", "Contato", "Segmento", "E-mail", "WhatsApp", "Notas por mês", "Aceita WhatsApp",
                "Etapa", "Situação da conta", "Teste até", "Primeiro acesso", "E-mail de acesso", "Origem", "Observações"])
    situacoes = {"teste": "Em teste", "ativo": "Ativo", "suspenso": "Suspenso"}
    envio = {"enviado": "Enviado", "erro": "Erro", "pendente": "Pendente", "sem_envio": "Não enviado"}
    for l in _todos(db):
        e = l["escritorio"]
        situacao = {"oferta": "Aguardando pagamento", "plano_personalizado": "Plano personalizado"}.get(l["resultado"]) or (
            "Conta já existia" if l["resultado"] == "email_existente" else None) or (
            "Teste encerrado" if e and e["bloqueio"] and e["situacao"] == "teste" else situacoes.get(e["situacao"], "-") if e else "-")
        w.writerow([l["criado_em"].astimezone(regras.BRASILIA).strftime("%d/%m/%Y %H:%M"), l["campanha_rotulo"] or "Teste grátis",
                    l["nome"], l["contato"] or "", l["segmento_rotulo"], l["email"], l["telefone"], l["notas_mes_rotulo"] or "",
                    {True: "Sim", False: "Não"}[bool(l["aceita_whatsapp"])] if l["campanha"] else "",
                    ETAPAS.get(l["etapa"], l["etapa"]), situacao,
                    _br(e["teste_ate"]) if e and e["teste_ate"] else "",
                    {True: "Sim", False: "Não", None: ""}[l["primeiro_acesso_feito"]],
                    envio.get(l["email_status"], l["email_status"]) if not l["campanha"] else "", l["origem"] or "", l["observacoes"] or ""])
    nome = f"leads_contask_{regras.hoje().strftime('%Y-%m-%d')}.csv"
    return Response(("﻿" + saida.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


class EdicaoLead(BaseModel):
    etapa: str | None = None
    observacoes: str | None = Field(None, max_length=4000)


def _lead(db: Session, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "Lead não encontrado.")
    return lead


@painel.put("/{lead_id}")
def editar(lead_id: int, d: EdicaoLead, db: Session = Depends(sessao), _adm: Usuario = Depends(exigir_admin)):
    lead = _lead(db, lead_id)
    if "etapa" in d.model_fields_set:
        if d.etapa not in ETAPAS:
            raise HTTPException(422, "Etapa inválida.")
        lead.etapa = d.etapa
    if "observacoes" in d.model_fields_set:
        lead.observacoes = (d.observacoes or "").strip() or None
    db.commit()
    return {"id": lead.id, "etapa": lead.etapa, "observacoes": lead.observacoes}


@painel.post("/{lead_id}/reenviar")
def reenviar(lead_id: int, db: Session = Depends(sessao), _adm: Usuario = Depends(exigir_admin)):
    """Gera uma senha provisória nova e envia de novo o e-mail de acesso."""
    lead = _lead(db, lead_id)
    u = db.get(Usuario, lead.usuario_id) if lead.usuario_id else None
    if u is None:
        raise HTTPException(409, "Este lead não tem conta criada pelo formulário.")
    if not correio.configurado():
        raise HTTPException(409, "O e-mail do sistema não está configurado no servidor.")
    senha = auth.senha_aleatoria()
    u.senha_hash, u.trocar_senha, u.ativo = auth.gerar_hash(senha), True, True
    auth.encerrar_sessoes(db, u.id)
    db.commit()
    status = enviar_acesso(lead.id, senha)
    db.expire_all()
    lead = _lead(db, lead_id)
    if status != "enviado":
        raise HTTPException(502, lead.email_erro or "Não foi possível enviar o e-mail.")
    return {"email_status": status}
