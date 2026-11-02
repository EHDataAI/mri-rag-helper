"""RC1.1-A acceptance criteria: real answer relevance, not just Hit@3.

The first three are intentionally RED on RC1. Keep evidence separate from repo.
"""

from __future__ import annotations

import pytest

from mri_rag.answer import ask
from mri_rag.retrieval import search_sparse
from mri_rag.security import screen_question

DWI_QUESTION = "¿Qué diferencia hay entre DWI y ADC?"


def test_dwi_adc_retrieval_excludes_generic_intro():
    ids = [hit["id"] for hit in search_sparse(DWI_QUESTION, limit=3)]
    assert "mri_dwi_adc" in ids
    assert "mri_fundamentos" not in ids


def test_dwi_adc_answer_excludes_generic_intro():
    answer = ask(DWI_QUESTION, mode="sparse", llm="none", top_k=3)
    assert answer["status"] == "ok"
    assert answer["engine_status"] == "extractive"
    assert "[S1]" in answer["answer"]
    assert "mri_fundamentos" not in [h["id"] for h in answer["hits"]]
    assert "Qué es la resonancia magnética:" not in answer["answer"]


def test_unsupported_coil_calibration_abstains():
    answer = ask("¿Cómo se calibra una bobina de RM?", mode="sparse", llm="none")
    assert answer["status"] == "insufficient_evidence"
    assert answer["citations"] == []


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("¿Qué es T1?", "mri_t1"),
        ("¿Qué significa T2 en resonancia?", "mri_t2"),
        ("¿Para qué sirve la secuencia FLAIR?", "mri_flair"),
        ("¿Qué es B0?", "mri_campo_b0"),
        ("¿Qué es el tiempo de repetición TR y el tiempo de eco TE?", "mri_tr_te"),
        ("¿Qué significa MR Conditional en un implante?", "mri_implantes"),
    ],
)
def test_existing_educational_questions_keep_relevant_document(question, expected):
    assert expected in [h["id"] for h in search_sparse(question, limit=3)]


def test_patient_specific_question_remains_blocked():
    allowed, _ = screen_question("Tengo marcapasos, ¿puedo entrar al resonador 3T?")
    assert not allowed


def test_out_of_domain_question_still_abstains():
    answer = ask("¿Cuál es la capital de Chile?", mode="sparse", llm="none")
    assert answer["status"] == "insufficient_evidence"
    assert answer["citations"] == []
