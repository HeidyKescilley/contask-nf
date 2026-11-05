from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig

from app.core.config import config

BACKEND = Path(__file__).resolve().parents[2]


def migrar() -> None:
    """Aplica as migrações pendentes (alembic upgrade head)."""
    cfg = config()
    cfg.dados_dir.mkdir(parents=True, exist_ok=True)
    ac = AlembicConfig(str(BACKEND / "alembic.ini"))
    ac.set_main_option("script_location", str(BACKEND / "migrations"))
    ac.set_main_option("sqlalchemy.url", cfg.db_url)
    ac.attributes["configurar_log"] = False
    command.upgrade(ac, "head")
