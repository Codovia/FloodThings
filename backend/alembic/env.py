"""Credentials come only from environment, not alembic.ini or output."""
import os
from alembic import context
from app.location_database import database_engine, metadata

engine = database_engine(os.environ.get('LOCATION_DIRECTORY_ADMIN_URL') or os.environ.get('DATABASE_URL'))
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
