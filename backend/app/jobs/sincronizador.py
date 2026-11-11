"""Executa um job de busca: percorre a distribuição do ADN a partir do último NSU salvo.

Garantias:
- NSU exclusivo: a próxima chamada usa o maior NSU recebido (nunca +1).
- Em cada página: grava os arquivos, depois banco + NSU numa única transação. Se algo falhar, o NSU
  não avança e a página é refeita na próxima vez (unicidade de (empresa, nsu) e (empresa, chave)).
- Status da nota vem só dos eventos, recalculado por chave a cada página.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adn.cliente import (
    ClienteADN, DocDFe, ErroADN, ErroCertificadoADN, ErroProcuracao, ErroTemporario, RespostaDFe,
)
from app.core.certificados import carregar_pfx, situacao_validade
from app.core.config import config
from app.core.uso import limite_atingido, restante_teste
from app.fiscal.parser import XmlInvalido, parse_evento, parse_nfse
from app.fiscal.status import DESCRICOES, EventoStatus, calcular_status
from app.models import BuscaJob, BuscaLog, Certificado, DocumentoDfe, Empresa, EventoNota, Nota, SyncEstado
from .barramento import barramento

log = logging.getLogger("contask.busca")

FabricaCliente = Callable[[bytes, str], ClienteADN]


def agora() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Contexto:
    fabrica: FabricaCliente
    pausa: float = 1.5
    dormir: Callable[[float], None] = lambda s: threading.Event().wait(s)
    deve_parar: Callable[[], bool] = lambda: False  # desligamento do sistema
    publicar: Callable[[dict], None] = field(default=barramento.publicar)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def certificado_da_empresa(db: Session, e: Empresa) -> Certificado | None:
    if e.modo_certificado == "contabilidade" and not e.is_contabilidade:
        c = db.scalar(select(Empresa).where(Empresa.escritorio_id == e.escritorio_id, Empresa.is_contabilidade))
        return db.get(Certificado, c.certificado_id) if c and c.certificado_id else None
    return db.get(Certificado, e.certificado_id) if e.certificado_id else None


def _gravar(caminho: Path, dados: bytes) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_bytes(dados)
    os.replace(tmp, caminho)


def _rel(p: Path) -> str:
    return p.relative_to(config().dados_dir).as_posix()


def registrar(db: Session, job: BuscaJob, mensagem: str, nivel: str = "info") -> None:
    db.add(BuscaLog(job_id=job.id, momento=agora(), nivel=nivel, mensagem=mensagem))


def resumo_job(db: Session, job: BuscaJob) -> dict:
    sync = db.get(SyncEstado, job.empresa_id)
    empresa = db.get(Empresa, job.empresa_id)
    return {
        "tipo": "job", "id": job.id, "empresa_id": job.empresa_id, "status": job.status, "tipo_job": job.tipo,
        "paginas": job.paginas, "docs_recebidos": job.docs_recebidos, "notas_ok": job.notas_ok,
        "eventos_ok": job.eventos_ok, "docs_com_erro": job.docs_com_erro, "eventos_sem_nota": job.eventos_sem_nota,
        "ultimo_nsu": job.ultimo_nsu, "mensagem": job.mensagem,
        "situacao_empresa": sync.situacao if sync else None,
        "escritorio_id": empresa.escritorio_id if empresa else None,
    }


def recalcular_status(db: Session, empresa_id: int, chaves: set[str]) -> None:
    if not chaves:
        return
    notas = {n.chave: n for n in db.scalars(select(Nota).where(Nota.empresa_id == empresa_id, Nota.chave.in_(chaves)))}
    eventos: dict[str, list[EventoStatus]] = {}
    for ev in db.scalars(select(EventoNota).where(EventoNota.empresa_id == empresa_id, EventoNota.chave.in_(chaves))):
        eventos.setdefault(ev.chave, []).append(EventoStatus(ev.codigo, ev.data_evento, ev.nsu))
    for chave, nota in notas.items():
        s = calcular_status(eventos.get(chave, []))
        nota.status, nota.status_detalhe = s.status, s.detalhe
        nota.em_analise_fiscal, nota.bloqueada = s.em_analise_fiscal, s.bloqueada


def contar_eventos_sem_nota(db: Session, empresa_id: int) -> int:
    return db.scalar(
        select(func.count(func.distinct(EventoNota.chave))).where(
            EventoNota.empresa_id == empresa_id,
            ~select(Nota.id).where(Nota.empresa_id == empresa_id, Nota.chave == EventoNota.chave).exists(),
        )) or 0


# ---------------------------------------------------------------------------
# Processamento de uma página
# ---------------------------------------------------------------------------

@dataclass
class ResultadoPagina:
    recebidos: int = 0
    novos: int = 0
    notas: int = 0
    eventos: int = 0
    erros: int = 0


def processar_documento(db: Session, empresa: Empresa, doc: DocDFe, chaves: set[str], r: ResultadoPagina) -> None:
    base = config().dados_dir / "empresas" / empresa.cnpj
    existente = db.scalar(select(DocumentoDfe).where(DocumentoDfe.empresa_id == empresa.id, DocumentoDfe.nsu == doc.nsu))
    if existente is not None and existente.processado:
        return  # já veio antes (retomada ou "refazer"): nada a fazer
    reg = existente or DocumentoDfe(empresa_id=empresa.id, nsu=doc.nsu)
    reg.chave, reg.tipo_documento, reg.tipo_evento, reg.gerado_em = doc.chave, doc.tipo_documento, doc.tipo_evento, doc.gerado_em
    reg.processado, reg.erro_processamento = False, None
    if existente is None:
        db.add(reg)
    r.novos += 1

    if doc.xml is None:
        reg.erro_processamento = doc.erro or "Documento sem XML."
        r.erros += 1
        return
    reg.sha256 = hashlib.sha256(doc.xml).hexdigest()

    try:
        if doc.tipo_documento == "NFSE":
            d = parse_nfse(doc.xml)
            caminho = base / "xml" / d.mes_arquivo / f"{d.chave}.xml"
            _gravar(caminho, doc.xml)
            reg.xml_path, reg.chave = _rel(caminho), d.chave
            nota = db.scalar(select(Nota).where(Nota.empresa_id == empresa.id, Nota.chave == d.chave))
            if nota is None:
                nota = Nota(empresa_id=empresa.id, chave=d.chave, status="autorizada")
                db.add(nota)
            nota.papel = d.papel(empresa.cnpj)
            nota.numero, nota.serie, nota.n_dps = d.numero, d.serie, d.n_dps
            nota.emitente_doc, nota.emitente_nome, nota.emitente_uf = d.emitente_doc, d.emitente_nome, d.emitente_uf
            nota.prestador_doc, nota.tomador_doc, nota.tomador_nome = d.prestador_doc, d.tomador_doc, d.tomador_nome
            nota.valor_servico, nota.valor_liquido, nota.valor_iss = d.valor_servico, d.valor_liquido, d.valor_iss
            nota.data_emissao, nota.competencia, nota.municipio = d.data_emissao, d.competencia, d.municipio
            nota.c_stat, nota.xml_path, nota.nsu = d.c_stat, _rel(caminho), doc.nsu
            chaves.add(d.chave)
            r.notas += 1
        elif doc.tipo_documento == "EVENTO":
            ev = parse_evento(doc.xml)
            caminho = base / "eventos" / ev.mes_arquivo / f"{ev.chave}_{ev.codigo or 'desconhecido'}_{doc.nsu}.xml"
            _gravar(caminho, doc.xml)
            reg.xml_path, reg.chave = _rel(caminho), ev.chave
            ja = db.scalar(select(EventoNota).where(EventoNota.empresa_id == empresa.id, EventoNota.nsu == doc.nsu))
            if ja is None:
                db.flush()  # garante reg.id
                db.add(EventoNota(empresa_id=empresa.id, chave=ev.chave, codigo=ev.codigo,
                                  descricao=ev.descricao or DESCRICOES.get(ev.codigo or "") or doc.tipo_evento,
                                  data_evento=ev.data_evento, nsu=doc.nsu, documento_id=reg.id))
            chaves.add(ev.chave)
            r.eventos += 1
        else:
            caminho = base / "outros" / f"{doc.nsu}_{doc.tipo_documento or 'desconhecido'}.xml"
            _gravar(caminho, doc.xml)
            reg.xml_path = _rel(caminho)
            reg.erro_processamento = f"Tipo de documento não tratado: {doc.tipo_documento or '(vazio)'}"
            r.erros += 1
            return
        reg.processado = True
    except XmlInvalido as e:
        caminho = base / "com_erro" / f"{doc.nsu}.xml"
        _gravar(caminho, doc.xml)
        reg.xml_path, reg.erro_processamento = _rel(caminho), str(e)
        r.erros += 1


def processar_pagina(db: Session, empresa: Empresa, resp: RespostaDFe) -> ResultadoPagina:
    r = ResultadoPagina(recebidos=len(resp.documentos))
    chaves: set[str] = set()
    for doc in sorted(resp.documentos, key=lambda d: d.nsu):
        processar_documento(db, empresa, doc, chaves, r)
    db.flush()
    recalcular_status(db, empresa.id, chaves)
    return r


# ---------------------------------------------------------------------------
# Execução do job
# ---------------------------------------------------------------------------

def executar_job(job_id: int, sessao_factory: Callable[[], Session], ctx: Contexto) -> str:
    """Devolve o status final do job."""
    with sessao_factory() as db:
        job = db.get(BuscaJob, job_id)
        if job is None or job.status not in ("fila", "rodando"):
            return job.status if job else "inexistente"
        empresa = db.get(Empresa, job.empresa_id)
        sync = db.get(SyncEstado, empresa.id) or SyncEstado(empresa_id=empresa.id, ultimo_nsu=0)
        db.add(sync)

        primeira_vez = job.ultimo_nsu is None
        if job.tipo == "refazer" and primeira_vez:
            sync.ultimo_nsu = 0
            registrar(db, job, "Refazer do zero: a busca recomeça do NSU 0 (documentos já salvos não são duplicados).")
        if job.tipo == "incremental" and sync.ultima_busca_em is None:
            job.tipo = "inicial"  # histórico ainda não terminou (nunca chegou ao fim da fila): não conta no limite
        from app.core.escritorios import em_teste
        if empresa.is_contabilidade and em_teste(db, empresa.escritorio_id):
            job.status, job.finalizado_em = "cancelado", agora()
            job.mensagem = "No teste grátis, só a empresa escolhida é buscada; a contabilidade entra pelo certificado."
            registrar(db, job, job.mensagem)
            db.commit()
            ctx.publicar(resumo_job(db, job))
            return job.status
        job.status, job.iniciado_em = "rodando", job.iniciado_em or agora()
        job.ultimo_nsu = sync.ultimo_nsu
        sync.situacao, sync.ultimo_erro = "buscando", None

        cert = certificado_da_empresa(db, empresa)
        if cert is None or situacao_validade(cert.validade) == "vencido":
            msg = "Sem certificado para a busca." if cert is None else \
                f"Certificado de {cert.titular_nome} vencido em {cert.validade:%d/%m/%Y}."
            return _finalizar_erro(db, job, sync, "erro_certificado", msg, ctx)

        registrar(db, job, f"Início ({job.tipo}) a partir do NSU {sync.ultimo_nsu}, com o certificado de {cert.titular_nome}.")
        db.commit()
        ctx.publicar(resumo_job(db, job))

        try:
            pfx, senha = carregar_pfx(cert)
            cliente = ctx.fabrica(pfx, senha)
            del senha
        except Exception as e:  # noqa: BLE001
            log.exception("Falha ao carregar o certificado")
            return _finalizar_erro(db, job, sync, "erro_certificado", f"Não foi possível carregar o certificado: {type(e).__name__}.", ctx)

        with cliente:
            nsu = sync.ultimo_nsu
            while True:
                db.refresh(job)
                if job.status in ("pausado", "cancelado"):
                    sync.situacao = "em_dia" if sync.ultima_busca_em else "nunca_buscada"
                    registrar(db, job, "Busca pausada." if job.status == "pausado" else "Busca cancelada.")
                    db.commit()
                    ctx.publicar(resumo_job(db, job))
                    return job.status
                if ctx.deve_parar():
                    job.status = "fila"  # retoma do NSU salvo na próxima abertura
                    registrar(db, job, "Sistema encerrado: a busca continua de onde parou na próxima abertura.")
                    db.commit()
                    return job.status

                restante = restante_teste(db, empresa.escritorio_id)
                if restante == 0:
                    return _finalizar_erro(db, job, sync, "limite_teste",
                                           "Teste grátis concluído: os XMLs de demonstração já foram baixados. "
                                           "Assine o plano para liberar o histórico completo e todas as empresas.", ctx)
                if job.tipo == "incremental" and limite_atingido(db, empresa.escritorio_id):
                    return _finalizar_erro(db, job, sync, "limite_mes",
                                           "Limite mensal de XMLs do plano atingido. As buscas voltam no próximo mês "
                                           "ou após ampliar o plano.", ctx)

                def _esperando(msg: str):
                    with sessao_factory() as db2:
                        db2.add(BuscaLog(job_id=job.id, momento=agora(), nivel="aviso", mensagem=msg))
                        db2.commit()
                    ctx.publicar({"tipo": "log", "id": job.id, "empresa_id": empresa.id,
                                  "escritorio_id": empresa.escritorio_id, "nivel": "aviso", "mensagem": msg})

                try:
                    resp = cliente.distribuicao(nsu, cnpj=empresa.cnpj, ao_esperar=_esperando)
                except ErroProcuracao as e:
                    return _finalizar_erro(db, job, sync, "sem_procuracao", str(e), ctx)
                except ErroCertificadoADN as e:
                    _erro_certificado_em_todas(db, cert.id, job.id)
                    return _finalizar_erro(db, job, sync, "erro_certificado", str(e), ctx)
                except (ErroTemporario, ErroADN) as e:
                    return _finalizar_erro(db, job, sync, "erro", str(e), ctx)

                if resp.tipo_consulta:
                    sync.tipo_consulta = resp.tipo_consulta
                if restante is not None and len(resp.documentos) > restante:
                    # Teste: guarda só os primeiros pela ordem do NSU; o NSU salvo para no último guardado,
                    # e a busca continua dele quando o plano for liberado.
                    resp.documentos = sorted(resp.documentos, key=lambda d: d.nsu)[:restante]
                if resp.fim:
                    job.eventos_sem_nota = contar_eventos_sem_nota(db, empresa.id)
                    job.status, job.finalizado_em = "concluido", agora()
                    sync.situacao, sync.ultima_busca_em = "em_dia", agora()
                    registrar(db, job, f"Fim da fila no NSU {nsu}. {job.notas_ok} nota(s) e {job.eventos_ok} evento(s) novos.")
                    db.commit()
                    ctx.publicar(resumo_job(db, job))
                    return job.status

                maior = resp.maior_nsu
                if maior is None or maior <= nsu:
                    return _finalizar_erro(db, job, sync, "erro", f"O ADN devolveu NSU {maior} a partir de {nsu}: resposta inconsistente.", ctx)
                try:
                    r = processar_pagina(db, empresa, resp)
                    sync.ultimo_nsu = maior  # NSU exclusivo: sem +1
                    job.ultimo_nsu = maior
                    job.paginas += 1
                    job.docs_recebidos += r.recebidos
                    job.notas_ok += r.notas
                    job.eventos_ok += r.eventos
                    job.docs_com_erro += r.erros
                    job.eventos_sem_nota = contar_eventos_sem_nota(db, empresa.id)
                    registrar(db, job, f"NSU {nsu + 1}–{maior}: {r.recebidos} documento(s), {r.notas} nota(s), "
                                       f"{r.eventos} evento(s){f', {r.erros} com erro' if r.erros else ''}.")
                    db.commit()
                except Exception as e:  # noqa: BLE001 - a página inteira volta; o NSU não avança
                    db.rollback()
                    log.exception("Falha ao gravar a página")
                    return _finalizar_erro(db, db.get(BuscaJob, job_id), db.get(SyncEstado, empresa.id), "erro",
                                           f"Falha ao gravar a página a partir do NSU {nsu}: {type(e).__name__}: {e}", ctx)
                nsu = maior
                ctx.publicar(resumo_job(db, job))
                ctx.dormir(ctx.pausa)


def _finalizar_erro(db: Session, job: BuscaJob, sync: SyncEstado, situacao: str, msg: str, ctx: Contexto) -> str:
    job.status, job.finalizado_em, job.mensagem = "erro", agora(), msg
    sync.situacao, sync.ultimo_erro = situacao, msg
    registrar(db, job, msg, "erro")
    db.commit()
    ctx.publicar(resumo_job(db, job))
    return job.status


def _erro_certificado_em_todas(db: Session, cert_id: int, job_atual: int) -> None:
    """Certificado recusado: os demais jobs na fila com o mesmo certificado não devem tentar."""
    for j in db.scalars(select(BuscaJob).where(BuscaJob.status == "fila", BuscaJob.id != job_atual)):
        e = db.get(Empresa, j.empresa_id)
        c = certificado_da_empresa(db, e) if e else None
        if c is not None and c.id == cert_id:
            j.status, j.mensagem, j.finalizado_em = "erro", "Certificado recusado pelo ADN em outra busca.", agora()
            s = db.get(SyncEstado, j.empresa_id)
            if s:
                s.situacao, s.ultimo_erro = "erro_certificado", j.mensagem
