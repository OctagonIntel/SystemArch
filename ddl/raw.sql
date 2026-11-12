-- Raw landing tables. `just apply-policy` runs this as wh_owner, so wh_owner owns them
-- and the ingest accounts only ever get INSERT.
--
-- Every column is text on purpose. Raw keeps exactly what the source sent and staging
-- does the typing. Raw is also append-only: each load gets a _batch_id, and staging
-- picks the newest row per key.

CREATE TABLE IF NOT EXISTS raw.hr_employees (
    employee_id    text,
    first_name     text,
    last_name      text,
    email          text,
    phone          text,
    date_of_birth  text,
    national_id    text,
    department     text,
    job_title      text,
    region         text,
    country        text,
    hire_date      text,
    salary_eur     text,
    manager_id     text,
    _batch_id      text NOT NULL,
    _source_file   text,
    _loaded_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.crm_customers (
    customer_id       text,
    company_name      text,
    contact_name      text,
    contact_email     text,
    contact_phone     text,
    region            text,
    country           text,
    account_owner_id  text,
    created_at        text,
    _batch_id         text NOT NULL,
    _source_file      text,
    _loaded_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.crm_deals (
    deal_id       text,
    customer_id   text,
    owner_id      text,
    amount_eur    text,
    stage         text,
    created_at    text,
    close_date    text,
    _batch_id     text NOT NULL,
    _source_file  text,
    _loaded_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.support_tickets (
    ticket_id      text,
    customer_id    text,
    contact_email  text,
    subject        text,
    priority       text,
    status         text,
    opened_at      text,
    closed_at      text,
    agent_id       text,
    _batch_id      text NOT NULL,
    _source_file   text,
    _loaded_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.finance_invoices (
    invoice_id      text,
    invoice_number  text,
    customer_id     text,
    invoice_date    text,
    due_date        text,
    amount          text,
    currency        text,
    status          text,
    paid_at         text,
    _batch_id       text NOT NULL,
    _source_file    text,
    _loaded_at      timestamptz NOT NULL DEFAULT now()
);
