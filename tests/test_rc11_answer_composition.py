"""RC1.1-C: direct, literal, correctly scoped educational excerpts."""

from __future__ import annotations

import re

import pytest

from mri_rag.answer import ask
from mri_rag.generation_guard import assess_generated_answer
from mri_rag.retrieval import search_sparse

DWI = "¿Qué diferencia hay entre DWI y ADC?"


def test_comparison_explains_both_concepts_with_verbatim_sentences():
    result = ask(DWI, llm="none", top_k=3)
    assert result["status"] == "ok"
    assert result["engine_status"] == "extractive"
    assert result["hits"][0]["id"] == "mri_dwi_adc"
    assert len(result["hits"]) == 1
    lines = result["answer"].splitlines()
    assert len(lines) == 2
    assert all(line.startswith("[S1] ") for line in lines)
    assert any("DWI introduce" in line for line in lines)
    assert any("El ADC es" in line for line in lines)
    assert "Qué es la resonancia magnética" not in result["answer"]


def test_cited_answer_is_bound_to_approved_source():
    result = ask(DWI, llm="none", top_k=3)
    hit = search_sparse(DWI, limit=3)[0]
    assert assess_generated_answer(result["answer"], [hit]) == "accepted"
    assert {c["card_id"] for c in result["citations"]} == {"mri_dwi_adc"}
    assert {c["ref"] for c in result["citations"]} == {"S1"}


def test_no_unjustified_extra_documents():
    result = ask(DWI, llm="none", top_k=8)
    assert {h["id"] for h in result["hits"]} == {"mri_dwi_adc"}
    assert len(set(re.findall(r"\[S(\d+)\]", result["answer"]))) == 1


@pytest.mark.parametrize(
    "question, expected",
    [
        ("¿Qué es T1?", "mri_t1"),
        ("¿Para qué sirve FLAIR?", "mri_flair"),
        ("¿Qué significa MR Conditional en un implante?", "mri_implantes"),
    ],
)
def test_excerpts_only_from_one_relevant_card(question, expected):
    result = ask(question, llm="none", top_k=3)
    assert result["status"] == "ok"
    assert len(result["hits"]) == 1
    assert result["hits"][0]["id"] == expected
    assert result["answer"].startswith("[S1] ")
    assert {c["card_id"] for c in result["citations"]} == {expected}


def test_unsupported_calibration_abstains():
    result = ask("¿Cómo se calibra una bobina de RM?", llm="none")
    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []


def test_reversed_comparison_order_is_still_supported():
    result = ask("¿Cuál es la diferencia entre ADC y DWI?", llm="none")
    assert result["status"] == "ok"
    assert "DWI introduce" in result["answer"]
    assert "El ADC es" in result["answer"]


def test_out_of_domain_abstains():
    result = ask("¿Cuál es la capital de Chile?", llm="none")
    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []


def test_patient_specific_question_blocked():
    result = ask("Tengo marcapasos, ¿puedo entrar a RM 3T?", llm="none")
    assert result["status"] == "blocked"
    assert result["citations"] == []
