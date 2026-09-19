"""In-memory stand-ins for Supabase and Groq.

The real clients are network-bound, which makes tests slow, flaky and dependent
on a live API key. These fakes mimic just enough of each client's surface for
the endpoints to run unchanged.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


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

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def order(self, column):
        self._order_by = column
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
                rows = sorted(rows, key=lambda r: r[self._order_by])
            return _Result([dict(r) for r in rows])

        if self._op == "delete":
            doomed = self._matching()
            self._table.rows = [r for r in self._table.rows if r not in doomed]
            return _Result(doomed)

        raise NotImplementedError(self._op)


class _Table:
    def __init__(self):
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

    def delete(self):
        return _Query(self, "delete")


class FakeSupabase:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        return self._tables.setdefault(name, _Table())

    def rows(self, name):
        return self._tables.setdefault(name, _Table()).rows


class FakeGroq:
    """Records the messages it was called with and replays a scripted response."""

    def __init__(self, tokens=("Hello", " there", "!"), error=None):
        self._tokens = tokens
        self._error = error
        self.last_messages = None
        self.call_count = 0

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model, messages, stream, max_tokens=None):
        self.call_count += 1
        self.last_messages = messages
        if self._error:
            raise self._error
        return iter(
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=token))]
            )
            for token in self._tokens
        )
