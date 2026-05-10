from app.services.chunker import TextChunk
from app.services.vector_store import VectorStore


class _FakeCollection:
    def __init__(self):
        self.payload = None

    def upsert(self, **kwargs):
        self.payload = kwargs


class _TestVectorStore(VectorStore):
    def __init__(self):
        self.collection = _FakeCollection()


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

    metadata = store.collection.payload["metadatas"][0]
    assert "branch" not in metadata
    assert "nullable_field" not in metadata
    assert metadata["repo_owner"] == "octocat"
    assert metadata["file_path"] == "src/app.py"
