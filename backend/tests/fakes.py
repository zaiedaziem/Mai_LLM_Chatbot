"""In-memory stand-ins for Supabase and the LLM.

The real clients are network-bound, which makes tests slow, flaky and dependent
on a live API key. FakeSupabase mimics just enough of the query builder for the
endpoints to run unchanged; FakeLLM implements our own LLMProvider interface,
so it never has to imitate a vendor SDK.
"""

import uuid
from datetime import datetime, timedelta, timezone

from src.llm import LLMProvider


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """Mimics the Supabase chained query builder (.select().eq().order().execute())."""

    def __init__(self, table, op, payload=None):
        self._table = table
        self._op = op
        self._payload = payload
        self._filters = []
        self._order_by = None
        self._order_desc = False

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def order(self, column, desc=False):
        self._order_by = column
        self._order_desc = desc
        return self

    def _matching(self):
        rows = self._table.rows
        for column, value in self._filters:
            rows = [r for r in rows if r.get(column) == value]
        return rows

    def execute(self):
        if self._op == "insert":
            row = dict(self._payload)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", self._table.next_timestamp())
            self._table.rows.append(row)
            return _Result([row])

        if self._op == "select":
            rows = self._matching()
            if self._order_by:
                rows = sorted(
                    rows, key=lambda r: r[self._order_by], reverse=self._order_desc
                )
            return _Result([dict(r) for r in rows])

        if self._op == "update":
            matched = self._matching()
            for row in matched:
                row.update(self._payload)
            return _Result([dict(r) for r in matched])

        if self._op == "delete":
            doomed = self._matching()
            self._table.rows = [r for r in self._table.rows if r not in doomed]
            if self._table.name == "sessions":
                # Mimic messages.session_id's ON DELETE CASCADE.
                doomed_ids = {r["id"] for r in doomed}
                self._table.db.table("messages").rows = [
                    m
                    for m in self._table.db.table("messages").rows
                    if m["session_id"] not in doomed_ids
                ]
            return _Result(doomed)

        raise NotImplementedError(self._op)


class _Table:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self.rows = []
        self._clock = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def next_timestamp(self):
        # Monotonic fake clock so insertion order is always recoverable by
        # created_at, even when rows are written in the same real millisecond.
        self._clock += timedelta(seconds=1)
        return self._clock.isoformat()

    def select(self, *_columns):
        return _Query(self, "select")

    def insert(self, payload):
        return _Query(self, "insert", payload)

    def update(self, payload):
        return _Query(self, "update", payload)

    def delete(self):
        return _Query(self, "delete")


class FakeSupabase:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.setdefault(name, _Table(self, name))

    def rows(self, name):
        return self.table(name).rows


class FakeLLM(LLMProvider):
    """Replays a scripted token list and records what it was asked."""

    def __init__(self, tokens=("Hello", " there", "!"), error=None):
        self._tokens = tokens
        self._error = error
        self.last_messages = None
        self.last_system_prompt = None
        self.call_count = 0

    def stream(self, messages, system_prompt=None):
        self.call_count += 1
        self.last_messages = messages
        self.last_system_prompt = system_prompt
        if self._error:
            raise self._error
        yield from self._tokens
