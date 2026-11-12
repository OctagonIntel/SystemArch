"""Generates the fake source-system exports as CSV files in data/exports/<source>/.

Fixed seed and a fixed "today", so the same data comes out every run and tests stay stable.
A few rows get deliberately messy values (stray spaces, uppercase emails) so staging
has some real cleaning to do.
"""
import csv
import random
import unicodedata
from datetime import date, datetime, time, timedelta
from pathlib import Path

from faker import Faker

SEED = 42
AS_OF = date(2026, 10, 31)
OUT = Path(__file__).resolve().parent.parent / "data" / "exports"

REGIONS = {
    "EU": {"weight": 40, "locales": {"en_GB": "United Kingdom", "de_DE": "Germany", "fr_FR": "France", "nl_NL": "Netherlands"}, "currency": "EUR"},
    "US": {"weight": 45, "locales": {"en_US": "United States"}, "currency": "USD"},
    "APAC": {"weight": 15, "locales": {"en_AU": "Australia", "en_NZ": "New Zealand"}, "currency": "AUD"},
}

COUNTRY_CODES = {
    "United Kingdom": "GB", "Germany": "DE", "France": "FR", "Netherlands": "NL",
    "United States": "US", "Australia": "AU", "New Zealand": "NZ",
}

# department: (headcount, salary min, salary max, job titles)
DEPARTMENTS = {
    "Sales": (60, 52000, 98000, ["Account Executive", "Sales Development Rep", "Sales Manager"]),
    "Support": (40, 36000, 62000, ["Support Agent", "Senior Support Agent", "Support Lead"]),
    "Finance": (20, 50000, 95000, ["Accountant", "Financial Analyst", "Controller"]),
    "HR": (12, 45000, 82000, ["HR Generalist", "Recruiter", "HR Business Partner"]),
    "Engineering": (90, 62000, 135000, ["Software Engineer", "Senior Engineer", "Engineering Manager"]),
    "Marketing": (18, 45000, 88000, ["Marketing Specialist", "Content Lead", "Growth Manager"]),
}

DEAL_STAGES = ["prospecting", "proposal", "negotiation", "won", "lost"]
TICKET_SUBJECTS = [
    "Cannot log in", "Invoice amount looks wrong", "Export to CSV fails", "Need a new user added",
    "Report is loading slowly", "Password reset email not arriving", "Integration stopped syncing",
    "Question about renewal", "Feature request: dark mode", "Data missing from dashboard",
]

rng = random.Random(SEED)
fakers: dict[str, Faker] = {}
for i, region in enumerate(REGIONS.values()):
    for j, locale in enumerate(region["locales"]):
        f = Faker(locale)
        f.seed_instance(SEED + i * 10 + j)
        fakers[locale] = f


def ascii_slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch == ".").strip(".")


def pick_region() -> str:
    return rng.choices(list(REGIONS), weights=[r["weight"] for r in REGIONS.values()])[0]


def pick_locale(region: str) -> tuple[str, str]:
    locale, country = rng.choice(list(REGIONS[region]["locales"].items()))
    return locale, country


def rand_date(start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, max(0, (end - start).days)))


def rand_datetime(start: date, end: date) -> datetime:
    return datetime.combine(rand_date(start, end), time(rng.randint(7, 19), rng.randint(0, 59)))


def messy(value: str, chance: float = 0.04) -> str:
    """Occasionally return the value the way a real source system would mangle it."""
    if rng.random() >= chance:
        return value
    return rng.choice([value.upper(), f" {value}", f"{value}  "])


def employees() -> list[dict]:
    rows, used_emails, n = [], set(), 0
    for dept, (headcount, lo, hi, titles) in DEPARTMENTS.items():
        dept_ids = []
        for k in range(headcount):
            n += 1
            region = pick_region()
            locale, country = pick_locale(region)
            fake = fakers[locale]
            first, last = fake.first_name(), fake.last_name()
            email = f"{ascii_slug(first)}.{ascii_slug(last)}@corp.example"
            while email in used_emails:
                email = email.replace("@", f"{rng.randint(1, 9)}@", 1)
            used_emails.add(email)
            emp_id = f"E{n:04d}"
            if k == 0:
                manager = ""  # department head
            elif k <= max(1, headcount // 10):
                manager = dept_ids[0]
            else:
                manager = rng.choice(dept_ids[1:max(2, headcount // 10 + 1)])
            dept_ids.append(emp_id)
            rows.append({
                "employee_id": emp_id,
                "first_name": messy(first),
                "last_name": last,
                "email": messy(email),
                "phone": fake.phone_number(),
                "date_of_birth": fake.date_of_birth(minimum_age=21, maximum_age=64).isoformat(),
                "national_id": f"{COUNTRY_CODES[country]}-{rng.randint(10**8, 10**9 - 1)}",
                "department": dept,
                "job_title": titles[-1] if manager == "" else rng.choice(titles[:-1]),
                "region": region,
                "country": country,
                "hire_date": rand_date(date(2015, 1, 1), AS_OF).isoformat(),
                "salary_eur": str(round(rng.uniform(lo, hi) / 500) * 500),
                "manager_id": manager,
            })
    return rows


def customers(emps: list[dict]) -> list[dict]:
    sales_by_region = {r: [e["employee_id"] for e in emps if e["department"] == "Sales" and e["region"] == r] for r in REGIONS}
    rows = []
    for n in range(1, 601):
        region = pick_region()
        locale, country = pick_locale(region)
        fake = fakers[locale]
        company = fake.company()
        first, last = fake.first_name(), fake.last_name()
        domain = ascii_slug(company.replace(" ", ""))[:20] or "customer"
        rows.append({
            "customer_id": f"C{n:04d}",
            "company_name": messy(company),
            "contact_name": f"{first} {last}",
            "contact_email": messy(f"{ascii_slug(first)}.{ascii_slug(last)}@{domain}.example"),
            "contact_phone": fake.phone_number(),
            "region": region,
            "country": country,
            "account_owner_id": rng.choice(sales_by_region[region]),
            "created_at": rand_datetime(date(2019, 1, 1), AS_OF).isoformat(sep=" "),
        })
    return rows


def deals(custs: list[dict]) -> list[dict]:
    rows = []
    for n in range(1, 1501):
        c = rng.choice(custs)
        created = rand_date(datetime.fromisoformat(c["created_at"]).date(), AS_OF)
        stage = rng.choices(DEAL_STAGES, weights=[20, 15, 10, 35, 20])[0]
        closed = stage in ("won", "lost")
        rows.append({
            "deal_id": f"D{n:05d}",
            "customer_id": c["customer_id"],
            "owner_id": c["account_owner_id"],
            "amount_eur": str(rng.randint(5, 250) * 1000),
            "stage": stage,
            "created_at": created.isoformat(),
            "close_date": min(created + timedelta(days=rng.randint(10, 180)), AS_OF).isoformat() if closed else "",
        })
    return rows


def tickets(custs: list[dict], emps: list[dict]) -> list[dict]:
    agents_by_region = {r: [e["employee_id"] for e in emps if e["department"] == "Support" and e["region"] == r] for r in REGIONS}
    all_agents = [a for ids in agents_by_region.values() for a in ids]
    rows = []
    for n in range(1, 4001):
        c = rng.choice(custs)
        opened = rand_datetime(max(date(2024, 11, 1), datetime.fromisoformat(c["created_at"]).date()), AS_OF)
        age_days = (AS_OF - opened.date()).days
        status = "closed" if age_days > 14 and rng.random() < 0.95 else rng.choice(["open", "pending", "closed"])
        closed_at = ""
        if status == "closed":
            closed_at = min(opened + timedelta(hours=rng.randint(1, 240)), datetime.combine(AS_OF, time(23, 59))).isoformat(sep=" ")
        rows.append({
            "ticket_id": f"T{n:05d}",
            "customer_id": c["customer_id"],
            "contact_email": c["contact_email"].strip().lower(),
            "subject": rng.choice(TICKET_SUBJECTS),
            "priority": rng.choices(["low", "normal", "high", "urgent"], weights=[30, 45, 20, 5])[0],
            "status": status,
            "opened_at": opened.isoformat(sep=" "),
            "closed_at": closed_at,
            "agent_id": rng.choice(agents_by_region[c["region"]] or all_agents),
        })
    return rows


def invoices(custs: list[dict]) -> list[dict]:
    rows = []
    for n in range(1, 2501):
        c = rng.choice(custs)
        inv_date = rand_date(max(date(2023, 1, 1), datetime.fromisoformat(c["created_at"]).date()), AS_OF)
        due = inv_date + timedelta(days=30)
        paid_at = ""
        if rng.random() < 0.85 and inv_date + timedelta(days=5) <= AS_OF:
            paid = inv_date + timedelta(days=rng.randint(5, 60))
            if paid <= AS_OF:
                paid_at = paid.isoformat()
        status = "paid" if paid_at else ("overdue" if due < AS_OF else "open")
        rows.append({
            "invoice_id": f"I{n:05d}",
            "invoice_number": f"INV-{inv_date.year}-{n:05d}",
            "customer_id": c["customer_id"],
            "invoice_date": inv_date.isoformat(),
            "due_date": due.isoformat(),
            "amount": f"{rng.randint(500, 60000)}.{rng.randint(0, 99):02d}",
            "currency": REGIONS[c["region"]]["currency"],
            "status": status,
            "paid_at": paid_at,
        })
    return rows


def write(source: str, table: str, rows: list[dict]) -> None:
    path = OUT / source / f"{table}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {path.relative_to(OUT.parent.parent)}: {len(rows)} rows")


def main() -> None:
    emps = employees()
    custs = customers(emps)
    print("Generating source exports:")
    write("hr", "employees", emps)
    write("crm", "customers", custs)
    write("crm", "deals", deals(custs))
    write("support", "tickets", tickets(custs, emps))
    write("finance", "invoices", invoices(custs))


if __name__ == "__main__":
    main()
