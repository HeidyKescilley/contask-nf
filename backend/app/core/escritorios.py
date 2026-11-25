"""Situação e plano de cada escritório (painel de administração).

- suspenso: ninguém do escritório entra; as buscas automáticas e as notas recorrentes param.
- teste: teste grátis até `teste_ate`; vencido, o acesso fica bloqueado (os dados continuam guardados).
  Com CONTASK_TESTE_COMPLETO (servidor online), tudo liberado no período. Sem ele, o teste limitado:
  contabilidade e mais 1 empresa, busca completa, XML avulso fechado, 1 exportação de até 30 dias e 1 emissão.
- ativo: uso normal, com o limite de XMLs do escritório (ou o padrão do sistema).
O bloqueio vale para o sistema (área do cliente). A administração tem login próprio e não depende dele.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import config
from app.models import Escritorio

BRASILIA = timezone(timedelta(hours=-3))
SITUACOES = {"teste", "ativo", "suspenso"}
TIPOS = {"contador", "empresa"}
TIPO_ROTULO = {"contador": "Contador", "empresa": "Empresa"}
# Conta de empresa: um CNPJ só (o da própria empresa, cadastrado como empresa principal da conta)
MSG_CONTA_EMPRESA = ("Sua conta é da sua empresa e tem um CNPJ só. Para cuidar de vários CNPJs, "
                     "fale com o suporte do Contask NF sobre a conta de contador.")
# Frase única de todo recurso fechado no teste grátis
CONTRATE = "Contrate um plano para ter acesso completo ao sistema."


def hoje() -> date:
    return datetime.now(BRASILIA).date()


def motivo_bloqueio(esc: Escritorio | None) -> str | None:
    if esc is None:
        return None
    if esc.situacao == "suspenso":
        return "O acesso do seu escritório está suspenso. Fale com o suporte do Contask NF."
    if esc.situacao == "teste" and esc.teste_ate is not None and esc.teste_ate < hoje():
        return f"O período de teste do seu escritório terminou. {CONTRATE}"
    return None


def bloqueado(db: Session, escritorio_id: int) -> bool:
    return motivo_bloqueio(db.get(Escritorio, escritorio_id)) is not None


def ids_bloqueados(db: Session) -> set[int]:
    return {e.id for e in db.scalars(select(Escritorio)) if motivo_bloqueio(e)}


def conta_empresa(db: Session, escritorio_id: int) -> bool:
    """Conta da própria empresa (não de um escritório de contabilidade)."""
    esc = db.get(Escritorio, escritorio_id)
    return esc is not None and esc.tipo == "empresa"


def exigir_conta_contador(db: Session, escritorio_id: int) -> None:
    """403 na conta de empresa para tudo que cadastra outro CNPJ."""
    if conta_empresa(db, escritorio_id):
        from fastapi import HTTPException
        raise HTTPException(403, MSG_CONTA_EMPRESA)


def em_teste(db: Session, escritorio_id: int) -> bool:
    """Teste com limites: o modo geral (CONTASK_TESTE, instalação de um escritório só) ou o do escritório,
    quando o servidor não libera tudo no teste (CONTASK_TESTE_COMPLETO)."""
    if config().teste:
        return True
    if config().teste_completo:
        return False
    esc = db.get(Escritorio, escritorio_id)
    return esc is not None and esc.situacao == "teste"


def periodo_de_teste(db: Session, escritorio_id: int) -> dict | None:
    """Fim do teste grátis do escritório e os dias que faltam (contando hoje)."""
    esc = db.get(Escritorio, escritorio_id)
    if esc is None or esc.situacao != "teste" or esc.teste_ate is None:
        return None
    return {"ate": esc.teste_ate.isoformat(), "dias_restantes": max((esc.teste_ate - hoje()).days + 1, 0)}


def iniciar_teste(esc: Escritorio, dias: int) -> None:
    """Cadastro pela tela: `dias` dias de teste contando hoje; no dia seguinte ao último, o acesso fecha."""
    esc.situacao = "teste"
    esc.teste_ate = hoje() + timedelta(days=dias - 1)


def limite_xmls(db: Session, escritorio_id: int) -> int:
    """XMLs novos por mês (0 = sem limite): o do escritório ou o padrão do sistema."""
    esc = db.get(Escritorio, escritorio_id)
    if esc is not None and esc.limite_xmls_mes is not None:
        return esc.limite_xmls_mes
    return config().limite_xmls_mes


def no_dia(ano: int, mes: int, dia: int) -> date:
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def mes_seguinte(d: date, dia: int | None = None) -> date:
    """Mesmo dia (ou o dia de vencimento) no mês seguinte; meses curtos usam o último dia."""
    ano, mes = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return no_dia(ano, mes, dia or d.day)


# ---------------------------------------------------------------------------
# Recursos fechados no teste grátis
# ---------------------------------------------------------------------------

MSG_XML = f"No teste grátis dá para ver as notas e abrir o PDF, mas não baixar o XML. {CONTRATE}"


def exportacoes_do_escritorio(db: Session, escritorio_id: int) -> int:
    """Exportações já pedidas (as que deram erro não contam)."""
    from sqlalchemy import func
    from app.models import Empresa, Exportacao
    return int(db.scalar(select(func.count()).select_from(Exportacao).join(Empresa, Empresa.id == Exportacao.empresa_id)
                         .where(Empresa.escritorio_id == escritorio_id, Exportacao.status != "erro")) or 0)


def emissoes_do_escritorio(db: Session, escritorio_id: int) -> int:
    from sqlalchemy import func
    from app.models import NotaEmitida
    return int(db.scalar(select(func.count()).select_from(NotaEmitida)
                         .where(NotaEmitida.escritorio_id == escritorio_id)) or 0)


def exigir_plano(db: Session, escritorio_id: int, mensagem: str = MSG_XML) -> None:
    """402 no teste grátis: o recurso só existe no plano pago."""
    if em_teste(db, escritorio_id):
        from fastapi import HTTPException
        raise HTTPException(402, mensagem)
