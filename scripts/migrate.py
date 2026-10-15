"""Explicit, versioned database migration runner. Never called by app startup."""

import argparse
import hashlib
import importlib.util
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    inspect,
    select,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.types import TypeDecorator


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = Path(__file__).resolve().parent / "migrations" / "0001_subscription_foundation.py"
PG_ADVISORY_LOCK_KEY = 0x4153495355425343  # Stable signed 64-bit key for this app's migration runner.
SCHEMA_METADATA = MetaData()


class _UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value


schema_migrations = Table(
    "schema_migrations",
    SCHEMA_METADATA,
    Column("version", String(32), primary_key=True),
    Column("name", String(160), nullable=False),
    Column("checksum", String(64), nullable=False),
    Column("applied_at", _UTCDateTime(), nullable=False),
)


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    checksum: str
    module: object
    expected_tables: tuple = ()


def _load_migration():
    spec = importlib.util.spec_from_file_location("subscription_migration_0001", MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the Stage 1 migration module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected_tables = tuple(module.expected_tables())

    digest = hashlib.sha256(MIGRATION_PATH.read_bytes())
    # The migration creates ORM table metadata. Include the resulting SQLite
    # and PostgreSQL DDL in the checksum so model-constraint edits cannot leave
    # an already-applied revision looking unchanged.
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        for table in expected_tables:
            digest.update(str(CreateTable(table).compile(dialect=dialect)).encode("utf-8"))
            for index in sorted(table.indexes, key=lambda item: item.name or ""):
                digest.update(str(CreateIndex(index).compile(dialect=dialect)).encode("utf-8"))
    return Migration(
        version=module.VERSION,
        name=module.NAME,
        checksum=digest.hexdigest(),
        module=module,
        expected_tables=expected_tables,
    )


def _migration_registry():
    migrations = (_load_migration(),)
    versions = [migration.version for migration in migrations]
    if versions != sorted(set(versions)):
        raise RuntimeError("Migration versions must be unique and ordered")
    return migrations


def _begin_locked_transaction(connection, dialect):
    """Acquire a dialect lock before any migration-history read."""
    if dialect == "sqlite":
        # Set the wait timeout directly on the DBAPI connection so SQLAlchemy
        # does not begin a deferred transaction before BEGIN IMMEDIATE.
        connection.connection.driver_connection.execute("PRAGMA busy_timeout=15000")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        return connection.get_transaction()

    if dialect == "postgresql":
        transaction = connection.begin()
        connection.exec_driver_sql("SET LOCAL lock_timeout = '30s'")
        connection.exec_driver_sql(
            "SELECT pg_advisory_xact_lock(%s)", (PG_ADVISORY_LOCK_KEY,)
        )
        return transaction

    raise RuntimeError(f"Unsupported migration dialect: {dialect}")


def _history_exists(connection):
    return inspect(connection).has_table("schema_migrations")


def _read_history(connection):
    if not _history_exists(connection):
        return {}
    rows = connection.execute(select(schema_migrations)).mappings().all()
    return {row["version"]: dict(row) for row in rows}


def _validate_history(history, migrations):
    known = {migration.version: migration for migration in migrations}
    unexpected = sorted(set(history) - set(known))
    if unexpected:
        raise RuntimeError(f"Unexpected migration version(s): {', '.join(unexpected)}")
    applied_positions = [
        index for index, migration in enumerate(migrations) if migration.version in history
    ]
    if applied_positions and applied_positions != list(range(max(applied_positions) + 1)):
        raise RuntimeError("Migration history contains a gap before a later version")
    for version, row in history.items():
        migration = known[version]
        if row["name"] != migration.name:
            raise RuntimeError(f"Migration name mismatch for version {version}")
        if row["checksum"] != migration.checksum:
            raise RuntimeError(f"Migration checksum mismatch for version {version}")


def _ddl_applies(constraint, dialect_name):
    rule = getattr(constraint, "_ddl_if", None)
    if rule is None or rule.dialect is None:
        return True
    dialects = rule.dialect if isinstance(rule.dialect, (tuple, list, set)) else (rule.dialect,)
    return dialect_name in dialects


def _validate_table_contract(connection, table):
    inspector = inspect(connection)
    table_name = table.name
    actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
    missing = sorted(set(table.columns.keys()) - actual_columns)
    if missing:
        raise RuntimeError(f"Schema drift in {table_name}: missing columns: {', '.join(missing)}")

    actual_indexes = {
        (index.get("name"), tuple(index.get("column_names") or ()))
        for index in inspector.get_indexes(table_name)
    }
    for index in table.indexes:
        expected = (index.name, tuple(column.name for column in index.columns))
        if expected not in actual_indexes:
            raise RuntimeError(f"Schema drift in {table_name}: missing index {index.name}")

    actual_checks = {
        constraint.get("name")
        for constraint in inspector.get_check_constraints(table_name)
        if constraint.get("name")
    }
    expected_checks = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name
        and _ddl_applies(constraint, connection.dialect.name)
    }
    missing_checks = sorted(expected_checks - actual_checks)
    if missing_checks:
        raise RuntimeError(f"Schema drift in {table_name}: missing constraints: {', '.join(missing_checks)}")

    actual_fks = {
        (tuple(fk.get("constrained_columns") or ()), fk.get("referred_table"),
         tuple(fk.get("referred_columns") or ()), (fk.get("options") or {}).get("ondelete"))
        for fk in inspector.get_foreign_keys(table_name)
    }
    for fk in table.foreign_key_constraints:
        elements = list(fk.elements)
        expected = (
            tuple(element.parent.name for element in elements),
            elements[0].column.table.name,
            tuple(element.column.name for element in elements),
            fk.ondelete,
        )
        if expected not in actual_fks:
            raise RuntimeError(f"Schema drift in {table_name}: missing foreign key on {', '.join(expected[0])}")

    actual_uniques = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(table_name)
    }
    expected_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    missing_uniques = sorted(expected_uniques - actual_uniques)
    if missing_uniques:
        columns = ", ".join("(" + ", ".join(cols) + ")" for cols in missing_uniques)
        raise RuntimeError(f"Schema drift in {table_name}: missing unique constraints: {columns}")


def _validate_schema_state(connection, history, migrations):
    inspected_tables = set(inspect(connection).get_table_names())
    expected_by_version = {migration.version: migration.expected_tables for migration in migrations}
    known_tables = {table.name for tables in expected_by_version.values() for table in tables}
    present_subscription_tables = known_tables.intersection(inspected_tables)
    if not history and present_subscription_tables:
        raise RuntimeError("Subscription tables exist without a matching migration history record")
    if not history:
        return

    applied = [migration for migration in migrations if migration.version in history]
    latest = applied[-1]
    latest_contract_tables = {table.name for table in latest.expected_tables}
    premature_tables = sorted(present_subscription_tables - latest_contract_tables)
    if premature_tables:
        raise RuntimeError(
            "Subscription tables exist before their migration version is recorded: "
            + ", ".join(premature_tables)
        )
    for table in latest.expected_tables:
        if table.name not in inspected_tables:
            raise RuntimeError(f"Migration {latest.version} is recorded but table {table.name} is missing")
        _validate_table_contract(connection, table)

    if "schema_migrations" not in inspected_tables:
        raise RuntimeError("Migration history is recorded but schema_migrations is missing")
    history_columns = {column["name"] for column in inspect(connection).get_columns("schema_migrations")}
    required_history_columns = {"version", "name", "checksum", "applied_at"}
    if not required_history_columns.issubset(history_columns):
        missing = sorted(required_history_columns - history_columns)
        raise RuntimeError(f"Schema drift in schema_migrations: missing columns: {', '.join(missing)}")


def _upgrade_locked(connection, migrations):
    history_exists = _history_exists(connection)
    history = _read_history(connection) if history_exists else {}
    _validate_history(history, migrations)
    _validate_schema_state(connection, history, migrations)
    if not history_exists:
        schema_migrations.create(connection)

    applied = []
    for index, migration in enumerate(migrations):
        if migration.version in history:
            continue
        if any(later.version in history for later in migrations[index + 1 :]):
            raise RuntimeError("Migration history contains a gap before a later version")
        migration.module.upgrade(connection)
        connection.execute(
            schema_migrations.insert().values(
                version=migration.version,
                name=migration.name,
                checksum=migration.checksum,
                applied_at=datetime.now(timezone.utc),
            )
        )
        applied.append(migration.version)
    return applied


def _status_locked(connection, migrations):
    history = _read_history(connection)
    _validate_history(history, migrations)
    _validate_schema_state(connection, history, migrations)
    return [
        {
            "version": migration.version,
            "name": migration.name,
            "applied": migration.version in history,
            "checksum": migration.checksum,
        }
        for migration in migrations
    ]


def _downgrade_locked(connection, migrations, version, confirm_empty):
    if not confirm_empty:
        raise RuntimeError("Downgrade requires explicit --confirm-empty confirmation")
    history = _read_history(connection)
    _validate_history(history, migrations)
    _validate_schema_state(connection, history, migrations)
    if version not in history:
        return False
    applied_versions = [migration.version for migration in migrations if migration.version in history]
    if not applied_versions or applied_versions[-1] != version:
        raise RuntimeError("Only the latest applied migration can be downgraded")

    migration = next(item for item in migrations if item.version == version)
    migration.module.downgrade(connection)
    connection.execute(schema_migrations.delete().where(schema_migrations.c.version == version))
    return True


def run_migration_command(engine, command, version=None, confirm_empty=False):
    """Run upgrade/status/downgrade under a lock acquired before history reads."""
    migrations = _migration_registry()
    with engine.connect() as connection:
        transaction = _begin_locked_transaction(connection, engine.dialect.name)
        try:
            if command == "upgrade":
                result = _upgrade_locked(connection, migrations)
            elif command == "status":
                result = _status_locked(connection, migrations)
            elif command == "downgrade":
                if not version:
                    raise RuntimeError("Downgrade requires a migration version")
                result = _downgrade_locked(connection, migrations, version, confirm_empty)
            else:
                raise RuntimeError(f"Unknown migration command: {command}")
            transaction.commit()
            return result
        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit AI Interview Studio schema migrations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("upgrade", help="Apply pending migrations")
    subparsers.add_parser("status", help="Show applied migration versions")
    downgrade_parser = subparsers.add_parser("downgrade", help="Remove an empty migration schema")
    downgrade_parser.add_argument("--version", required=True)
    downgrade_parser.add_argument("--confirm-empty", action="store_true")
    args = parser.parse_args(argv)

    # Refuse the app's implicit local interview.db fallback. The operator must
    # explicitly provide the target URL in the process environment.
    if not os.environ.get("DATABASE_URL", "").strip():
        parser.error("Set DATABASE_URL explicitly for the intended migration target")
    from app.database import engine

    try:
        result = run_migration_command(
            engine,
            args.command,
            version=getattr(args, "version", None),
            confirm_empty=getattr(args, "confirm_empty", False),
        )
    except Exception as exc:
        # Do not print database URLs or driver details that may include credentials.
        parser.exit(1, f"Migration failed ({type(exc).__name__}); inspect safe server logs.\n")

    if args.command == "status":
        for row in result:
            print(f"{row['version']} {row['name']}: {'applied' if row['applied'] else 'pending'}")
    elif args.command == "upgrade":
        print("Already up to date." if not result else f"Applied migration(s): {', '.join(result)}")
    else:
        print("Downgrade completed." if result else "Migration was not applied; no changes made.")


if __name__ == "__main__":
    main()
