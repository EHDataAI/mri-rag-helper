"""MRI-RAG Academy public demo: trusted FTS5 and extractive answers only."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from mri_rag.answer import ask
from mri_rag.corpus import load_corpus, verify_manifest

st.set_page_config(page_title="MRI-RAG-HELPER | Demo", layout="wide")
st.html(Path(__file__).resolve().parent / "assets/mri_helper.css")
with st.container(border=True, key="mri_helper_hero"):
    st.title("MRI-RAG-HELPER")
    st.caption("Asistente educativo de resonancia magnética basado en evidencias.")
st.warning(
    "Contenido pendiente de revisión clínica por pares. "
    "No introduzca datos de pacientes. No utilizar para decisiones diagnósticas, "
    "implantes, contrastes ni tratamientos."
)

checks = verify_manifest()
if not checks or not all(checks.values()):
    st.error("El corpus no superó la verificación de integridad.")
    st.stop()

cards, sources = load_corpus()
with st.sidebar:
    st.header("Modo público")
    st.caption("Recuperación SQLite FTS5; respuestas extractivas.")
    st.metric("Fichas educativas", len(cards))
    st.metric("Fuentes", len(sources))

question = st.text_input(
    "Pregunta académica",
    placeholder="¿Qué diferencia existe entre DWI y ADC?",
    max_chars=1500,
)
if st.button("Consultar evidencias", type="primary"):
    if not question.strip():
        st.info("Escriba una pregunta académica.")
    else:
        try:
            result = ask(question, mode="sparse", llm="none", top_k=3)
            with st.container(border=True, key="mri_helper_result"):
                st.subheader("Respuesta documental")
                st.write(result["answer"])
                engine = result.get("engine_status", result["status"])
                st.caption("Respuesta extractiva" if engine == "extractive" else engine)
                if result.get("citations"):
                    st.subheader("Referencias")
                    grouped: dict[str, list[dict]] = {}
                    seen = set()
                    for citation in result["citations"]:
                        key = (citation["ref"], citation["source_id"])
                        if key not in seen:
                            grouped.setdefault(citation["ref"], []).append(citation)
                            seen.add(key)
                    for ref, citations in grouped.items():
                        st.markdown(f"**Evidencia [{ref}]**")
                        for citation in citations:
                            st.markdown(f"[{citation['title']}]({citation['url']})")
                st.caption(result["notice"])
        except (RuntimeError, ImportError, OSError, ValueError):
            st.error("La consulta no está disponible. Revise el estado del servicio.")

with st.expander("Temas disponibles"):
    for module in sorted({card["module"] for card in cards}):
        titles = ", ".join(card["title"] for card in cards if card["module"] == module)
        st.markdown(f"**{module}:** {titles}")

with st.expander("Alcance y limitaciones"):
    st.write(
        "Las fichas son resúmenes originales pendientes de revisión por pares. "
        "Las citas no suponen validación clínica ni respaldo institucional."
    )
