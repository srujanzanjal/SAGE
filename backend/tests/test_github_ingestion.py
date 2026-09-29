from __future__ import annotations

from pathlib import Path

from app.models.schemas import IngestResponse
from app.services import ingestion_pipeline, qa_pipeline
from app.services.github_repo import RepoRef
from app.services.retrieval_types import RetrievedChunk


class FakeSettings:
    chunk_size_chars = 500
    chunk_overlap_chars = 0


class FakeEmbeddingService:
    def embed_documents(self, documents):
        return [[0.0] * 3 for _ in documents]


class FakeVectorStore:
    def get_overview_chunks(self, source_ids):
        return []

    def get_edge_chunks(self, source_id, from_end, count=2):
        return []

    def __init__(self):
        self.calls = []

    def upsert_chunks(self, **kwargs):
        self.calls.append(kwargs)


class FakeRepo:
    def __init__(self):
        self.created_knowledgebases = []
        self.created_sources = []
        self.inserted_chunks = []
        self.updated_status = []

    def get_knowledgebase_by_canonical_ref(self, canonical_ref):
        return None

    def get_source_by_canonical_ref(self, canonical_ref):
        return None

    def create_knowledgebase(self, *, name, source_type, canonical_ref):
        payload = {"id": "kb_1", "name": name, "source_type": source_type, "canonical_ref": canonical_ref}
        self.created_knowledgebases.append(payload)
        return payload

    def create_source(self, **kwargs):
        payload = {"id": "src_1", **kwargs}
        self.created_sources.append(payload)
        return payload

    def update_knowledgebase_status(self, knowledgebase_id, status):
        self.updated_status.append((knowledgebase_id, status))

    def insert_chunks(self, **kwargs):
        self.inserted_chunks.append(kwargs)

    def get_chunks_count(self, knowledgebase_id):
        return 0


def test_ingest_github_creates_line_metadata_and_persists_chunks(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "README.md").write_text("# Sample\n\nThis is a repo.", encoding="utf-8")
    src_dir = repo_root / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    fake_repo = FakeRepo()
    fake_vectors = FakeVectorStore()

    monkeypatch.setattr(ingestion_pipeline, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(ingestion_pipeline, "SupabaseRepository", lambda: fake_repo)
    monkeypatch.setattr(ingestion_pipeline, "get_embedding_service", lambda: FakeEmbeddingService())
    monkeypatch.setattr(ingestion_pipeline, "get_vector_store", lambda: fake_vectors)
    monkeypatch.setattr(
        ingestion_pipeline,
        "fetch_repository",
        lambda url, branch=None: (str(repo_root), RepoRef(owner="octocat", repo="hello-world", branch=branch, canonical="https://github.com/octocat/hello-world")),
    )

    result = ingestion_pipeline.ingest_github("https://github.com/octocat/hello-world", branch="main")

    assert isinstance(result, IngestResponse)
    assert result.source_type == "github"
    assert result.repo_owner == "octocat"
    assert result.repo_name == "hello-world"
    assert result.branch == "main"
    assert result.files_indexed == 2
    assert result.files_skipped == 0
    assert result.chunks_count >= 2
    assert fake_repo.updated_status[-1] == ("kb_1", "ready")

    assert len(fake_vectors.calls) == 1
    vector_call = fake_vectors.calls[0]
    assert vector_call["source_type"] == "github"
    assert vector_call["source_id"] == "src_1"
    assert len(vector_call["chunks"]) == len(vector_call["chunk_ids"])
    assert any(chunk.extra_metadata.get("file_path") == "src/app.py" for chunk in vector_call["chunks"])
    assert any(chunk.extra_metadata.get("language") == "Python" for chunk in vector_call["chunks"])

    assert len(fake_repo.inserted_chunks) == 1
    inserted = fake_repo.inserted_chunks[0]
    assert inserted["source_type"] == "github"
    assert inserted["source_id"] == "src_1"
    assert any(row.extra_metadata.get("file_path") == "README.md" for row in inserted["chunks"])


def test_build_context_includes_github_metadata():
    chunk = RetrievedChunk(
        chunk_id="c1",
        text="def hello():\n    return 'world'",
        metadata={
            "source_id": "src_1",
            "source_type": "github",
            "source_ref": "https://github.com/octocat/hello-world",
            "source_title": "GitHub: octocat/hello-world",
            "file_path": "src/app.py",
            "language": "Python",
            "start_line": 1,
            "end_line": 2,
            "repo_owner": "octocat",
            "repo_name": "hello-world",
            "branch": "main",
        },
        distance=0.1,
        semantic_score=0.9,
        score=0.9,
    )

    context, citations = qa_pipeline.build_context([chunk])

    assert "File: src/app.py (lines 1-2)" in context
    assert "Language: Python" in context
    assert "GitHub: https://github.com/octocat/hello-world/blob/main/src/app.py#L1-L2" in context
    assert citations[0].file_path == "src/app.py"
    assert citations[0].language == "Python"
    assert citations[0].file_url == "https://github.com/octocat/hello-world/blob/main/src/app.py#L1-L2"


def test_build_context_handles_repo_overview_chunk():
    """Test that repository overview chunks are handled specially (no GitHub link, Repository Overview label)"""
    overview_text = """Repository: octocat/hello-world
Branch: main

SUMMARY
======
Detected Languages: Python, Markdown
Files Indexed: 2
Files Skipped: 0
Total Chunks Created: 10

STRUCTURE
======
Top-level Directories: src, tests

IMPORTANT FILES & DIRECTORIES
======
README: ✓ README.md
Main Entry Points: ✓ src/app.py
"""
    
    chunk = RetrievedChunk(
        chunk_id="overview_chunk",
        text=overview_text,
        metadata={
            "source_id": "src_1",
            "source_type": "github",
            "source_ref": "https://github.com/octocat/hello-world",
            "source_title": "GitHub: octocat/hello-world",
            "file_path": "__SAGE_REPO_OVERVIEW__",
            "language": "text",
            "chunk_kind": "source_overview",
            "overview_type": "github",
            "start_line": 1,
            "end_line": 1,
            "repo_owner": "octocat",
            "repo_name": "hello-world",
            "branch": "main",
        },
        distance=0.1,
        semantic_score=0.9,
        score=0.9,
    )

    context, citations = qa_pipeline.build_context([chunk])

    # Verify special handling for overview chunk
    assert "Repository Overview" in context  # Should show as "Repository Overview", not file path
    assert "Source: Repository Overview" in context
    assert "__SAGE_REPO_OVERVIEW__" not in context  # File path should not be exposed
    
    # Should NOT have GitHub link for overview
    assert "GitHub: https://" not in context or "https://github.com/octocat/hello-world/blob/" not in context
    
    # Should include full text, not truncated
    assert "Detected Languages: Python, Markdown" in context
    assert "SUMMARY" in context
    
    # Citation should indicate no file_url (since it's a synthetic chunk)
    assert citations[0].file_path == "__SAGE_REPO_OVERVIEW__"
    assert citations[0].file_url is None  # Should be None for overview chunks


def test_ingest_github_includes_overview_chunk(tmp_path, monkeypatch):
    """Test that ingestion includes the repository overview chunk"""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "README.md").write_text("# Sample\n\nThis is a repo.", encoding="utf-8")
    src_dir = repo_root / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    fake_repo = FakeRepo()
    fake_vectors = FakeVectorStore()

    monkeypatch.setattr(ingestion_pipeline, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(ingestion_pipeline, "SupabaseRepository", lambda: fake_repo)
    monkeypatch.setattr(ingestion_pipeline, "get_embedding_service", lambda: FakeEmbeddingService())
    monkeypatch.setattr(ingestion_pipeline, "get_vector_store", lambda: fake_vectors)
    monkeypatch.setattr(
        ingestion_pipeline,
        "fetch_repository",
        lambda url, branch=None: (str(repo_root), RepoRef(owner="octocat", repo="hello-world", branch=branch, canonical="https://github.com/octocat/hello-world")),
    )

    result = ingestion_pipeline.ingest_github("https://github.com/octocat/hello-world", branch="main")

    # Verify overview chunk is included in the result
    assert result.chunks_count >= 3  # At least 1 overview + 2 files

    # Verify overview chunk is in the vector store
    vector_call = fake_vectors.calls[0]
    chunks = vector_call["chunks"]
    
    # Find the overview chunk (should be first, with special file_path)
    overview_chunks = [c for c in chunks if c.extra_metadata.get("file_path") == "__SAGE_REPO_OVERVIEW__"]
    assert len(overview_chunks) == 1, "Overview chunk should be present"
    
    overview_chunk = overview_chunks[0]
    assert overview_chunk.extra_metadata["chunk_kind"] == "source_overview"
    assert overview_chunk.extra_metadata["overview_type"] == "github"
    assert overview_chunk.extra_metadata["language"] == "text"
    assert overview_chunk.extra_metadata["repo_owner"] == "octocat"
    assert overview_chunk.extra_metadata["repo_name"] == "hello-world"
    
    # Overview chunk text should contain repository metadata
    assert "octocat/hello-world" in overview_chunk.text
    assert "SUMMARY" in overview_chunk.text or "Summary" in overview_chunk.text or "Detected" in overview_chunk.text
