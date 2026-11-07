# MRI RAG HELPER

> Laboratorio RAG local en español sobre Resonancia Magnética, para estudiantes de salud. **Prototipo de investigación y portafolio: no dispositivo médico, no consejo clínico.**

## Propósito y límites

Responde preguntas académicas con fichas originales y enlaces a instituciones como NIH/NIBIB, FDA, NLM/MedlinePlus y ACR (manual 2026). No ingiere ni redistribuye manuales ACR ni recursos RSNA/OpenStax con restricciones. Las 20 fichas **siguen pendientes de revisión clínica por pares**. No introducir datos reales ni datos sensibles.

## Características MVP

- 20 fichas educativas originales, 15 referencias de autoridad en un catálogo con derechos y fechas.
- Retrieval baseline local: SQLite FTS5, sin claves, credenciales ni GPU.
- Opción RAG híbrido: recuperación léxica + embeddings `intfloat/multilingual-e5-small` (licencia MIT) + RRF.
- Opción generación Ollama local con `qwen3:1.7b` (licencia Apache-2.0); citas comprobadas *sintácticamente*, no semánticamente.
- Abstención por falta de coincidencias y bloqueo básico de consultas paciente-específicas.
- Benchmarks Hit@k, MRR@k y tasa de abstención fuera de dominio (OOD), con partición dev/test.
- QA: pytest, Ruff, preflight SHA-256, CI sin conexiones de negocio.

## Requisitos

Python >=3.11; recomendado Python 3.12. Windows PowerShell 5.1/7 o Ubuntu WSL. No se requiere Docker. Las opciones semánticas y de LLM requieren descargas/modelos adicionales.

### Inicio rápido (WSL o Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[ui,dev]"
mri-rag preflight
mri-rag build
mri-rag ask "¿Qué diferencia existe entre DWI y ADC?"
streamlit run app.py --server.address 127.0.0.1
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui,dev]"
.\.venv\Scripts\mri-rag.exe preflight
.\.venv\Scripts\mri-rag.exe build
.\.venv\Scripts\mri-rag.exe ask "¿Qué significa MR Conditional?"
.\.venv\Scripts\streamlit.exe run app.py --server.address 127.0.0.1
```

### Híbrido local y LLM (opcionales)

```bash
python -m pip install -e ".[dense]"
mri-rag ask "¿Qué relación existe entre el ADC y la difusión?" --mode hybrid
# Ollama instalado aparte: ollama pull qwen3:1.7b
mri-rag ask "¿Qué es una secuencia FLAIR?" --llm ollama
```

El primer uso de embeddings descarga el modelo de Hugging Face: requiere Internet y suficiente RAM/almacenamiento. Ollama debe estar disponible en `http://127.0.0.1:11434`. Nunca abrir el servidor fuera de loopback sin revisión de seguridad, autenticación y privacidad. Si Ollama falla, la salida vuelve al modo extractivo y lo informa.

## QA y evaluación

```bash
python -m ruff check --fix src tests app.py scripts
python -m ruff format src tests app.py scripts
python -m compileall -q src tests app.py
python -m ruff check src tests app.py scripts
python -m ruff format --check src tests app.py scripts
python -m pytest -q --junitxml=reports-junit.xml
mri-rag eval --split dev --k 3
mri-rag eval --split test --k 3
```

`hit@3` no significa respuesta correcta. Las preguntas de benchmark son pequeñas, creadas por el laboratorio y no constituyen validación externa.

## Seguridad y reproducibilidad

- Lista de dominios HTTPS para referencias; ningún servidor web externo consultado al hacer preguntas.
- Corpus de autores con SHA-256 y sin materiales de terceros copiados.
- No PHI, no datos clínicos, no imágenes médicas reales, no ingestión arbitraria de archivos o URLs.
- Ollama con validación loopback. El sistema no autoriza estudios con implantes ni determina dosis de contraste.
- Seguridad y licenciamiento documentados en `docs/`.
- Código libre MIT; fichas originales CC BY 4.0. Las referencias mantienen derechos propios.

## Roadmap propuesto

1. **Lab00:** fuentes, licencias, esquema, amenazas y corpus revisado (MVP preliminar en este ZIP).
2. **Lab01:** FTS5, benchmark dev/test, control de integridad y reproducibilidad.
3. **Lab02:** E5 híbrido, RRF, búsqueda cruzada en español, reranking; evaluaciones ciegas y sensibilidad.
4. **Lab03:** generación con Ollama y verificación *claim-level* por evidencia, tutor con preguntas y feedback.
5. **Lab04:** revisión clínica formal, pruebas adversariales, UX y accesibilidad; solo entonces despliegue público controlado.

## Documentación

- [Arquitectura](docs/ARCHITECTURE.md)
- [Derechos y fuentes](docs/SOURCES_AND_LICENSES.md)
- [ADR](docs/ADR-0001-LOCAL-FIRST.md)
- [Plan ERL v2](docs/ERL_V2_PLAN.md)

**Aviso:** los modelos y sus pesos no se distribuyen. Una cita bibliográfica no representa aprobación institucional ni una garantía de que el texto generado sea correcto.

**Estado de release:** el ZIP inicial es `RC0`, con QA parcial y sin autorización de publicación clínica. Ejecutar los gates restantes antes de cualquier push público.
- [Modelo de amenazas](docs/THREAT_MODEL.md)
- [Decisiones de stack](docs/TECH_STACK_DECISIONS.md)
- [Informe QA RC0](docs/QA_REPORT.md)

## Demostración pública RC1 (Streamlit Community Cloud)

La demostración pública usa `streamlit_public.py`, Python 3.12, recuperación
SQLite FTS5 y **respuestas extractivas únicamente**. No instala ni activa Ollama,
embeddings E5, modelos externos o claves de API.

1. Publicar el código tras pasar los controles de QA y revisar secretos.
2. Crear la aplicación en Streamlit Community Cloud desde el repositorio GitHub.
3. Seleccionar rama `main`, archivo principal `streamlit_public.py` y Python 3.12.
4. Comprobar reconstrucción de FTS5, consulta educativa y referencias en navegador.

El archivo `requirements.txt` instala el paquete local y usa
`constraints-cloud.txt` para fijar las 35 dependencias resueltas de una
instalación de referencia Python 3.12/Linux. Estos pins **no son un lockfile
con hashes ni sustituyen** los controles periódicos de seguridad.

Limitaciones: demo académica, 20 fichas originales, 15 referencias y preguntas
de benchmark reducidas; contenido pendiente de revisión clínica por pares.
No cargar información de pacientes ni usarlo para decisiones clínicas.
La base SQLite se reconstruye durante el arranque y el almacenamiento local
de Streamlit Community Cloud puede ser efímero.

## Estado RC1.1 - Relevancia y fundamentación (2026-10-26)

RC1.1 incorpora recuperación léxica más selectiva, composición extractiva
de respuestas y comparaciones T1/T2 sustentadas en dos fichas independientes.

Validaciones locales: 130 pruebas Pytest/JUnit aprobadas; auditoría
funcional de 11 consultas aprobada; corpus de 20 fichas y 14 fuentes
verificado. Las evaluaciones DEV y TEST mantienen Hit@3 = 1.0;
MRR@3 = 0.9583 (DEV) y 1.0 (TEST); abstención OOD TEST = 1.0.

Ruff, Bandit y los análisis de Gitleaks del historial Git y de una
copia del árbol de trabajo finalizaron correctamente, con cero
hallazgos de secretos. pip-audit no encontró vulnerabilidades conocidas
en dependencias auditables; el paquete local no fue auditado mediante PyPI.

La revisión clínica independiente y la validación con preguntas
externas siguen pendientes. Estas pruebas no acreditan seguridad
clínica, generalización ni exactitud médica independiente.

RC1.1 continúa en preparación de release. La demostración pública
basada en main permanece en RC1 hasta aprobar el pull request y
su despliegue.

## RC1.1-N4 - Identidad y accesibilidad visual (candidato)

La identidad visible pasa a **MRI-RAG-HELPER**, con interfaz **dark-first** de baja luminosidad, variante clara opcional y referencias agrupadas por evidencia S1/S2. El motor RAG, el paquete `mri_rag` y la CLI `mri-rag` no se renombran. La demostración no está validada para decisiones clínicas.

La licencia conserva las atribuciones históricas de MRI-RAG Academy Lab. El repositorio público ya utiliza el nombre `EHDataAI/mri-rag-helper`. La integración de RC1.1 en `main` y su despliegue continúan sujetos a los quality gates y a la revisión correspondiente.


## RC1.1 - Actualización de integración (2026-11-07)

El estado actual del corpus es de 20 fichas educativas originales y
15 referencias registradas. Las cifras de 14 fuentes y 130 pruebas
indicadas en el historial de RC1.1 corresponden a etapas anteriores.

La última validación local comunicada para esta iteración registró
207 pruebas aprobadas. El commit de endurecimiento de grounding y
seguridad fue firmado y verificado por GitHub. Antes de esta
actualización documental, el PR #1 mostraba dos controles `quality`
aprobados; los controles deberán ejecutarse nuevamente cuando se
publique el próximo commit.

La aplicación es una demostración educativa. Las fichas permanecen
pendientes de revisión clínica externa por pares. No utilizar datos
de pacientes ni emplear las respuestas para decisiones clínicas.
