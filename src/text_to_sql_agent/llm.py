"""LLM access behind a small interface.

Two implementations:

* ``MockLLM`` (default) — a deterministic, offline SQL generator. It maps
  natural-language question patterns to SQL using the introspected schema.
  No API key, no network: the whole project, including the eval harness,
  runs offline with it.
* ``EnvLLM`` — an optional provider client configured purely through
  environment variables (``TEXT_TO_SQL_API_URL``, ``TEXT_TO_SQL_API_KEY``,
  ``TEXT_TO_SQL_MODEL``) that talks to a generic chat-completions style
  HTTP endpoint. Only used when those variables are set.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class LLM(Protocol):
    def generate(self, question: str, schema_text: str,
                 error: str | None = None,
                 previous_sql: str | None = None) -> str:
        """Return one SQL statement for ``question``.

        On a retry, ``error`` carries the failure of ``previous_sql`` so the
        generator can correct itself.
        """
        ...


# ---------------------------------------------------------------------------
# Deterministic offline generator
# ---------------------------------------------------------------------------

# (needles that must all appear in the normalised question, SQL)
# Order matters: more specific patterns are checked first.
_RULES: list[tuple[tuple[str, ...], str]] = [
    (("revenue", "per plan"),
     "SELECT p.plan_name, ROUND(SUM(i.amount), 2) AS revenue "
     "FROM invoices i "
     "JOIN subscriptions s ON s.subscription_id = i.subscription_id "
     "JOIN plans p ON p.plan_id = s.plan_id "
     "WHERE i.status = 'paid' GROUP BY p.plan_name ORDER BY p.plan_name"),
    (("revenue", "by plan"),
     "SELECT p.plan_name, ROUND(SUM(i.amount), 2) AS revenue "
     "FROM invoices i "
     "JOIN subscriptions s ON s.subscription_id = i.subscription_id "
     "JOIN plans p ON p.plan_id = s.plan_id "
     "WHERE i.status = 'paid' GROUP BY p.plan_name ORDER BY p.plan_name"),
    (("most active subscribers",),
     "SELECT p.plan_name, COUNT(*) AS active_subscribers "
     "FROM subscriptions s JOIN plans p ON p.plan_id = s.plan_id "
     "WHERE s.status = 'active' GROUP BY p.plan_name "
     "ORDER BY active_subscribers DESC, p.plan_name ASC LIMIT 1"),
    (("active subscribers", "per plan"),
     "SELECT p.plan_name, COUNT(*) AS active_subscribers "
     "FROM subscriptions s JOIN plans p ON p.plan_id = s.plan_id "
     "WHERE s.status = 'active' GROUP BY p.plan_name ORDER BY p.plan_name"),
    (("active subscribers", "by plan"),
     "SELECT p.plan_name, COUNT(*) AS active_subscribers "
     "FROM subscriptions s JOIN plans p ON p.plan_id = s.plan_id "
     "WHERE s.status = 'active' GROUP BY p.plan_name ORDER BY p.plan_name"),
    (("top 5 customers",),
     "SELECT c.full_name, ROUND(SUM(i.amount), 2) AS total_paid "
     "FROM invoices i JOIN customers c ON c.customer_id = i.customer_id "
     "WHERE i.status = 'paid' GROUP BY c.customer_id, c.full_name "
     "ORDER BY total_paid DESC, c.full_name ASC LIMIT 5"),
    (("top customers", "paid"),
     "SELECT c.full_name, ROUND(SUM(i.amount), 2) AS total_paid "
     "FROM invoices i JOIN customers c ON c.customer_id = i.customer_id "
     "WHERE i.status = 'paid' GROUP BY c.customer_id, c.full_name "
     "ORDER BY total_paid DESC, c.full_name ASC LIMIT 5"),
    (("average data usage", "per plan"),
     "SELECT p.plan_name, ROUND(AVG(u.data_used_gb), 2) AS avg_data_used_gb "
     "FROM usage_records u "
     "JOIN subscriptions s ON s.subscription_id = u.subscription_id "
     "JOIN plans p ON p.plan_id = s.plan_id "
     "GROUP BY p.plan_name ORDER BY p.plan_name"),
    (("total revenue",),
     "SELECT ROUND(SUM(amount), 2) AS total_revenue "
     "FROM invoices WHERE status = 'paid'"),
    (("revenue from paid",),
     "SELECT ROUND(SUM(amount), 2) AS total_revenue "
     "FROM invoices WHERE status = 'paid'"),
    (("which country", "most customers"),
     "SELECT country, COUNT(*) AS customer_count FROM customers "
     "GROUP BY country ORDER BY customer_count DESC, country ASC LIMIT 1"),
    (("customers", "each country"),
     "SELECT country, COUNT(*) AS customer_count FROM customers "
     "GROUP BY country ORDER BY country"),
    (("customers", "per country"),
     "SELECT country, COUNT(*) AS customer_count FROM customers "
     "GROUP BY country ORDER BY country"),
    (("customers", "by country"),
     "SELECT country, COUNT(*) AS customer_count FROM customers "
     "GROUP BY country ORDER BY country"),
    (("how many customers",),
     "SELECT COUNT(*) AS customer_count FROM customers"),
    (("total number of customers",),
     "SELECT COUNT(*) AS customer_count FROM customers"),
    (("number of customers",),
     "SELECT COUNT(*) AS customer_count FROM customers"),
    (("average monthly price",),
     "SELECT ROUND(AVG(monthly_price), 2) AS avg_monthly_price FROM plans"),
    (("average price", "plan"),
     "SELECT ROUND(AVG(monthly_price), 2) AS avg_monthly_price FROM plans"),
    (("tickets", "open"),
     "SELECT COUNT(*) AS open_tickets FROM support_tickets "
     "WHERE status = 'open'"),
    (("tickets", "category"),
     "SELECT category, COUNT(*) AS ticket_count FROM support_tickets "
     "GROUP BY category ORDER BY category"),
    (("tickets", "priority"),
     "SELECT priority, COUNT(*) AS ticket_count FROM support_tickets "
     "GROUP BY priority ORDER BY priority"),
    (("invoices", "overdue"),
     "SELECT COUNT(*) AS overdue_invoices FROM invoices "
     "WHERE status = 'overdue'"),
    (("how many invoices",),
     "SELECT COUNT(*) AS invoice_count FROM invoices"),
    (("unpaid", "total"),
     "SELECT ROUND(SUM(amount), 2) AS total_unpaid "
     "FROM invoices WHERE status = 'unpaid'"),
    (("unpaid", "amount"),
     "SELECT ROUND(SUM(amount), 2) AS total_unpaid "
     "FROM invoices WHERE status = 'unpaid'"),
    (("subscriptions", "cancelled"),
     "SELECT COUNT(*) AS cancelled_subscriptions FROM subscriptions "
     "WHERE status = 'cancelled'"),
    (("subscriptions", "by status"),
     "SELECT status, COUNT(*) AS subscription_count FROM subscriptions "
     "GROUP BY status ORDER BY status"),
    (("subscriptions", "per status"),
     "SELECT status, COUNT(*) AS subscription_count FROM subscriptions "
     "GROUP BY status ORDER BY status"),
    (("average invoice amount",),
     "SELECT ROUND(AVG(amount), 2) AS avg_invoice_amount FROM invoices"),
    (("most expensive plan",),
     "SELECT plan_name, monthly_price FROM plans "
     "ORDER BY monthly_price DESC LIMIT 1"),
    (("highest priced plan",),
     "SELECT plan_name, monthly_price FROM plans "
     "ORDER BY monthly_price DESC LIMIT 1"),
    (("total data usage",),
     "SELECT ROUND(SUM(data_used_gb), 2) AS total_data_used_gb "
     "FROM usage_records"),
    (("how many subscriptions",),
     "SELECT COUNT(*) AS subscription_count FROM subscriptions"),
    (("how many tickets",),
     "SELECT COUNT(*) AS ticket_count FROM support_tickets"),
    (("list all plans",),
     "SELECT plan_name, monthly_price, data_allowance_gb, voice_minutes "
     "FROM plans ORDER BY monthly_price"),
    (("list plans",),
     "SELECT plan_name, monthly_price, data_allowance_gb, voice_minutes "
     "FROM plans ORDER BY monthly_price"),
]

# Known wrong identifiers -> correct ones, used on the self-correction path.
_TYPO_FIXES = {
    "customer_name": "full_name",
    "cust_name": "full_name",
    "plan_price": "monthly_price",
    "subscription_status": "status",
    "ticket_status": "status",
    "invoice_status": "status",
    "amount_paid": "amount",
    "data_usage_gb": "data_used_gb",
}


def _normalise(question: str) -> str:
    return re.sub(r"\s+", " ", question.lower().strip().rstrip("?"))


def rule_based_sql(question: str) -> str | None:
    q = _normalise(question)
    for needles, sql in _RULES:
        if all(n in q for n in needles):
            return sql
    return None


class MockLLM:
    """Deterministic offline generator (the default)."""

    name = "mock"

    def generate(self, question: str, schema_text: str,
                 error: str | None = None,
                 previous_sql: str | None = None) -> str:
        if error and previous_sql:
            fixed = previous_sql
            for wrong, right in _TYPO_FIXES.items():
                fixed = re.sub(rf"\b{wrong}\b", right, fixed)
            if fixed != previous_sql:
                return fixed
            sql = rule_based_sql(question)
            if sql and sql != previous_sql:
                return sql
            return previous_sql
        sql = rule_based_sql(question)
        if sql:
            return sql
        # Generic fallback: a safe sample of the first table in the schema.
        m = re.search(r"Table (\w+)", schema_text)
        table = m.group(1) if m else "customers"
        return f"SELECT * FROM {table}"


# ---------------------------------------------------------------------------
# Optional provider client (environment-configured only)
# ---------------------------------------------------------------------------

class EnvLLM:
    name = "env"

    def __init__(self) -> None:
        self.url = os.environ["TEXT_TO_SQL_API_URL"]
        self.key = os.environ["TEXT_TO_SQL_API_KEY"]
        self.model = os.environ.get("TEXT_TO_SQL_MODEL", "default")

    def generate(self, question: str, schema_text: str,
                 error: str | None = None,
                 previous_sql: str | None = None) -> str:
        prompt = (
            "Write a single read-only SQLite SELECT query for the question.\n"
            f"Schema:\n{schema_text}\nQuestion: {question}\n"
        )
        if error and previous_sql:
            prompt += (f"Previous query:\n{previous_sql}\n"
                       f"It failed with: {error}\nReturn a corrected query.\n")
        prompt += "Return only the SQL, no explanation."
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            self.url, data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read())
        text = payload["choices"][0]["message"]["content"]
        text = re.sub(r"```(sql)?", "", text).strip()
        return text.splitlines()[0] if text else ""


def get_llm() -> LLM:
    """Env-configured provider when available, otherwise the offline mock."""
    if os.environ.get("TEXT_TO_SQL_API_URL") and os.environ.get("TEXT_TO_SQL_API_KEY"):
        return EnvLLM()
    return MockLLM()
