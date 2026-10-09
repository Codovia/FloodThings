"""Explicit administrator operation, never a public endpoint."""
import argparse
import json
import os
from .locations import DATASET, LocationsUnavailable
from .location_database import database_engine, import_directory
from sqlalchemy.exc import SQLAlchemyError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default=str(DATASET))
    parser.add_argument('--no-activate', action='store_true')
    args = parser.parse_args()
    engine = None
    try:
        engine = database_engine(os.environ.get('LOCATION_DIRECTORY_ADMIN_URL') or os.environ.get('DATABASE_URL'))
        print(json.dumps(import_directory(engine, args.directory, activate=not args.no_activate)))
    except (LocationsUnavailable, SQLAlchemyError):
        parser.exit(1, 'Directory import failed; check source integrity, migration state and administrator configuration. No partial version was activated.\n')
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    main()
