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
    keyring_servico: str = "ContaskNF"

    # Servidor na internet (instância de um escritório)
    # Domínio público (ex.: escritorio.contasknf.com.br): libera Host e Origin https://<dominio>.
    dominio: str | None = None
    # Chave-mestra fora do keyring do Windows: valor direto ou arquivo (criado na primeira abertura).
    chave_mestra: SecretStr | None = None
    chave_mestra_arquivo: Path | None = None
    # Login obrigatório. Ligado sempre que o servidor escuta fora de 127.0.0.1.
    login: bool = False
    sessao_dias: int = 14
    cookie_seguro: bool = False  # só HTTPS (ligar atrás do Caddy)
    # Limite mensal de XMLs novos baixados (0 = sem limite). A carga inicial do histórico não conta.
    limite_xmls_mes: int = 0

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
    def hosts_permitidos(self) -> set[str]:
        hosts = {f"127.0.0.1:{self.porta}", f"localhost:{self.porta}", "127.0.0.1", "localhost"}
        if self.dominio:
            hosts.add(self.dominio.lower())
        return hosts

    @property
    def origens_permitidas(self) -> set[str]:
        base = {f"http://127.0.0.1:{self.porta}", f"http://localhost:{self.porta}"}
        if self.dominio:
            base.add(f"https://{self.dominio.lower()}")
        return base | set(self.origens_extras)

    @property
    def login_ativo(self) -> bool:
        return self.login or self.host not in ("127.0.0.1", "localhost")


@lru_cache
def config() -> Config:
    return Config()
