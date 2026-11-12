"""Shared fixtures. Access tests connect as the real person or service account.
The admin connection is only used to read the catalog and ground truth."""
from collections import OrderedDict

import psycopg
import pytest

from common.db import admin_connect, connect_as
from generator.policy import load_policy

ALLOW, DENY = "allow", "deny"


class Sessions:
    """A few open connections, reused across tests. The Supabase pooler caps connections."""

    def __init__(self, size: int = 3):
        self.size = size
        self.open: OrderedDict[str, psycopg.Connection] = OrderedDict()

    def _get(self, role: str) -> psycopg.Connection:
        if role in self.open:
            self.open.move_to_end(role)
            return self.open[role]
        while len(self.open) >= self.size:
            self.open.popitem(last=False)[1].close()
        self.open[role] = connect_as(role, autocommit=True)
        return self.open[role]

    def run(self, role: str, query: str, params=None) -> tuple[str, list]:
        """Runs a query as `role`. Returns (allow, rows) or (deny, message).
        Only a permission error counts as deny. Anything else is a broken test and raises."""
        for attempt in (1, 2):
            conn = self._get(role)
            try:
                cur = conn.execute(query, params)
                return ALLOW, cur.fetchall() if cur.description else []
            except psycopg.errors.InsufficientPrivilege as e:
                return DENY, str(e).splitlines()[0]
            except psycopg.OperationalError:
                self.open.pop(role, None)
                if attempt == 2:
                    raise

    def close(self):
        for conn in self.open.values():
            conn.close()


@pytest.fixture(scope="session")
def policy():
    return load_policy()


@pytest.fixture(scope="session")
def sessions():
    s = Sessions()
    yield s
    s.close()


@pytest.fixture(scope="session")
def admin():
    with admin_connect(autocommit=True) as conn:
        yield conn
