from eval.run_eval import answer_correct, evidence_found, first_hit_rank, is_refusal


def test_evidence_matching_ignores_case_and_line_breaks():
    assert evidence_found(["four structurally different"], ["It ingests FOUR structurally\ndifferent sources"])
    assert not evidence_found(["ChromaDB"], ["uses Supabase"])


def test_evidence_all_requires_every_item():
    texts = ["SAGE paper text", "Wikipedia text"]
    assert evidence_found(["SAGE", "Wikipedia"], texts, require_all=True)
    assert not evidence_found(["SAGE", "missing"], texts, require_all=True)


def test_first_hit_rank():
    assert first_hit_rank(["target"], ["a", "b target", "target"]) == 2
    assert first_hit_rank(["target"], ["a"]) is None


def test_answer_scoring_handles_refusals():
    answerable = {"category": "factual", "answer_keywords": ["ChromaDB"]}
    unanswerable = {"category": "unanswerable", "answer_keywords": []}
    refusal = "Not available in the provided source."
    assert is_refusal(refusal)
    assert answer_correct(answerable, "SAGE uses ChromaDB [S1].")
    assert not answer_correct(answerable, refusal)
    assert answer_correct(unanswerable, refusal)
    assert not answer_correct(unanswerable, "It is Paris.")
