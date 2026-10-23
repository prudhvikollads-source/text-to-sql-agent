"""Seed script: generates the bundled synthetic sample database.

The database models a neutral commercial telecom / e-commerce business:
customers buy subscription plans, get invoiced monthly, consume data, and
raise support tickets. All data is synthetic, generated with a fixed random
seed so every run produces exactly the same database.

Usage:
    python -m text_to_sql_agent.seed [path-to-db]
    python scripts/seed_db.py [path-to-db]
"""

from __future__ import annotations

import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

SEED = 42

FIRST_NAMES = [
    "Amelia", "Noah", "Priya", "Liam", "Sofia", "Ethan", "Maya", "Lucas",
    "Aisha", "Oliver", "Chen", "Fatima", "Diego", "Ingrid", "Marcus",
    "Lena", "Omar", "Grace", "Tomas", "Nadia", "Ravi", "Elena", "Jonas",
    "Mei", "Carlos", "Anita", "Felix", "Zara", "Hugo", "Tara",
]
LAST_NAMES = [
    "Sharma", "Johnson", "Garcia", "Kim", "Novak", "Haddad", "Muller",
    "Rossi", "Tanaka", "Novikova", "Brown", "Ali", "Fischer", "Dubois",
    "Silva", "Berg", "Nair", "Costa", "Weber", "Osei", "Larsen", "Meier",
    "Khan", "Petrov", "Singh", "Moreau", "Lindqvist", "Adeyemi", "Varga",
    "Cohen",
]

COUNTRIES_CITIES = {
    "United States": ["New York", "Austin", "Denver", "Seattle", "Chicago"],
    "Canada": ["Toronto", "Vancouver", "Montreal"],
    "United Kingdom": ["London", "Manchester", "Edinburgh"],
    "Germany": ["Berlin", "Munich", "Hamburg"],
    "France": ["Paris", "Lyon", "Nantes"],
    "Australia": ["Sydney", "Melbourne", "Perth"],
    "India": ["Bengaluru", "Hyderabad", "Pune"],
    "Brazil": ["Sao Paulo", "Recife", "Curitiba"],
    "Spain": ["Madrid", "Valencia", "Bilbao"],
    "Netherlands": ["Amsterdam", "Utrecht", "Eindhoven"],
}

PLANS = [
    # plan_id, plan_name, monthly_price, data_allowance_gb, voice_minutes
    (1, "Basic", 15.0, 5, 100),
    (2, "Standard", 29.0, 25, 500),
    (3, "Premium", 49.0, 100, 2000),
    (4, "Unlimited", 79.0, 1000, 10000),
    (5, "Family", 99.0, 300, 5000),
]

SUBSCRIPTION_STATUSES = ["active", "active", "active", "active", "cancelled", "paused"]
INVOICE_STATUSES = ["paid", "paid", "paid", "paid", "unpaid", "overdue"]
TICKET_CATEGORIES = ["billing", "connectivity", "account", "device", "plan_change", "other"]
TICKET_PRIORITIES = ["low", "medium", "medium", "high", "urgent"]
TICKET_STATUSES = ["open", "open", "in_progress", "resolved", "resolved", "closed"]

SCHEMA_DDL = """
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    full_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    country     TEXT NOT NULL,
    city        TEXT NOT NULL,
    signup_date TEXT NOT NULL
);
CREATE TABLE plans (
    plan_id           INTEGER PRIMARY KEY,
    plan_name         TEXT NOT NULL UNIQUE,
    monthly_price     REAL NOT NULL,
    data_allowance_gb INTEGER NOT NULL,
    voice_minutes     INTEGER NOT NULL
);
CREATE TABLE subscriptions (
    subscription_id INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    plan_id         INTEGER NOT NULL REFERENCES plans(plan_id),
    start_date      TEXT NOT NULL,
    end_date        TEXT,
    status          TEXT NOT NULL
);
CREATE TABLE invoices (
    invoice_id      INTEGER PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    invoice_date    TEXT NOT NULL,
    amount          REAL NOT NULL,
    status          TEXT NOT NULL
);
CREATE TABLE usage_records (
    usage_id       INTEGER PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
    usage_month    TEXT NOT NULL,
    data_used_gb   REAL NOT NULL,
    minutes_used   INTEGER NOT NULL,
    sms_used       INTEGER NOT NULL
);
CREATE TABLE support_tickets (
    ticket_id     INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    created_date  TEXT NOT NULL,
    category      TEXT NOT NULL,
    priority      TEXT NOT NULL,
    status        TEXT NOT NULL,
    resolution_days REAL
);
"""


def build_database(db_path: str | Path, n_customers: int = 500, n_tickets: int = 450) -> Path:
    """Create (or recreate) the sample database at ``db_path`` deterministically."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    rng = random.Random(SEED)
    base = date(2023, 1, 1)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_DDL)
        conn.executemany("INSERT INTO plans VALUES (?, ?, ?, ?, ?)", PLANS)

        countries = list(COUNTRIES_CITIES)
        customers = []
        used_names: set[str] = set()
        for cid in range(1, n_customers + 1):
            while True:
                name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
                if name not in used_names:
                    used_names.add(name)
                    break
            country = rng.choice(countries)
            city = rng.choice(COUNTRIES_CITIES[country])
            email = name.lower().replace(" ", ".") + f"{cid}@example.com"
            signup = base + timedelta(days=rng.randrange(0, 700))
            customers.append((cid, name, email, country, city, signup.isoformat()))
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", customers)

        plan_price = {p[0]: p[2] for p in PLANS}
        plan_allowance = {p[0]: p[3] for p in PLANS}
        subscriptions = []
        sid = 0
        for cid, *_rest in customers:
            n_subs = 1 + (1 if rng.random() < 0.3 else 0)
            for _ in range(n_subs):
                sid += 1
                plan_id = rng.choice([1, 2, 2, 3, 3, 4, 5])
                start = base + timedelta(days=rng.randrange(30, 720))
                status = rng.choice(SUBSCRIPTION_STATUSES)
                end = None
                if status == "cancelled":
                    end = (start + timedelta(days=rng.randrange(30, 300))).isoformat()
                subscriptions.append(
                    (sid, cid, plan_id, start.isoformat(), end, status)
                )
        conn.executemany(
            "INSERT INTO subscriptions VALUES (?, ?, ?, ?, ?, ?)", subscriptions
        )

        invoices = []
        iid = 0
        for sub_id, cust_id, plan_id, start_s, _end, _status in subscriptions:
            start = date.fromisoformat(start_s)
            for k in range(rng.randrange(3, 7)):
                iid += 1
                inv_date = start + timedelta(days=30 * k)
                factor = rng.choice([1.0, 1.0, 1.0, 1.05, 1.1])
                amount = round(plan_price[plan_id] * factor, 2)
                invoices.append(
                    (iid, sub_id, cust_id, inv_date.isoformat(), amount,
                     rng.choice(INVOICE_STATUSES))
                )
        conn.executemany("INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)", invoices)

        usage = []
        uid = 0
        for sub_id, _cust_id, plan_id, start_s, _end, _status in subscriptions:
            start = date.fromisoformat(start_s)
            allowance = plan_allowance[plan_id]
            for k in range(3):
                uid += 1
                month = start + timedelta(days=30 * k)
                data_used = round(rng.uniform(0.2, 1.1) * allowance, 2)
                usage.append(
                    (uid, sub_id, month.strftime("%Y-%m"), data_used,
                     rng.randrange(10, 1800), rng.randrange(0, 300))
                )
        conn.executemany(
            "INSERT INTO usage_records VALUES (?, ?, ?, ?, ?, ?)", usage
        )

        tickets = []
        for tid in range(1, n_tickets + 1):
            cust_id = rng.randrange(1, n_customers + 1)
            created = base + timedelta(days=rng.randrange(60, 730))
            status = rng.choice(TICKET_STATUSES)
            resolution = None
            if status in ("resolved", "closed"):
                resolution = round(rng.uniform(0.2, 14.0), 1)
            tickets.append(
                (tid, cust_id, created.isoformat(), rng.choice(TICKET_CATEGORIES),
                 rng.choice(TICKET_PRIORITIES), status, resolution)
            )
        conn.executemany(
            "INSERT INTO support_tickets VALUES (?, ?, ?, ?, ?, ?, ?)", tickets
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def default_db_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "sample.db"


def ensure_database(db_path: str | Path | None = None) -> Path:
    path = Path(db_path) if db_path else default_db_path()
    if not path.exists():
        build_database(path)
    return path


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    target = Path(args[0]) if args else default_db_path()
    build_database(target)
    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        total = 0
        for t in tables:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            total += n
            print(f"{t}: {n} rows")
        print(f"Seeded {target} ({total} rows total, seed={SEED})")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
