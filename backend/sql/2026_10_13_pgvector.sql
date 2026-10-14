-- SAGE pgvector migration: move chunk embeddings from Chroma into Supabase.
-- Run this in the Supabase SQL Editor once, after schema.sql.
--
-- Vector dimension (384) matches the default embedding model all-MiniLM-L6-v2.
-- If you change EMBEDDING_MODEL_NAME to a model with a different dimension,
-- change vector(384) here and re-ingest.

create extension if not exists vector;

alter table public.chunks
    add column if not exists embedding vector(384);

-- Cosine distance, to match the previous Chroma collection (hnsw:space=cosine).
create index if not exists idx_chunks_embedding
    on public.chunks using hnsw (embedding vector_cosine_ops);

-- Nearest-neighbour search with the same metadata filters the app used in Chroma.
-- Any null filter is ignored; pass only the ones you want applied.
create or replace function public.match_chunks(
    query_embedding vector(384),
    match_count int,
    filter_source_ids text[] default null,
    filter_knowledgebase_id uuid default null,
    filter_source_id uuid default null
)
returns table (
    id text,
    knowledgebase_id uuid,
    source_id uuid,
    chunk_index int,
    text text,
    token_estimate int,
    source_ref text,
    page_number int,
    section_title text,
    metadata jsonb,
    distance float
)
language sql stable
as $$
    select
        c.id, c.knowledgebase_id, c.source_id, c.chunk_index, c.text,
        c.token_estimate, c.source_ref, c.page_number, c.section_title,
        c.metadata, (c.embedding <=> query_embedding) as distance
    from public.chunks c
    where c.embedding is not null
      and (filter_source_ids is null or c.source_id = any(filter_source_ids::uuid[]))
      and (filter_knowledgebase_id is null or c.knowledgebase_id = filter_knowledgebase_id)
      and (filter_source_id is null or c.source_id = filter_source_id)
    order by c.embedding <=> query_embedding
    limit match_count;
$$;
