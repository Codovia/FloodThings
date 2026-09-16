"""
Alembic environment configuration for FloodPulse.

Reads DATABASE_URL from the application configuration (environment
variables / .env) rather than from alembic.ini, so that credentials
are never embedded in a checked-in file.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.session import Base

# Alembic Config object — provides access to alembic.ini values.
config = context.config

# Logging configuration from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLAlchemy MetaData for autogenerate support.
target_metadata = Base.metadata


def _get_url() -> str:
    """Resolve the database URL from environment configuration."""
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it in the environment "
            "or in a .env file before running migrations."
        )
    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given SQL to the script output.
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
