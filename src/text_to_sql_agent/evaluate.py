"""Eval harness: execution-accuracy scoring over the bundled questions.

For each natural-language question, the agent's answer is compared against
a hand-written reference query by *executing both* on the same database
and comparing the resulting row sets (order-insensitive). This is the
standard execution-accuracy metric for text-to-SQL.

Runs fully offline with the default deterministic generator:

    python -m text_to_sql_agent.evaluate
    python scripts/run_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .agent import run_agent
from .schema import execute_readonly
from .seed import default_db_path, ensure_database
from .validator import validate_sql

QUESTIONS_PATH = Path(__file__).resolve().parents[2] / "eval" / "questions.json"


def load_questions(path: str | Path | None = None) -> list[dict]:
    with open(path or QUESTIONS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _normalise_rows(rows: list[tuple]) -> list[str]:
    return sorted(repr(tuple(row)) for row in rows)


def results_match(agent_rows: list[tuple], reference_rows: list[tuple]) -> bool:
    return _normalise_rows(agent_rows) == _normalise_rows(reference_rows)


def run_eval(db_path: str | Path | None = None, verbose: bool = True) -> dict:
    path = ensure_database(db_path or default_db_path())
    questions = load_questions()
    passed = 0
    outcomes = []
    for item in questions:
        result = run_agent(item["question"], db_path=path)
        _cols, reference_rows = execute_readonly(
            path, validate_sql(item["reference_sql"]))
        ok = bool(result.success) and results_match(result.rows, reference_rows)
        passed += int(ok)
        outcomes.append({"id": item["id"], "question": item["question"],
                         "passed": ok, "sql": result.sql,
                         "attempts": result.attempts})
        if verbose:
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] Q{item['id']:>2} ({result.attempts} attempt(s)) "
                  f"{item['question']}")
            print(f"       SQL: {result.sql}")
            if not ok:
                print(f"       agent rows: {result.rows}")
                print(f"       reference rows: {reference_rows}")
    total = len(questions)
    score = (passed / total * 100) if total else 0.0
    if verbose:
        print()
        print(f"Execution accuracy: {passed}/{total} = {score:.1f}%")
    return {"passed": passed, "total": total, "score_pct": score,
            "outcomes": outcomes}


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    db = args[0] if args else None
    report = run_eval(db)
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
