"""Schema introspection over a read-only SQLite connection."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    """Open the database strictly read-only (SQLite URI mode=ro)."""
    path = Path(db_path)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def introspect_schema(db_path: str | Path) -> dict:
    """Return {table: {"columns": [(name, type), ...], "row_count": int}}."""
    conn = connect_readonly(db_path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        schema: dict = {}
        for table in tables:
            columns = [(r[1], r[2]) for r in conn.execute(f"PRAGMA table_info({table})")]
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            schema[table] = {"columns": columns, "row_count": count}
        return schema
    finally:
        conn.close()


def schema_to_text(schema: dict) -> str:
    """Render the schema compactly, the way it is handed to the SQL generator."""
    lines = []
    for table, info in schema.items():
        cols = ", ".join(f"{name} {ctype}" for name, ctype in info["columns"])
        lines.append(f"Table {table} ({info['row_count']} rows): {cols}")
    return "\n".join(lines)


def execute_readonly(db_path: str | Path, sql: str) -> tuple[list[str], list[tuple]]:
    """Execute an already-validated query read-only; return (columns, rows)."""
    conn = connect_readonly(db_path)
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return columns, rows
    finally:
        conn.close()
