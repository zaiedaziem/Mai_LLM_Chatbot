# Streaming LLM Chat — MaiStorage Assessment (Task 2, Question 2)

A chat interface that streams an LLM's reply token-by-token and remembers the
conversation across turns.

**Stack:** FastAPI (SSE streaming) · React + Vite · Supabase (Postgres) · Groq (`openai/gpt-oss-20b`)

The model is configurable via the `GROQ_MODEL` env var — Groq rotates its
catalogue, so check `GET /openai/v1/models` if the default stops resolving.

---

## Running it

### 1. Supabase

Create a project at [supabase.com](https://supabase.com), then run
[`backend/schema.sql`](backend/schema.sql) in **SQL Editor → New query**.

Copy the project URL and `anon` key from **Settings → API**.

### 2. Groq

Get a free key at [console.groq.com](https://console.groq.com/keys).

### 3. Backend

```bash
cd backend
python -m venv venv                      # create an isolated Python environment in ./venv
venv/Scripts/activate                    # macOS/Linux: source venv/bin/activate
                                          # ^ switches this shell to use venv's Python, so installs
                                          #   below land here instead of your system Python
pip install -r requirements-dev.txt      # install FastAPI, Supabase, Groq, pytest, etc. into venv
cp .env.example .env                     # then fill in the three keys (Supabase URL/key, Groq key)
uvicorn src.main:app --reload            # start the API server
                                          # ^ src.main:app = "the `app` object in src/main.py"
                                          #   --reload     = restart automatically on file changes
```

Runs on http://localhost:8000. Every command after `activate` must be run
with the venv still active — if you open a new terminal, run `activate`
again first.

### 4. Frontend

```bash
cd frontend
npm install     # download React, Vite and other dependencies into node_modules
npm run dev     # start the Vite dev server with hot-reload
```

Open http://localhost:5173.

### Or with Docker

Put `GROQ_API_KEY`, `SUPABASE_URL` and `SUPABASE_KEY` in a `.env` at the repo
root, then:

```bash
docker compose up --build
```

Frontend on http://localhost:3000, API on http://localhost:8000.

---

## Project structure

```
backend/
├── src/
│   ├── main.py            wiring only: CORS + routers
│   ├── config.py          every env var, read in one place
│   ├── dependencies.py    get_db / get_llm / get_system_prompt (swapped out in tests)
│   ├── api/
│   │   ├── sessions.py    /sessions CRUD + /sessions/{id}/messages
│   │   └── chat.py        /chat/stream
│   ├── llm/
│   │   ├── base.py        LLMProvider interface
│   │   └── groq.py        GroqProvider — the only file that imports the Groq SDK
│   ├── middleware/
│   │   └── rate_limit.py  sliding-window limiter, per client IP
│   └── prompts/
│       └── system_prompt.md
├── tests/
├── migrations/            one-off SQL for databases created before a schema change
└── schema.sql             full schema for a fresh project
frontend/
└── src/
    ├── App.jsx            state + chat window
    ├── Sidebar.jsx        session list, rename, delete
    └── api.js             fetch wrappers + the SSE parser
```

The split follows *reasons to change*: the LLM vendor, the rate-limit policy
and the HTTP routes each vary independently, so each has its own module. Before
those concerns existed the backend was a single `main.py`, which was the right
size for it at the time.

---

## Thought process

### Why Server-Sent Events rather than WebSockets

Token streaming is strictly one-directional: the client sends one prompt, then
only listens. WebSockets buy bidirectional traffic that this app never uses, at
the cost of a stateful connection to keep alive, reconnect and scale. SSE runs
over plain HTTP, so it survives ordinary proxies and load balancers, and
`StreamingResponse` expresses it in a handful of lines. The one real SSE
limitation — six concurrent connections per browser origin — does not bite
because a stream here is short-lived and there is only ever one in flight.

### Where the conversation memory lives

The model itself is stateless; every call must carry the whole history. The
alternative to storing it is keeping the transcript in browser memory and
posting it back each turn, which loses everything on refresh and lets the client
rewrite what the model believes was said.

So the database is the single source of truth. Each turn:

1. the user's message is written to `messages`
2. every row for that session is read back in `created_at` order
3. that list is what gets sent to Groq

Persisting *before* reading means the new message is naturally part of the
history — no separate append step that could drift out of order. A page reload
replays the same rows, so the UI and the model always agree on what was said.

### Why the assistant reply is saved after the stream, not during

Writing each token would mean one round-trip to Postgres per token. Instead the
generator accumulates into `reply` and performs a single insert once the stream
completes. The cost is that a connection dropped mid-stream loses that reply —
an acceptable trade, since a half-written answer is not worth resuming, and the
user's own message is already safe.

### Errors inside a stream

Once `StreamingResponse` begins, the HTTP status is already on the wire — a
later failure cannot become a 500. Provider errors are therefore sent in-band as
a `{"error": ...}` frame, which the client renders as a failed bubble. The
`return` after that frame is what keeps a partial reply out of the database.

### Dependency injection for the clients

`get_db` and `get_llm` are `@lru_cache`'d factories behind `Depends`. This keeps
credentials out of import time (the module imports fine without them, and a
missing key raises a clear error at request time instead of a cryptic one at
startup) and lets the tests substitute in-memory fakes through
`app.dependency_overrides` — no network, no monkeypatching of globals.

### The provider abstraction

The streaming endpoint talks to an `LLMProvider` interface with one method,
`stream(messages, system_prompt)`. `GroqProvider` is the only implementation,
and the only file that imports the Groq SDK. Swapping vendors is a new subclass
and one line in `dependencies.py`; the endpoint does not change.

The system prompt is passed *separately* from the conversation on purpose.
Providers attach it differently — a `"system"` role message for OpenAI-style
APIs, a `system_instruction` argument for Gemini — and the endpoint should not
have to know which. It also keeps the stored history clean: the database holds
only real turns, so a reload replays exactly what the user saw.

A side effect worth naming: the test double implements our four-line interface
instead of imitating a vendor SDK, which made it roughly half the size.

### Rate limiting

A sliding window per client IP, applied to `/chat/stream` only — the endpoint
that costs money. It is a FastAPI dependency rather than ASGI middleware
precisely so that cheap endpoints (listing sessions, loading history) are never
throttled. Rejected requests get a `429` with a `Retry-After` header, which the
frontend reads to show a countdown; `expose_headers` in the CORS config is what
lets the browser see that header cross-origin.

State is in-process memory: it resets on restart and is not shared between
workers. That is the right trade for a single-instance demo. The production
version is the same algorithm with the timestamps in Redis. Limits are
configurable via `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS`.

### The system prompt

Loaded from `src/prompts/system_prompt.md`, resolved relative to the file
rather than the working directory so it is found no matter where uvicorn is
launched from. It is injected as a proper system message, never concatenated
onto the user's text — the latter weakens the instruction and lets a user
override it.

### The SSE parser's buffer

`reader.read()` yields network chunks, not lines; a chunk can end halfway
through `data: {"content":"hel`. The client therefore keeps a `buffer`, splits
on `\n`, and holds the final (possibly incomplete) element back until the
newline that finishes it arrives. Parsing chunks directly appears to work in
local testing and corrupts tokens under real network conditions.

---

## Test suite

```bash
cd backend && python -m pytest tests/ -q
```

34 tests, <1s, no network. `tests/fakes.py` provides an in-memory Supabase
(mimicking the chained `.select().eq().order().execute()` builder, including
`ON DELETE CASCADE`) and a `FakeLLM` that implements the `LLMProvider`
interface, replays a scripted token list, and records what it was asked. Both
are wired in through `app.dependency_overrides` in `conftest.py`.

The suite is organised around the things that can independently break.

**1. Session lifecycle** — a session can be created and its id persisted;
history starts empty; deleting a session removes its messages too; deleting one
session leaves another intact; and a deleted session can no longer be chatted
with. Unknown session ids are rejected with a 404 rather than silently creating
orphan messages.

**2. Session titles** — a new session has no title; the first message sets one;
an over-long first message is truncated; and a *second* message does not
overwrite it (the regression that would otherwise rename a conversation on every
turn). Renaming is asserted to persist, to 404 on an unknown id, and to reject
an empty title.

**3. Streaming contract** — the response really is `text/event-stream`, and
tokens arrive as *separate* frames ending in `{"done": true}`. That per-frame
assertion is the one that would catch the most likely regression: buffering the
whole reply and flushing it once still produces correct text, still passes a
naive "did I get the right answer" test, and completely defeats the purpose of
the feature. A provider failure is asserted to arrive as an in-band error frame
on a 200 response.

**4. Persistence** — both sides of a turn are stored in the right order, and the
stored assistant message is asserted to equal the concatenation of the streamed
frames. That equality is what guarantees a page reload shows the user exactly
what they watched appear. A failed turn is asserted to leave only the user's
message behind.

**5. Conversational memory** — the requirement "the LLM should know what the
user asked previously" is only really pinned down by inspecting what was sent to
the model, so `FakeLLM` records it. The first turn must send just the new
message; the second must replay turn one's question *and* answer alongside it.
Sessions are asserted not to leak history into each other, and a new session
after a delete is asserted to start empty. The system prompt is asserted to
reach the provider *without* appearing in the stored conversation.

**6. Provider** (`test_groq_provider.py`) — `GroqProvider` is unit-tested with a
stub SDK client: empty deltas are dropped, the system prompt becomes the first
`"system"` message, and no prompt means no system message. These are Groq's
quirks, so they are tested where the Groq code lives, not in the endpoint.

**7. Rate limiting** (`test_rate_limit.py`) — requests under the limit succeed;
the one over it gets `429` with `Retry-After`; a rejected message is asserted
*not* to reach the database (otherwise a reload would show a turn with no reply);
and cheap endpoints are asserted to be unaffected. The limit is patched low via
`monkeypatch` so the tests run in milliseconds.

### What is deliberately not covered

No live calls to Groq or Supabase — those test someone else's uptime, not this
code. No React component tests: the interesting frontend logic is the SSE
buffering in `api.js`, and the rest is rendering that is faster to verify by
looking at it.

---

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/sessions` | Start a session, returns `session_id` |
| `GET` | `/sessions` | List all sessions, newest first |
| `PATCH` | `/sessions/{session_id}` | Rename a session |
| `DELETE` | `/sessions/{session_id}` | Delete a session and its messages |
| `GET` | `/sessions/{session_id}/messages` | Replay stored history |
| `POST` | `/chat/stream` | Stream a reply as SSE — rate limited |

Interactive docs at http://localhost:8000/docs.

---

## Multi-session history

The brief only required a single session, but the app keeps a sidebar of past
conversations, because a chat you cannot return to is hard to demo and hard to
trust.

A session is titled automatically from its first user message (truncated to 50
characters), which avoids an extra LLM call purely for naming and means the
title is available the instant the first message is sent. Titles are editable —
the auto-title is a starting point, not a decision.

`DELETE /sessions/{id}` removes the session row; `messages.session_id` is
declared `ON DELETE CASCADE`, so the transcript goes with it in one statement
rather than two round trips that could half-fail.

If your `sessions` table predates the `title` column, apply
[`migrations/001_add_session_title.sql`](backend/migrations/001_add_session_title.sql)
— `schema.sql` is `CREATE TABLE IF NOT EXISTS`, so it will not alter a table
that already exists.
