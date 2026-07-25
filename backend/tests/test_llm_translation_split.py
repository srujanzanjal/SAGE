from app.services.llm import _hard_slice, _split_for_translation


def test_split_for_translation_respects_paragraph_boundaries():
    text = "First paragraph." + "\n\n" + "Second paragraph." + "\n\n" + "Third paragraph."
    segments = _split_for_translation(text, max_chars=1000)
    assert segments == [text]  # small enough to fit in one segment


def test_split_for_translation_splits_oversized_paragraph_groups():
    paragraphs = [f"Paragraph number {i} with some extra padding text to add length." for i in range(20)]
    text = "\n\n".join(paragraphs)
    segments = _split_for_translation(text, max_chars=200)
    assert len(segments) > 1
    assert all(len(segment) <= 200 for segment in segments)


def test_split_for_translation_hard_slices_a_single_giant_paragraph():
    # Regression test: website text extracted with no blank-line breaks at
    # all (a real, observed case) must still be split into safe-sized pieces
    # instead of becoming one oversized segment that blows a provider's
    # tokens-per-minute budget in a single request.
    giant_paragraph = " ".join(f"word{i}" for i in range(5000))
    assert "\n\n" not in giant_paragraph
    segments = _split_for_translation(giant_paragraph, max_chars=3000)
    assert len(segments) > 1
    assert all(len(segment) <= 3000 for segment in segments)
    # No word content lost in the split.
    assert " ".join(segments).split() == giant_paragraph.split()


def test_hard_slice_returns_input_unchanged_when_already_small():
    assert _hard_slice("short text", max_chars=3000) == ["short text"]


def test_hard_slice_never_exceeds_max_chars():
    text = " ".join(f"tok{i}" for i in range(2000))
    pieces = _hard_slice(text, max_chars=500)
    assert all(len(piece) <= 500 for piece in pieces)
    assert " ".join(pieces).split() == text.split()
