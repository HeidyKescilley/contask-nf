"""Fila de buscas persistida no banco (busca_job) + workers em threads.

- No máximo `max_total` buscas ao mesmo tempo por escritório e 1 por certificado (um certificado da
  contabilidade atende muitas empresas e o limite do ADN é desconhecido). O processo varre todos
  os escritórios.
- Ao abrir: jobs que estavam "rodando" (sistema fechado no meio) voltam para a fila e continuam do NSU salvo;
  e cada empresa ativa ganha uma busca incremental.
- A cada `intervalo_h` horas com o sistema aberto: nova busca incremental das empresas ativas.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.config import config
from app.models import BuscaJob, Empresa, SyncEstado
from .barramento import barramento
from .sincronizador import Contexto, FabricaCliente, certificado_da_empresa, executar_job, resumo_job

log = logging.getLogger("contask.fila")

PENDENTES = ("fila", "rodando", "pausado")


class JobEmAndamento(Exception):
    pass


def enfileirar(db: Session, empresa_id: int, tipo: str) -> BuscaJob:
    """Cria um job ou reaproveita o pendente. Não faz commit."""
    pend = db.scalar(select(BuscaJob).where(BuscaJob.empresa_id == empresa_id, BuscaJob.status.in_(PENDENTES))
                     .order_by(BuscaJob.id.desc()))
    if pend is not None:
        if tipo == "refazer" and pend.tipo != "refazer":
            if pend.status == "rodando":
                raise JobEmAndamento("Há uma busca em andamento. Pause-a antes de refazer do zero.")
            pend.tipo, pend.ultimo_nsu, pend.status, pend.mensagem = "refazer", None, "fila", None
        elif pend.status == "pausado":
            pend.status = "fila"
        return pend
    job = BuscaJob(empresa_id=empresa_id, tipo=tipo, status="fila")
    db.add(job)
    db.flush()
    s = db.get(SyncEstado, empresa_id)
    if s is None:
        db.add(SyncEstado(empresa_id=empresa_id, ultimo_nsu=0, situacao="nunca_buscada"))
    return job


class Gerenciador:
    def __init__(self, sessao_factory: Callable[[], Session], fabrica: FabricaCliente, *, max_total: int = 2,
                 pausa: float = 1.5, intervalo_h: float = 6.0, tick: float = 1.0,
                 dormir: Callable[[float], None] | None = None, buscar_ao_abrir: bool = True):
        self._sf = sessao_factory
        self._fabrica = fabrica
        self._max = max_total  # teto por escritório, não do processo inteiro
        self._pausa = pausa
        self._intervalo = timedelta(hours=intervalo_h)
        self._tick = tick
        self._dormir = dormir
        self._buscar_ao_abrir = buscar_ao_abrir
        self._lock = threading.Lock()
        self._rodando: dict[int, tuple[int, str]] = {}  # job_id -> (escritorio_id, chave do certificado)
        self._parar = threading.Event()
        self._acordar = threading.Event()
        self._pool = ThreadPoolExecutor(max_workers=32, thread_name_prefix="busca")
        self._thread: threading.Thread | None = None
        self._proxima_periodica = datetime.now(timezone.utc) + self._intervalo

    # --- ciclo de vida ------------------------------------------------------------

    def iniciar(self) -> None:
        with self._sf() as db:
            for j in db.scalars(select(BuscaJob).where(BuscaJob.status == "rodando")):
                j.status = "fila"
                log.info("Job %s retomado após encerramento.", j.id)
            db.commit()
        if self._buscar_ao_abrir:
            self.enfileirar_incrementais()
        self._thread = threading.Thread(target=self._laco, name="fila-buscas", daemon=True)
        self._thread.start()

    def parar(self, esperar: float = 10.0) -> None:
        self._parar.set()
        self._acordar.set()
        if self._thread:
            self._thread.join(timeout=esperar)
        self._pool.shutdown(wait=True, cancel_futures=True)

    def acordar(self) -> None:
        self._acordar.set()

    @property
    def em_execucao(self) -> dict[int, str]:
        with self._lock:
            return {jid: chave for jid, (_eid, chave) in self._rodando.items()}

    # --- agendamento ----------------------------------------------------------------

    def enfileirar_incrementais(self) -> int:
        n = 0
        with self._sf() as db:
            from app.core.escritorios import em_teste, ids_bloqueados
            bloqueados = ids_bloqueados(db)
            for e in db.scalars(select(Empresa).where(Empresa.ativa)):
                if e.escritorio_id in bloqueados:
                    continue  # escritório suspenso ou com o teste vencido: sem busca automática
                if e.is_contabilidade and em_teste(db, e.escritorio_id):
                    continue
                if db.scalar(select(BuscaJob.id).where(BuscaJob.empresa_id == e.id, BuscaJob.status.in_(PENDENTES))):
                    continue
                enfileirar(db, e.id, "incremental")
                n += 1
            db.commit()
        self.acordar()
        return n

    def _laco(self) -> None:
        while not self._parar.is_set():
            try:
                if datetime.now(timezone.utc) >= self._proxima_periodica:
                    self._proxima_periodica = datetime.now(timezone.utc) + self._intervalo
                    self.enfileirar_incrementais()
                self._despachar()
            except Exception:  # noqa: BLE001
                log.exception("Erro no laço da fila")
            self._acordar.wait(self._tick)
            self._acordar.clear()

    def _despachar(self) -> None:
        with self._lock:
            por_escritorio: dict[int, int] = {}
            ocupados: set[str] = set()
            for eid, chave in self._rodando.values():
                por_escritorio[eid] = por_escritorio.get(eid, 0) + 1
                ocupados.add(chave)
            with self._sf() as db:
                from app.core.escritorios import ids_bloqueados
                bloqueados = ids_bloqueados(db)
                prioridade = case((BuscaJob.tipo == "incremental", 1), else_=0)
                for job in db.scalars(select(BuscaJob).where(BuscaJob.status == "fila")
                                      .order_by(prioridade, BuscaJob.criado_em, BuscaJob.id)):
                    if job.id in self._rodando:
                        continue
                    e = db.get(Empresa, job.empresa_id)
                    if e is None or e.escritorio_id in bloqueados or por_escritorio.get(e.escritorio_id, 0) >= self._max:
                        continue
                    cert = certificado_da_empresa(db, e)
                    chave = f"cert:{cert.id}" if cert else f"empresa:{job.empresa_id}"
                    if chave in ocupados:
                        continue
                    ocupados.add(chave)
                    por_escritorio[e.escritorio_id] = por_escritorio.get(e.escritorio_id, 0) + 1
                    self._rodando[job.id] = (e.escritorio_id, chave)
                    self._pool.submit(self._executar, job.id)

    def _executar(self, job_id: int) -> None:
        ctx = Contexto(fabrica=self._fabrica, pausa=self._pausa, deve_parar=self._parar.is_set,
                       publicar=barramento.publicar,
                       dormir=self._dormir or (lambda s: self._parar.wait(s)))
        try:
            executar_job(job_id, self._sf, ctx)
        except Exception:  # noqa: BLE001
            log.exception("Job %s falhou de forma inesperada", job_id)
            with self._sf() as db:
                j = db.get(BuscaJob, job_id)
                if j and j.status == "rodando":
                    j.status, j.mensagem = "erro", "Falha inesperada. Veja o log do servidor."
                    s = db.get(SyncEstado, j.empresa_id)
                    if s:
                        s.situacao, s.ultimo_erro = "erro", j.mensagem
                    db.commit()
                    barramento.publicar(resumo_job(db, j))
        finally:
            with self._lock:
                self._rodando.pop(job_id, None)
            self.acordar()
