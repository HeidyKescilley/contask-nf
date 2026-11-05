"""ADN simulado (httpx.MockTransport) e geradores de XML no leiaute nacional, com dados fictícios."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import random
import threading
import time
from dataclasses import dataclass, field

import httpx

NS = "http://www.sped.fazenda.gov.br/nfse"


def chave_fake(seq: int, cnpj: str = "11444777000161") -> str:
    return f"5300108{cnpj}{seq:029d}"[:50]


def nfse_xml(chave: str, *, prest: str, toma: str | None, valor: str = "100.00", numero: int = 1,
             dh: str = "2026-10-05T10:00:00-03:00", nome_emit: str = "PRESTADOR FICTICIO LTDA") -> bytes:
    tomador = f"<toma><CNPJ>{toma}</CNPJ><xNome>TOMADOR FICTICIO</xNome></toma>" if toma else ""
    return f"""<?xml version="1.0" encoding="utf-8"?><NFSe versao="1.00" xmlns="{NS}"><infNFSe Id="NFS{chave}">
<xLocPrestacao>Brasilia</xLocPrestacao><nNFSe>{numero}</nNFSe><cStat>100</cStat><dhProc>{dh}</dhProc>
<emit><CNPJ>{prest}</CNPJ><xNome>{nome_emit}</xNome><enderNac><UF>DF</UF></enderNac></emit>
<valores><vLiq>{valor}</vLiq><vISSQN>2.00</vISSQN></valores>
<DPS versao="1.00"><infDPS Id="DPS1"><dhEmi>{dh}</dhEmi><serie>1</serie><nDPS>{numero}</nDPS><dCompet>{dh[:10]}</dCompet>
<prest><CNPJ>{prest}</CNPJ></prest>{tomador}<valores><vServPrest><vServ>{valor}</vServ></vServPrest></valores>
</infDPS></DPS></infNFSe></NFSe>""".encode()


def evento_xml(chave: str, codigo: str, *, dh: str = "2026-10-06T10:00:00-03:00", descricao: str | None = None) -> bytes:
    desc = descricao or {"101101": "Cancelamento de NFS-e",
                         "101103": "Solicitação de Análise Fiscal para Cancelamento de NFS-e",
                         "105105": "Cancelamento de NFS-e Indeferido por Análise Fiscal"}.get(codigo, "Evento")
    return f"""<?xml version="1.0" encoding="utf-8"?><evento versao="1.01" xmlns="{NS}"><infEvento Id="EVT{chave}{codigo}001">
<nSeqEvento>1</nSeqEvento><dhProc>{dh}</dhProc><pedRegEvento versao="1.01"><infPedReg Id="PRE{chave}{codigo}">
<dhEvento>{dh}</dhEvento><chNFSe>{chave}</chNFSe><e{codigo}><xDesc>{desc}</xDesc></e{codigo}></infPedReg></pedRegEvento>
</infEvento></evento>""".encode()


TIPOS_EVENTO = {"101101": "CANCELAMENTO", "101103": "SOLICITACAO_CANCELAMENTO_ANALISE_FISCAL",
                "105105": "CANCELAMENTO_INDEFERIDO_ANALISE_FISCAL", "105104": "CANCELAMENTO_DEFERIDO_ANALISE_FISCAL"}


@dataclass
class Doc:
    nsu: int
    tipo: str  # NFSE | EVENTO
    chave: str
    xml: bytes
    tipo_evento: str | None = None


class FalhaSimulada(Exception):
    """Simula o processo morrendo no meio (não é tratada pelo cliente)."""


@dataclass
class ADNSimulado:
    lote: int = 50
    atraso: float = 0.0
    docs: dict[str, list[Doc]] = field(default_factory=dict)
    sem_procuracao: set[str] = field(default_factory=set)
    roteiro: list[str] = field(default_factory=list)  # "429:7", "503", "rede", "tls", "morrer"
    chamadas: list[tuple[str, int]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    ativos_por_cert: dict[str, int] = field(default_factory=dict)
    max_por_cert: dict[str, int] = field(default_factory=dict)
    ativos_total: int = 0
    max_total: int = 0

    # --- montagem ---------------------------------------------------------------
    def adicionar(self, cnpj: str, tipo: str, chave: str, xml: bytes, tipo_evento: str | None = None) -> int:
        lista = self.docs.setdefault(cnpj, [])
        nsu = len(lista) + 1
        lista.append(Doc(nsu, tipo, chave, xml, tipo_evento))
        return nsu

    def adicionar_nota(self, cnpj: str, chave: str, **kw) -> int:
        return self.adicionar(cnpj, "NFSE", chave, nfse_xml(chave, prest=cnpj, toma=kw.pop("toma", "33000167000101"), **kw))

    def adicionar_evento(self, cnpj: str, chave: str, codigo: str, **kw) -> int:
        return self.adicionar(cnpj, "EVENTO", chave, evento_xml(chave, codigo, **kw), TIPOS_EVENTO.get(codigo, "OUTRO"))

    # --- transporte -----------------------------------------------------------------
    def fabrica(self, pfx: bytes, senha: str):
        from app.adn.cliente import ClienteADN
        cert = hashlib.sha256(pfx).hexdigest()[:12]
        return ClienteADN(base_url="https://adn.simulado", transport=httpx.MockTransport(lambda r: self._responder(r, cert)),
                          dormir=lambda s: None)

    def _responder(self, req: httpx.Request, cert: str) -> httpx.Response:
        with self._lock:
            acao = self.roteiro.pop(0) if self.roteiro else None
            self.ativos_por_cert[cert] = self.ativos_por_cert.get(cert, 0) + 1
            self.max_por_cert[cert] = max(self.max_por_cert.get(cert, 0), self.ativos_por_cert[cert])
            self.ativos_total += 1
            self.max_total = max(self.max_total, self.ativos_total)
        try:
            if self.atraso:
                time.sleep(self.atraso * (0.5 + random.random()))
            return self._resposta(req, acao)
        finally:
            with self._lock:
                self.ativos_por_cert[cert] -= 1
                self.ativos_total -= 1

    def _resposta(self, req: httpx.Request, acao: str | None) -> httpx.Response:
        if acao == "morrer":
            raise FalhaSimulada("processo encerrado no meio da busca")
        if acao == "rede":
            raise httpx.ConnectError("conexão recusada", request=req)
        if acao == "tls":
            raise httpx.ReadError("[SSL: RECORD_LAYER_FAILURE] record layer failure (_ssl.c:2713)", request=req)
        if acao and acao.startswith("429"):
            h = {"Retry-After": acao.split(":")[1]} if ":" in acao else {}
            return httpx.Response(429, headers=h, text="Too Many Requests")
        if acao and acao.isdigit():
            return httpx.Response(int(acao), text="erro")

        assert req.url.path.startswith("/contribuintes/DFe/")
        nsu = int(req.url.path.rsplit("/", 1)[1])
        cnpj = req.url.params.get("cnpjConsulta")
        assert cnpj, "cnpjConsulta é obrigatório"
        assert req.url.params.get("lote") == "true"
        self.chamadas.append((cnpj, nsu))
        base = {"TipoAmbiente": "PRODUCAO", "VersaoAplicativo": "1.0.0.0", "Alertas": []}
        if cnpj in self.sem_procuracao:
            return httpx.Response(400, json={**base, "TipoConsulta": "InscricaoCertificado", "StatusProcessamento": "REJEICAO",
                                             "LoteDFe": [], "Erros": [{"Codigo": "E2245", "Descricao": f"Não há procuração da inscrição X para a inscrição {cnpj}."}]})
        lote = [d for d in self.docs.get(cnpj, []) if d.nsu > nsu][: self.lote]  # NSU exclusivo
        if not lote:
            return httpx.Response(404, json={**base, "TipoConsulta": "Procuracao", "StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO",
                                             "LoteDFe": [], "Erros": [{"Codigo": "E2220", "Descricao": "Nenhum documento localizado"}]})
        return httpx.Response(200, json={**base, "TipoConsulta": "Procuracao", "StatusProcessamento": "DOCUMENTOS_LOCALIZADOS", "Erros": [],
                                         "LoteDFe": [{"NSU": d.nsu, "ChaveAcesso": d.chave, "TipoDocumento": d.tipo, "TipoEvento": d.tipo_evento,
                                                      "ArquivoXml": base64.b64encode(gzip.compress(d.xml)).decode(),
                                                      "DataHoraGeracao": "2026-10-06T10:00:00.123"} for d in lote]})


def resposta_json(r: httpx.Response) -> dict:
    return json.loads(r.content)
