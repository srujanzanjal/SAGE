-- Eval-only embedding store: compare embedding models without touching the
-- production chunks.embedding column (the pgvector analog of Chroma's one
-- collection per model). Run in the Supabase SQL Editor before an eval sweep.

create extension if not exists vector;

-- `vector` with no dimension so models of different widths (384, 768, ...) coexist.
-- No ANN index: an unsized vector column can't be HNSW-indexed, and eval corpora
-- are small enough that a sequential scan is fine.
create table if not exists public.eval_chunk_embeddings (
    chunk_id text not null references public.chunks(id) on delete cascade,
    model text not null,
    embedding vector not null,
    primary key (chunk_id, model)
);

-- Same shape and filters as match_chunks, but reads one model's eval vectors and
-- joins chunks for the text/metadata.
create or replace function public.match_chunks_eval(
    query_embedding vector,
    match_model text,
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
        c.metadata, (e.embedding <=> query_embedding) as distance
    from public.eval_chunk_embeddings e
    join public.chunks c on c.id = e.chunk_id
    where e.model = match_model
      and (filter_source_ids is null or c.source_id = any(filter_source_ids::uuid[]))
      and (filter_knowledgebase_id is null or c.knowledgebase_id = filter_knowledgebase_id)
      and (filter_source_id is null or c.source_id = filter_source_id)
    order by e.embedding <=> query_embedding
    limit match_count;
$$;
