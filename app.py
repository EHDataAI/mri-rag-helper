"""Interfaz Streamlit académica. Iniciar con: streamlit run app.py"""

from __future__ import annotations

import streamlit as st

from mri_rag.answer import ask
from mri_rag.corpus import load_corpus, verify_manifest

st.set_page_config(page_title="MRI-RAG-HELPER", page_icon="📖", layout="wide")
st.title("MRI-RAG-HELPER")
st.caption("Tutor documental de Resonancia Magnética · laboratorio público · no es software médico")
st.warning(
    "Solo educación. No utilice datos de pacientes ni este sistema para autorizar estudios, implantes o tratamientos."
)

checks = verify_manifest()
if not checks or not all(checks.values()):
    st.error("Integridad del corpus no verificada. Ejecute: mri-rag preflight")
    st.stop()

cards, sources = load_corpus()
with st.sidebar:
    st.header("Configuración de búsqueda")
    mode = st.selectbox(
        "Recuperador",
        ["sparse", "hybrid"],
        help="Híbrido descarga el modelo E5 en el primer uso y requiere dependencias extra.",
    )
    llm = st.selectbox(
        "Formato de respuesta",
        ["none", "ollama"],
        format_func=lambda v: (
            "Extractivo (offline)" if v == "none" else "Generativo (Ollama local)"
        ),
    )
    st.caption("RAG sin servicios comerciales, sin cargas clínicas y sin scraping automático.")
    st.metric("Fichas originales", len(cards))
    st.metric("Referencias", len(sources))

question = st.text_input(
    "Pregunta académica", placeholder="¿En qué se diferencian DWI y ADC?", max_chars=1500
)
if st.button("Consultar evidencias", type="primary"):
    if not question.strip():
        st.info("Escriba una pregunta.")
    else:
        try:
            result = ask(question, mode=mode, llm=llm)
            st.subheader("Respuesta")
            st.write(result["answer"])
            st.caption(result.get("engine_status", result["status"]))
            if result["citations"]:
                st.subheader("Referencias verificables")
                seen = set()
                for citation in result["citations"]:
                    key = (citation["ref"], citation["source_id"])
                    if key not in seen:
                        st.markdown(
                            f"**[{citation['ref']}]** [{citation['title']}]({citation['url']})"
                        )
                        seen.add(key)
            st.caption(result["notice"])
        except (RuntimeError, ImportError, OSError, ValueError) as exc:
            st.error(
                f"El modo solicitado no está disponible: {type(exc).__name__}. "
                "Use modo extractivo o revise dependencias y configuración local."
            )

with st.expander("Catálogo de temas disponibles"):
    for module in sorted({c["module"] for c in cards}):
        st.markdown(
            f"**{module}:** " + ", ".join(c["title"] for c in cards if c["module"] == module)
        )
with st.expander("Alcance y límites"):
    st.write(
        "Las fichas son resúmenes originales revisables. Están marcadas como pendientes "
        "de revisión clínica por pares; el sistema no sustituye manuales oficiales. "
        "La presencia de una cita no demuestra, por sí sola, fidelidad factual de un LLM."
    )
