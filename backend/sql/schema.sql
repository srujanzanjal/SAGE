-- SAGE MVP Supabase PostgreSQL schema
-- Run this in Supabase SQL Editor before starting the backend.

create extension if not exists "pgcrypto";

create table if not exists public.knowledgebases (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    source_type text not null check (source_type in ('website', 'pdf', 'video', 'github')),
    canonical_ref text not null unique,
    status text not null default 'processing' check (status in ('processing', 'ready', 'failed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.sources (
    id uuid primary key default gen_random_uuid(),
    knowledgebase_id uuid not null references public.knowledgebases(id) on delete cascade,
    source_type text not null check (source_type in ('website', 'pdf', 'video', 'github')),
    original_ref text not null,
    canonical_ref text not null unique,
    title text,
    status text not null default 'ready' check (status in ('processing', 'ready', 'failed')),
    content_hash text,
    text_length integer not null default 0,
    meta jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.chunks (
    id text primary key,
    knowledgebase_id uuid not null references public.knowledgebases(id) on delete cascade,
    source_id uuid not null references public.sources(id) on delete cascade,
    chunk_index integer not null,
    text text not null,
    token_estimate integer not null default 0,
    char_count integer not null default 0,
    source_ref text not null,
    page_number integer,
    section_title text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.query_history (
    id uuid primary key default gen_random_uuid(),
    knowledgebase_id uuid references public.knowledgebases(id) on delete set null,
    source_id uuid references public.sources(id) on delete set null,
    question text not null,
    rewritten_query text,
    mode text not null check (mode in ('grounded', 'exploratory')),
    answer text,
    confidence numeric,
    retrieved_chunk_ids jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_sources_kb on public.sources(knowledgebase_id);
create index if not exists idx_sources_canonical on public.sources(canonical_ref);
create index if not exists idx_chunks_kb on public.chunks(knowledgebase_id);
create index if not exists idx_chunks_source on public.chunks(source_id);
create index if not exists idx_query_history_kb on public.query_history(knowledgebase_id);

create or replace function public.set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_knowledgebases_updated_at on public.knowledgebases;
create trigger trg_knowledgebases_updated_at
before update on public.knowledgebases
for each row execute function public.set_updated_at();

drop trigger if exists trg_sources_updated_at on public.sources;
create trigger trg_sources_updated_at
before update on public.sources
for each row execute function public.set_updated_at();

-- Recommended for local testing only: use SUPABASE_KEY as service role key.
-- If you later expose client-side access, add Row Level Security policies carefully.

-- Optional cleanup helper for query history. Query history is disabled by default in the app.
create or replace function public.purge_old_query_history(retention_days integer default 30)
returns integer as $$
declare
    deleted_count integer;
begin
    delete from public.query_history
    where created_at < now() - make_interval(days => retention_days);
    get diagnostics deleted_count = row_count;
    return deleted_count;
end;
$$ language plpgsql;
