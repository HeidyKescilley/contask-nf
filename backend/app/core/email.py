"""E-mail do sistema (SMTP com SSL; no servidor, a caixa notas@ da Hostinger).

A senha da caixa vem de CONTASK_SMTP_SENHA (segredos/email.env, só root lê) e nunca vai para log.
O conteúdo das mensagens também não vai para log: pode levar a senha inicial de um usuário.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.core.config import config

log = logging.getLogger(__name__)


class ErroEmail(Exception):
    """Mensagem segura para guardar e mostrar no painel (sem senha nem conteúdo)."""


def configurado() -> bool:
    c = config()
    return bool(c.smtp_host and c.email_remetente and c.smtp_senha is not None)


def enviar(para: str, assunto: str, texto: str, html: str | None = None) -> None:
    c = config()
    if not configurado():
        raise ErroEmail("O e-mail do sistema não está configurado.")
    msg = EmailMessage()
    msg["From"] = formataddr((c.email_nome, c.email_remetente))
    msg["To"] = para
    msg["Subject"] = assunto
    msg["Message-ID"] = make_msgid(domain=c.email_remetente.split("@")[-1])
    msg.set_content(texto)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP_SSL(c.smtp_host, c.smtp_porta, context=ssl.create_default_context(), timeout=20) as s:
            s.login(c.smtp_usuario or c.email_remetente, c.smtp_senha.get_secret_value())
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise ErroEmail("O servidor de e-mail recusou o usuário ou a senha da caixa.") from None
    except smtplib.SMTPRecipientsRefused:
        raise ErroEmail("O servidor de e-mail recusou o endereço do destinatário.") from None
    except (smtplib.SMTPException, OSError) as e:
        log.warning("Falha ao enviar e-mail (%s).", type(e).__name__)
        raise ErroEmail(f"Falha ao enviar o e-mail ({type(e).__name__}).") from None
