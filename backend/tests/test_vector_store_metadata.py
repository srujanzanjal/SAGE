from app.services.chunker import TextChunk
from app.services.vector_store import VectorStore


class _FakeTable:
    def __init__(self):
        self.rows = None

    def upsert(self, rows, **kwargs):
        self.rows = rows
        return self

    def execute(self):
        return self


class _FakeDB:
    def __init__(self):
        self.table_obj = _FakeTable()

    def table(self, _name):
        return self.table_obj


class _TestVectorStore(VectorStore):
    def __init__(self):
        self.db = _FakeDB()


def test_upsert_chunks_drops_none_metadata_values():
    store = _TestVectorStore()

    chunks = [
        TextChunk(
            index=0,
            text="sample",
            token_estimate=2,
            extra_metadata={
                "repo_owner": "octocat",
                "repo_name": "hello-world",
                "branch": None,
                "file_path": "src/app.py",
                "start_line": 1,
                "end_line": 10,
                "nullable_field": None,
            },
        )
    ]

    store.upsert_chunks(
        knowledgebase_id="kb_1",
        source_id="src_1",
        source_type="github",
        source_ref="https://github.com/octocat/hello-world",
        chunks=chunks,
        embeddings=[[0.1, 0.2, 0.3]],
        chunk_ids=["chunk_1"],
    )

    row = store.db.table_obj.rows[0]
    metadata = row["metadata"]
    assert "branch" not in metadata
    assert "nullable_field" not in metadata
    assert metadata["repo_owner"] == "octocat"
    assert metadata["file_path"] == "src/app.py"
    # Embedding is serialised as a pgvector text literal.
    assert row["embedding"] == "[0.1,0.2,0.3]"
