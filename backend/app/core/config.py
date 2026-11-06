"""Configuração da aplicação. Valores podem ser sobrescritos por variáveis CONTASK_* ou .env na raiz."""
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parents[3]


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONTASK_", env_file=RAIZ / ".env", extra="ignore")

    host: str = "127.0.0.1"
    porta: int = 8765
    dados_dir: Path = RAIZ / "dados"
    frontend_dist: Path = RAIZ / "frontend" / "dist"
    # Origens extras aceitas (ex.: servidor do Vite em desenvolvimento)
    origens_extras: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Chave-mestra Fernet em base64. Sem ela a API não sobe.
    chave_mestra: SecretStr | None = None
    # Domínio único, separado por vírgula. Vazio = só localhost.
    hosts: str = ""
    sessao_dias: int = 14
    cookie_secure: bool = False  # CONTASK_COOKIE_SECURE: cookie Secure só no HTTPS
    # Limite mensal de XMLs novos baixados (0 = sem limite). A carga inicial do histórico não conta.
    limite_xmls_mes: int = 0
    # Teste grátis: só 1 empresa (além da contabilidade, que entra só pelo certificado) e no máximo
    # `teste_max_xmls` XMLs no total. Liberado ao desligar CONTASK_TESTE (as buscas continuam do NSU salvo).
    teste: bool = False
    teste_max_xmls: int = 5
    teste_max_empresas: int = 1

    # Motor de busca
    adn_url: str = "https://adn.nfse.gov.br"
    fila_ativa: bool = True
    max_buscas: int = 2
    pausa_paginas: float = 1.5
    intervalo_busca_h: float = 6.0
    buscar_ao_abrir: bool = True

    @property
    def db_url(self) -> str:
        return f"sqlite:///{(self.dados_dir / 'contask.db').as_posix()}"

    @property
    def lista_hosts(self) -> list[str]:
        return [h.strip().lower() for h in self.hosts.split(",") if h.strip()]

    @property
    def hosts_permitidos(self) -> set[str]:
        hosts = {f"127.0.0.1:{self.porta}", f"localhost:{self.porta}", "127.0.0.1", "localhost"}
        hosts.update(self.lista_hosts)
        return hosts

    @property
    def origens_permitidas(self) -> set[str]:
        base = {f"http://127.0.0.1:{self.porta}", f"http://localhost:{self.porta}"}
        for h in self.lista_hosts:
            base.add(f"https://{h}")
        return base | set(self.origens_extras)


@lru_cache
def config() -> Config:
    return Config()
