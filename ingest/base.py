"""Shared ingest logic. Each source runs as its own service account, which can only
INSERT into its own raw tables. It can't read them back, change them or delete them."""
import csv
import uuid

from psycopg import sql

from common.db import REPO, connect_as

EXPORTS = REPO / "data" / "exports"


def ingest(source: str) -> None:
    role = f"svc_ingest_{source}"
    files = sorted((EXPORTS / source).glob("*.csv"))
    if not files:
        raise SystemExit(f"No exports found for {source}. Run `just generate` first.")

    batch_id = str(uuid.uuid4())
    with connect_as(role) as conn:
        for path in files:
            table = f"{source}_{path.stem}"
            with path.open(newline="", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                columns = [*next(reader), "_batch_id", "_source_file"]
                copy_sql = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
                    sql.Identifier("raw"), sql.Identifier(table),
                    sql.SQL(", ").join(map(sql.Identifier, columns)),
                )
                count = 0
                with conn.cursor() as cur, cur.copy(copy_sql) as copy:
                    for row in reader:
                        copy.write_row([v if v != "" else None for v in row] + [batch_id, path.name])
                        count += 1
            print(f"  {role} -> raw.{table}: {count} rows (batch {batch_id[:8]})")
