"""Barramento em memória: os workers (threads) publicam, o SSE (asyncio) consome."""
from __future__ import annotations

import asyncio
import threading
from typing import Any


class Barramento:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._assinantes: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()

    def assinar(self) -> tuple[asyncio.AbstractEventLoop, asyncio.Queue]:
        item = (asyncio.get_running_loop(), asyncio.Queue(maxsize=500))
        with self._lock:
            self._assinantes.add(item)
        return item

    def cancelar(self, item) -> None:
        with self._lock:
            self._assinantes.discard(item)

    def publicar(self, evento: dict[str, Any]) -> None:
        with self._lock:
            assinantes = list(self._assinantes)
        for loop, fila in assinantes:
            def _por(f=fila):
                if f.full():  # cliente lento: descarta o mais antigo
                    f.get_nowait()
                f.put_nowait(evento)
            try:
                loop.call_soon_threadsafe(_por)
            except RuntimeError:
                self.cancelar((loop, fila))


barramento = Barramento()
