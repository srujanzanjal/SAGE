from app.services.chunker import chunk_pages, chunk_text


def test_chunk_text_creates_ordered_chunks():
    text = "This is sentence one. This is sentence two. " * 80
    chunks = chunk_text(text, chunk_size_chars=250, overlap_chars=40)
    assert len(chunks) > 1
    assert chunks[0].index == 0
    assert chunks[-1].index == len(chunks) - 1
    assert all(chunk.text for chunk in chunks)


def test_chunk_pages_preserves_page_numbers():
    pages = [(1, "Page one content. " * 30), (2, "Page two content. " * 30)]
    chunks = chunk_pages(pages, chunk_size_chars=220, overlap_chars=20)
    assert {chunk.page_number for chunk in chunks} == {1, 2}
