-- Run this in the Supabase SQL Editor (Dashboard > SQL Editor > New query)

create table if not exists sessions (
  id uuid primary key default gen_random_uuid(),
  title text,
  created_at timestamptz not null default now()
);

create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references sessions(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz not null default now()
);

-- History is always read as "all messages for one session, in order"
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

create policy "anon full access" on sessions
  for all using (true) with check (true);

create policy "anon full access" on messages
  for all using (true) with check (true);
