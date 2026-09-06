#!/usr/bin/env python3
"""
SQLite to PostgreSQL migration script for InterviewIQ.

This script:
1. Reads all tables from a SQLite database (data/app.db)
2. Creates matching tables in PostgreSQL (using DATABASE_URL)
3. Copies all data preserving IDs, timestamps, FKs, and JSON payloads
4. Verifies row counts match between source and destination

Usage:
    DATABASE_URL=postgresql://user:pass@host/db python scripts/migrate_sqlite_to_pg.py

Environment variables:
    DATABASE_URL - PostgreSQL connection string (required)
    SQLITE_PATH - Path to SQLite database (default: data/app.db)
"""
import os
import sys
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row


def get_sqlite_path() -> Path:
    """Get SQLite database path from environment or default."""
    sqlite_path = os.environ.get("SQLITE_PATH", "").strip()
    if sqlite_path:
        return Path(sqlite_path)
    return Path(__file__).resolve().parent.parent / "data" / "app.db"


def get_pg_connection():
    """Create PostgreSQL connection from DATABASE_URL."""
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")
    if not (database_url.startswith("postgresql://") or database_url.startswith("postgres://")):
        raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
    return psycopg.connect(database_url, row_factory=dict_row, autocommit=False)


def get_sqlite_connection(sqlite_path: Path):
    """Create SQLite connection."""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_sqlite_tables(sqlite_conn) -> list[str]:
    """Get list of user tables from SQLite."""
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row["name"] for row in cursor.fetchall()]


def get_table_schema(sqlite_conn, table: str) -> list[dict]:
    """Get column info for a SQLite table."""
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table})")
    return [dict(row) for row in cursor.fetchall()]


def get_sqlite_data(sqlite_conn, table: str) -> list[dict]:
    """Get all data from a SQLite table."""
    cursor = sqlite_conn.execute(f"SELECT * FROM {table}")
    return [dict(row) for row in cursor.fetchall()]


def sqlite_type_to_pg(sqlite_type: str) -> str:
    """Map SQLite type to PostgreSQL type."""
    sqlite_type = sqlite_type.upper()
    if sqlite_type in ("INTEGER", "INT"):
        return "INTEGER"
    if sqlite_type in ("REAL", "FLOAT", "DOUBLE"):
        return "REAL"
    if sqlite_type in ("TEXT", "VARCHAR", "CHAR", "CLOB"):
        return "TEXT"
    if sqlite_type in ("BLOB",):
        return "BYTEA"
    if sqlite_type in ("NUMERIC", "DECIMAL"):
        return "NUMERIC"
    if sqlite_type in ("BOOLEAN", "BOOL"):
        return "BOOLEAN"
    return "TEXT"


def create_pg_table(pg_conn, table: str, columns: list[dict], is_sqlite: bool = True):
    """Create a table in PostgreSQL matching the SQLite schema."""
    col_defs = []
    pk_cols = []
    
    for col in columns:
        col_name = col["name"]
        col_type = sqlite_type_to_pg(col["type"])
        not_null = "NOT NULL" if col["notnull"] else ""
        default = f"DEFAULT {col['dflt_value']}" if col["dflt_value"] is not None else ""
        pk = col["pk"]
        
        if pk:
            pk_cols.append(col_name)
            # For SQLite INTEGER PRIMARY KEY, use SERIAL in PostgreSQL
            if col_type == "INTEGER" and pk == 1:
                col_type = "SERIAL"
                not_null = "NOT NULL"
        
        col_defs.append(f'"{col_name}" {col_type} {not_null} {default}'.strip())
    
    # Add primary key constraint if not already inline
    if pk_cols and not any(col["type"].upper() == "INTEGER" and col["pk"] == 1 for col in columns):
        col_defs.append(f'PRIMARY KEY ({", ".join(f\'"{c}"\' for c in pk_cols)})')
    
    sql = f'CREATE TABLE IF NOT EXISTS "{table}" (\n    ' + ",\n    ".join(col_defs) + "\n)"
    
    with pg_conn.cursor() as cur:
        cur.execute(sql)
    pg_conn.commit()
    print(f"  Created table: {table}")


def copy_table_data(pg_conn, sqlite_conn, table: str, batch_size: int = 1000):
    """Copy all data from SQLite table to PostgreSQL."""
    # Get column names
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table})")
    columns = [row["name"] for row in cursor.fetchall()]
    
    if not columns:
        print(f"  Table {table}: no columns, skipping")
        return 0
    
    # Get all data
    data = get_sqlite_data(sqlite_conn, table)
    if not data:
        print(f"  Table {table}: 0 rows")
        return 0
    
    # Prepare insert statement
    placeholders = ", ".join(["%s"] * len(columns))
    cols_quoted = ", ".join(f'"{c}"' for c in columns)
    insert_sql = f'INSERT INTO "{table}" ({cols_quoted}) VALUES ({placeholders})'
    
    # Insert in batches
    total = 0
    with pg_conn.cursor() as cur:
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            values = [tuple(row[c] for c in columns) for row in batch]
            cur.executemany(insert_sql, values)
            total += len(batch)
        pg_conn.commit()
    
    print(f"  Table {table}: {total} rows copied")
    return total


def verify_counts(pg_conn, sqlite_conn, tables: list[str]) -> bool:
    """Verify row counts match between SQLite and PostgreSQL."""
    all_match = True
    print("\nVerifying row counts...")
    
    for table in tables:
        sqlite_count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        pg_count = 0
        with pg_conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            pg_count = cur.fetchone()[0]
        
        match = sqlite_count == pg_count
        status = "✓" if match else "✗"
        print(f"  {status} {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
        if not match:
            all_match = False
    
    return all_match


def main():
    print("InterviewIQ SQLite to PostgreSQL Migration")
    print("=" * 50)
    
    # Get paths
    sqlite_path = get_sqlite_path()
    print(f"SQLite source: {sqlite_path}")
    
    if not sqlite_path.exists():
        print(f"ERROR: SQLite database not found at {sqlite_path}")
        sys.exit(1)
    
    # Connect to databases
    print("Connecting to databases...")
    sqlite_conn = get_sqlite_connection(sqlite_path)
    pg_conn = get_pg_connection()
    
    try:
        # Get tables
        tables = get_sqlite_tables(sqlite_conn)
        print(f"\nFound {len(tables)} tables: {', '.join(tables)}")
        
        # Create tables and copy data
        print("\nCreating tables and copying data...")
        for table in tables:
            print(f"\nProcessing {table}...")
            columns = get_table_schema(sqlite_conn, table)
            create_pg_table(pg_conn, table, columns)
            copy_table_data(pg_conn, sqlite_conn, table)
        
        # Verify counts
        success = verify_counts(pg_conn, sqlite_conn, tables)
        
        if success:
            print("\n✓ Migration completed successfully! All row counts match.")
            sys.exit(0)
        else:
            print("\n✗ Migration completed with mismatches. Please review.")
            sys.exit(1)
            
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()