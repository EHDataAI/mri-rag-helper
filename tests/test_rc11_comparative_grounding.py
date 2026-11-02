"""Scientific regression: lexical co-mentions are not two-term explanations."""

from __future__ import annotations

import pytest

from mri_rag.answer import ask
from mri_rag.generation_guard import assess_generated_answer
from mri_rag.retrieval import search_sparse
from mri_rag.trusted_index import load_trusted_corpus


@pytest.mark.parametrize(
    "question",
    [
        "¿Cuál es la diferencia entre T1 y T2?",
        "¿Cuál es la diferencia entre T2 y T1?",
    ],
)
def test_independent_t1_t2_definitions_are_cited(question, corpus_root):
    result = ask(question, mode="sparse", llm="none", top_k=3)
    assert result["status"] == "ok"
    assert {hit["id"] for hit in result["hits"]} == {"mri_t1", "mri_t2"}
    assert {cite["card_id"] for cite in result["citations"]} == {"mri_t1", "mri_t2"}
    assert {cite["ref"] for cite in result["citations"]} == {"S1", "S2"}
    assert "T1 describe el proceso de recuperación" in result["answer"]
    assert "T2 se relaciona con la pérdida de coherencia" in result["answer"]
    assert "Ajustar TR y TE modifica" not in result["answer"]
    # ask() exposes only public hit metadata; the provenance validator needs
    # the original, integrity-checked source text in the same citation order.
    assert all("text" not in hit for hit in result["hits"])
    cards, _ = load_trusted_corpus(corpus_root)
    approved_by_id = {card["id"]: card for card in cards}
    full_hits = [approved_by_id[hit["id"]] for hit in result["hits"]]
    assert assess_generated_answer(result["answer"], full_hits) == "accepted"


def test_dwi_adc_single_card_comparison_remains_valid():
    question = "¿Qué diferencia hay entre DWI y ADC?"
    result = ask(question, mode="sparse", llm="none", top_k=3)
    assert result["status"] == "ok"
    assert [hit["id"] for hit in result["hits"]] == ["mri_dwi_adc"]
    assert "DWI introduce" in result["answer"]
    assert "El ADC es" in result["answer"]
    assert (
        assess_generated_answer(result["answer"], search_sparse(question, limit=3)[:1])
        == "accepted"
    )


def test_missing_comparison_evidence_abstains():
    result = ask("¿Qué diferencia hay entre T1 y 4D Flow?", llm="none")
    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []
