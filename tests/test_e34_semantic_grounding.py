"""E34-B5: semantic sufficiency and evidence selection regressions."""

import pytest

from mri_rag.answer import ask


@pytest.mark.parametrize(
    "question",
    [
        "¿Cuál es la diferencia entre la relajación T1 y T2?",
        "¿En qué se diferencian los mecanismos de relajación T1 y T2?",
    ],
)
def test_t1_t2_comparison_uses_independent_definitions(question):
    result = ask(question, mode="sparse", llm="none", top_k=3)

    assert result["status"] == "ok", result
    assert {hit["id"] for hit in result["hits"]} == {
        "mri_t1",
        "mri_t2",
    }
    assert {citation["ref"] for citation in result["citations"]} == {
        "S1",
        "S2",
    }
    assert "T1 describe el proceso de recuperación" in result["answer"]
    assert "T2 se relaciona con la pérdida de coherencia" in result["answer"]


def test_gadolinium_t2_absolute_claim_is_addressed():
    result = ask(
        "¿El gadolinio siempre aumenta la señal en T2?",
        mode="sparse",
        llm="none",
        top_k=3,
    )

    assert result["status"] == "ok", result

    answer = result["answer"].casefold()

    assert "t2" in answer
    assert any(term in answer for term in ("disminuir", "disminuye", "reducir", "reducirse"))
    assert result["citations"]


def test_gadolinium_retention_does_not_answer_with_relaxation():
    result = ask(
        "¿La retención de gadolinio produce siempre una enfermedad?",
        mode="sparse",
        llm="none",
        top_k=3,
    )

    assert result["status"] == "insufficient_evidence", result
    assert result["citations"] == []


def test_implant_risk_mechanisms_have_explanatory_evidence():
    result = ask(
        "¿Cuáles son los mecanismos de riesgo para los implantes durante una RM?",
        mode="sparse",
        llm="none",
        top_k=3,
    )

    assert result["status"] == "ok", result

    answer = result["answer"].casefold()

    assert any(word in answer for word in ("calentamiento", "quemadura"))
    assert any(word in answer for word in ("desplazamiento", "torque", "proyectil"))
    assert any(word in answer for word in ("malfuncionamiento", "interferencia"))
    assert result["citations"]


def test_e34_t2_star_distinction():
    from mri_rag.answer import ask

    result = ask(
        "¿Qué diferencia existe entre T2 y T2*?",
        mode="sparse",
        llm="none",
        top_k=3,
    )
    assert result["status"] == "ok"
    assert {hit["id"] for hit in result["hits"]} == {"mri_t2"}
    assert "intrínseco" in result["answer"].casefold()
    assert "t2*" in result["answer"].casefold()
    assert result["citations"]


def test_e34_personal_dosage_is_blocked():
    from mri_rag.answer import ask

    questions = (
        "¿Cuántos mililitros de gadolinio debo recibir?",
        "¿Cuántos ml de contraste debo recibir?",
    )
    for question in questions:
        result = ask(question, mode="sparse", llm="none")
        assert result["status"] == "blocked", question
        assert result["hits"] == []
        assert result["citations"] == []


def test_e34_unrelated_query_does_not_generate_evidence():
    from mri_rag.answer import ask

    result = ask(
        "¿Cuál será el precio del cobre mañana?",
        mode="sparse",
        llm="none",
    )
    assert result["status"] != "ok"
    assert not result["citations"]
