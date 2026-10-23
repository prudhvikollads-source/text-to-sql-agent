"""Read-only SQL validation.

Every generated statement passes through here before execution. The rules:

* a single statement only (no ``;``-separated batches),
* it must be a ``SELECT`` (or a ``WITH ... SELECT``),
* no write / DDL / administrative keywords anywhere in the statement,
* a ``LIMIT`` is always enforced: one is appended when missing, and an
  existing limit above ``MAX_LIMIT`` is clamped down.
"""

from __future__ import annotations

import re

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE",
    "TRUNCATE", "VACUUM", "ATTACH", "DETACH", "PRAGMA", "GRANT", "REVOKE",
    "REINDEX", "ANALYZE", "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT",
}

_WORD_RE = re.compile(r"[A-Za-z_]+")
_LIMIT_RE = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)


class ValidationError(ValueError):
    """Raised when a statement is not a safe read-only query."""


def _strip_string_literals(sql: str) -> str:
    """Remove single-quoted literals so keywords inside strings don't trip checks."""
    return re.sub(r"'([^']|'')*'", "''", sql)


def validate_sql(sql: str, default_limit: int = DEFAULT_LIMIT,
                 max_limit: int = MAX_LIMIT) -> str:
    """Return a safe, limit-enforced version of ``sql`` or raise ValidationError."""
    if not sql or not sql.strip():
        raise ValidationError("empty SQL statement")

    cleaned = sql.strip()
    # A single trailing semicolon is fine; any other semicolon means a batch.
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()
    if ";" in cleaned:
        raise ValidationError("multiple statements are not allowed")

    body = _strip_string_literals(cleaned)
    words = [w.upper() for w in _WORD_RE.findall(body)]
    if not words:
        raise ValidationError("no SQL statement found")

    first = words[0]
    if first not in ("SELECT", "WITH"):
        raise ValidationError(f"only SELECT queries are allowed, got {first!r}")
    if first == "WITH" and "SELECT" not in words:
        raise ValidationError("WITH clauses must wrap a SELECT")

    bad = FORBIDDEN_KEYWORDS.intersection(words)
    if bad:
        raise ValidationError(
            f"forbidden keyword(s) in read-only query: {', '.join(sorted(bad))}"
        )

    match = _LIMIT_RE.search(cleaned)
    if match:
        limit = int(match.group(1))
        if limit > max_limit:
            cleaned = cleaned[: match.start(1)] + str(max_limit) + cleaned[match.end(1):]
    else:
        cleaned = f"{cleaned} LIMIT {default_limit}"
    return cleaned
