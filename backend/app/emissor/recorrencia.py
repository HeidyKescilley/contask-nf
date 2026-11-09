"""Notas recorrentes: emissão automática todo mês no dia escolhido.

Regras de segurança:
- Uma recorrência emite no máximo uma nota por mês. A próxima data é avançada e gravada ANTES do envio,
  então uma falha no meio nunca gera nota em dobro.
- Mês perdido (sistema desligado no dia) não é emitido em atraso no mês seguinte: fica registrado o aviso.
  Dentro do mesmo mês, a nota sai na primeira verificação depois do dia.
- Erro antes de reservar o número (cadastro incompleto, certificado vencido…) não gasta número: a
  recorrência tenta de novo nas próximas verificações do mesmo mês.
- O ambiente é o da empresa (homologação ou produção), como em qualquer emissão.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.emissor import textos
from app.emissor.dps import BRASILIA
from app.models import NotaEmitida, NotaRecorrente, agora

log = logging.getLogger("contask.recorrencia")

HORA_INICIO = 7          # não emite de madrugada (horário de Brasília)
INTERVALO_S = 10 * 60
_trava = threading.Lock()


def hoje_brasilia() -> date:
    return datetime.now(BRASILIA).date()


def competencia_para(rec: NotaRecorrente, emissao: date) -> date:
    if rec.competencia == "anterior":
        return emissao.replace(day=1) - timedelta(days=1)  # último dia do mês anterior
    return emissao


def calcular_proxima(rec: NotaRecorrente, hoje: date) -> date:
    """Próxima data estritamente futura, sem repetir o mês da última emissão."""
    d = textos.proxima_data(rec.dia, hoje, incluir=False)
    if rec.ultima_em is not None and rec.ultima_nota_id is not None:
        u = rec.ultima_em if rec.ultima_em.tzinfo else rec.ultima_em.replace(tzinfo=timezone.utc)  # SQLite: UTC sem fuso
        u = u.astimezone(BRASILIA).date()
        if (u.year, u.month) == (d.year, d.month):
            d = textos.proxima_data(rec.dia, textos.dia_no_mes(d.year, d.month, 31), incluir=False)
    return d


def entrada(rec: NotaRecorrente, emissao: date):
    """Entrada do motor com as variáveis aplicadas. HTTPException do validador vira ErroEmissao."""
    from fastapi import HTTPException
    from app.api.emissor import EmissaoIn, _entrada
    from app.emissor.motor import ErroEmissao
    dados = {k: v for k, v in (rec.dados or {}).items() if k not in ("empresa_id", "competencia", "rascunho_id")}
    dados["descricao"] = textos.aplicar(dados.get("descricao"), emissao)
    if dados.get("info_complementar"):
        dados["info_complementar"] = textos.aplicar(dados["info_complementar"], emissao)
    try:
        ent = _entrada(EmissaoIn(**dados, empresa_id=rec.empresa_id, competencia=competencia_para(rec, emissao)))
    except HTTPException as ex:
        raise ErroEmissao(str(ex.detail)) from None
    except ValueError as ex:  # pydantic
        raise ErroEmissao(f"Dados da recorrência inválidos: {ex}") from None
    ent.recorrente_id = rec.id
    ent.salvar_tomador = False
    return ent


def executar(db: Session, rec: NotaRecorrente, hoje: date) -> NotaEmitida | None:
    """Emite a nota do mês. Devolve a nota criada ou None (erro anotado em rec.ultimo_erro)."""
    from app.emissor import motor
    prevista = rec.proxima_em
    rec.proxima_em = textos.proxima_data(rec.dia, hoje, incluir=False)
    rec.ultima_em = agora()
    db.commit()  # avançada antes do envio: nunca emite duas vezes no mês
    try:
        nota = motor.emitir(db, rec.escritorio_id, rec.usuario_id, entrada(rec, hoje))
    except motor.ErroEmissao as ex:
        db.rollback()
        rec = db.get(NotaRecorrente, rec.id)
        rec.proxima_em = prevista  # nada foi enviado: tenta de novo na próxima verificação
        rec.ultimo_erro = str(ex)
        db.commit()
        log.warning("Recorrência %s não emitida: %s", rec.id, ex)
        return None
    except Exception:  # noqa: BLE001 - resultado desconhecido: não tenta de novo sozinho
        log.exception("Falha inesperada na recorrência %s", rec.id)
        db.rollback()
        rec = db.get(NotaRecorrente, rec.id)
        rec.ultimo_erro = "Falha inesperada na emissão. Confira as notas emitidas antes de emitir manualmente."
        db.commit()
        return None
    rec.ultima_nota_id = nota.id
    rec.ultimo_erro = None if nota.situacao == "autorizada" else (nota.mensagem or "A nota não foi autorizada.")
    db.commit()
    return nota


def executar_pendentes(db: Session, hoje: date | None = None) -> list[int]:
    """Roda as recorrências vencidas. Devolve os ids das notas criadas."""
    hoje = hoje or hoje_brasilia()
    criadas: list[int] = []
    with _trava:
        ids = list(db.scalars(select(NotaRecorrente.id).where(NotaRecorrente.ativa, NotaRecorrente.proxima_em <= hoje)))
        for rid in ids:
            rec = db.get(NotaRecorrente, rid)
            if rec is None or not rec.ativa or rec.proxima_em is None or rec.proxima_em > hoje:
                continue
            if rec.proxima_em < hoje.replace(day=1):
                # Mês perdido: não emite atrasado
                rec.ultimo_erro = (f"A nota de {rec.proxima_em:%m/%Y} não foi emitida: o sistema estava desligado no dia "
                                   f"{rec.proxima_em:%d/%m/%Y}. Emita manualmente se precisar.")
                rec.proxima_em = textos.dia_no_mes(hoje.year, hoje.month, rec.dia)
                db.commit()
                if rec.proxima_em > hoje:
                    continue
            nota = executar(db, rec, hoje)
            if nota is not None:
                criadas.append(nota.id)
    return criadas


class Agendador:
    """Thread que confere as recorrências a cada 10 minutos (a partir das 7h de Brasília)."""

    def __init__(self, fabrica_sessao: Callable[[], Session], intervalo_s: int = INTERVALO_S):
        self._fabrica = fabrica_sessao
        self._intervalo = intervalo_s
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    def iniciar(self) -> None:
        self._thread = threading.Thread(target=self._laco, name="recorrencias", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _laco(self) -> None:
        if self._parar.wait(30):
            return
        while not self._parar.is_set():
            if datetime.now(BRASILIA).hour >= HORA_INICIO:
                try:
                    with self._fabrica() as db:
                        criadas = executar_pendentes(db)
                    if criadas:
                        log.info("Recorrências: %d nota(s) emitida(s).", len(criadas))
                except Exception:  # noqa: BLE001
                    log.exception("Falha ao conferir as recorrências")
            self._parar.wait(self._intervalo)
