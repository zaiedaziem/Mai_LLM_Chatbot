-- Full schema for a fresh Supabase project.
-- Run in: Dashboard > SQL Editor > New query. Safe to re-run.
--
-- Already have a database from an earlier version? Run the files in
-- migrations/ instead, in order -- this script will not alter existing tables.

-- One row per conversation. `title` is NULL until the first message arrives,
-- at which point the API sets it from that message (truncated to 50 chars);
-- the user can rename it afterwards via PATCH /sessions/{id}.
create table if not exists sessions (
  id uuid primary key default gen_random_uuid(),
  title text,
  created_at timestamptz not null default now()
);

-- One row per turn. Deleting a session cascades to its transcript, so the API
-- can remove a conversation with a single DELETE.
create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references sessions(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz not null default now()
);

-- The sidebar lists sessions newest-first.
create index if not exists sessions_created_idx
  on sessions (created_at desc);

-- History is always read as "all messages for one session, in order".
create index if not exists messages_session_created_idx
  on messages (session_id, created_at);

-- The project has "Enable automatic RLS" on, so every new table gets RLS
-- turned on with zero policies (all access denied) unless we add our own.
-- This app has no per-user auth (the assessment explicitly says none is
-- needed) and talks to Supabase only through the backend's anon key, so a
-- single permissive policy per table is the correct scope here -- it is not
-- meant to isolate users from each other, only to satisfy RLS being on.
alter table sessions enable row level security;
alter table messages enable row level security;

drop policy if exists "anon full access" on sessions;
create policy "anon full access" on sessions
  for all using (true) with check (true);

drop policy if exists "anon full access" on messages;
create policy "anon full access" on messages
  for all using (true) with check (true);
