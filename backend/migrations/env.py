from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import config as app_config
from app.models import Base

cfg = context.config
if cfg.config_file_name is not None and cfg.attributes.get("configurar_log", True):
    fileConfig(cfg.config_file_name, disable_existing_loggers=False)

if not cfg.get_main_option("sqlalchemy.url"):
    app_config().dados_dir.mkdir(parents=True, exist_ok=True)
    cfg.set_main_option("sqlalchemy.url", app_config().db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=cfg.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(cfg.get_section(cfg.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
