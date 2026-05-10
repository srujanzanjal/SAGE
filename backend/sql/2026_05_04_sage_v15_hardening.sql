-- SAGE hardening migration for existing Supabase projects.
-- Run this in Supabase SQL Editor if your existing schema was created before Video/GitHub modules.

alter table public.knowledgebases
    drop constraint if exists knowledgebases_source_type_check;

alter table public.knowledgebases
    add constraint knowledgebases_source_type_check
    check (source_type in ('website', 'pdf', 'video', 'github'));

alter table public.sources
    drop constraint if exists sources_source_type_check;

alter table public.sources
    add constraint sources_source_type_check
    check (source_type in ('website', 'pdf', 'video', 'github'));

-- Prefer deleting stored query history for removed sources/knowledgebases instead of leaving sensitive questions around.
delete from public.query_history
where knowledgebase_id is null and source_id is null;

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
