-- Run this once in Supabase SQL Editor if your `sessions` table was created
-- before the `title` column existed (schema.sql alone won't add it, since it
-- only runs CREATE TABLE IF NOT EXISTS).
alter table sessions add column if not exists title text;
