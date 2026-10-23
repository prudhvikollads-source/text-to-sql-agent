"""Command-line interface.

    python -m text_to_sql_agent "how many active subscribers per plan?"
    python -m text_to_sql_agent --db data/sample.db "total revenue from paid invoices?"
"""

from __future__ import annotations

import argparse
import json
import sys

from .agent import run_agent
from .seed import build_database, default_db_path


def format_table(columns: list[str], rows: list[tuple]) -> str:
    if not columns:
        return "(no result columns)"
    text_rows = [[("" if v is None else str(v)) for v in row] for row in rows]
    widths = [len(c) for c in columns]
    for row in text_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    header = " | ".join(c.ljust(widths[i]) for i, c in enumerate(columns))
    divider = "-+-".join("-" * w for w in widths)
    body = [" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
            for row in text_rows]
    return "\n".join([header, divider, *body])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="text-to-sql",
        description="Ask natural-language questions over the sample database.")
    parser.add_argument("question", nargs="*", help="the question to ask")
    parser.add_argument("--db", default=None,
                        help="path to the SQLite database (default: data/sample.db)")
    parser.add_argument("--max-attempts", type=int, default=3,
                        help="maximum SQL generation attempts (default: 3)")
    parser.add_argument("--seed", action="store_true",
                        help="rebuild the sample database and exit")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    args = parser.parse_args(argv)

    db_path = args.db or str(default_db_path())
    if args.seed:
        build_database(db_path)
        print(f"Seeded sample database at {db_path}")
        return 0

    question = " ".join(args.question).strip()
    if not question:
        parser.print_usage(sys.stderr)
        print("error: provide a question, e.g. "
              'python -m text_to_sql_agent "how many customers are there?"',
              file=sys.stderr)
        return 2

    result = run_agent(question, db_path=db_path, max_attempts=args.max_attempts)

    if args.json:
        print(json.dumps({
            "question": result.question,
            "sql": result.sql,
            "columns": result.columns,
            "rows": [list(r) for r in result.rows],
            "attempts": result.attempts,
            "success": result.success,
            "errors": result.errors,
            "backend": result.backend,
        }, indent=2))
        return 0 if result.success else 1

    print(f"Question: {result.question}")
    print(f"SQL: {result.sql}")
    print(f"Attempts: {result.attempts}  Backend: {result.backend}")
    if not result.success:
        print(f"Failed: {'; '.join(result.errors)}")
        return 1
    print(format_table(result.columns, result.rows))
    print(f"({len(result.rows)} row(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
