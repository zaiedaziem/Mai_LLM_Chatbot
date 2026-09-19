-- One-off cleanup for databases used during early development.
--
-- The frontend used to create a session row on every page load, so any reload
-- (or a switch to a different dev port, which clears localStorage) left behind
-- a session that never received a message. Sessions are now created lazily on
-- the first send, so this only needs running once.

-- 1. Drop sessions that never received a message.
delete from sessions s
where not exists (
  select 1 from messages m where m.session_id = s.id
);

-- 2. Backfill titles for sessions that predate the `title` column, using the
--    same rule the API applies to new sessions: the first user message,
--    whitespace-collapsed, truncated to 50 characters with an ellipsis.
update sessions s
set title = first_message.title
from (
  select distinct on (m.session_id)
    m.session_id,
    case
      when length(trim(regexp_replace(m.content, '\s+', ' ', 'g'))) <= 50
        then trim(regexp_replace(m.content, '\s+', ' ', 'g'))
      else
        rtrim(left(trim(regexp_replace(m.content, '\s+', ' ', 'g')), 49)) || '…'
    end as title
  from messages m
  where m.role = 'user'
  order by m.session_id, m.created_at
) as first_message
where s.id = first_message.session_id
  and s.title is null;
