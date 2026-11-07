# MRI-RAG Academy · ERL v2 · QA de construcción RC0

**Fecha de ejecución:** 2026-10-20. **Entorno verificado:** Linux, Python 3.13.5, pytest 9.0.2.

| Gate | Resultado | Evidencia |
|---|---|---|
| Carga y metadatos corpus | PASS | 20 fichas; 14 referencias; IDs y dominio HTTPS controlados |
| SHA-256 corpus | PASS | cards.jsonl y sources.json coinciden con manifest.json |
| SQLite FTS5 build | PASS | Índice de 20 fichas creado en local_data (no empaquetado) |
| QA pytest | PASS | 31/31 tests (tiempo <1 s), incluye seguridad básica y regresión |
| compileall Python | PASS | src, tests, app, scripts |
| CLI respuesta DWI/ADC | PASS | Consulta respondida con fichas/citas en modo extractivo |
| Evaluación test (8 respondibles, 3 OOD) | PASS TÉCNICO / NO VALIDACIÓN | Hit@3=1.0, MRR@3=1.0, abstención OOD=1.0 |
| Ruff y Ruff format | NOT_RUN | Ruff no instalado en entorno aislado; instalación sin red falló |
| Bandit / pip-audit / Gitleaks | NOT_RUN | Herramientas no disponibles |
| UI Streamlit | NOT_RUN | Streamlit no instalado; UI requiere verificación manual/WCAG |
| Embeddings E5 / modelo Ollama | NOT_RUN | Modelos y dependencias no descargados |
| Revisión clínica independiente | NOT_RUN | Fichas requieren revisión humana por TM RM + físico médico/docente |
| Auditoría externa y pen test aislado | NOT_RUN | Pendiente posterior a preparación del entorno |

## Interpretación correcta

El test fue escrito con vocabulario muy cercano al corpus original. Los tres ejemplos OOD son claramente ajenos a la RM. **Los valores 1.0 no demuestran generalización, calibración, fidelidad generativa, robustez ni seguridad del sistema.** Requiere un set congelado independiente, preguntas parafraseadas, casos adversariales, distractores, negativa a recomendaciones clínicas y peer review.

## Decisión de release

**RC0 = APTO PARA REVISIÓN LOCAL; BLOCK para despliegue público o uso educativo institucional hasta cerrar gates.**

## RC1.1 - Auditoría de relevancia y respuestas (2026-10-26)

Este apartado complementa el informe histórico RC0 anterior; no
modifica sus resultados originales.

| Gate local | Resultado | Alcance |
|---|---|---|
| RC1.1-D1 | PASS | 130 pruebas JUnit; Ruff; integridad del corpus |
| RC1.1-D2 | PASS | 11 consultas funcionales y control de citas |
| RC1.1-D3 | PASS | Bandit; pip-audit; Gitleaks con cero hallazgos |
| RC1.1-E0 | PASS | Evaluaciones de recuperación compatibles con CI |
| RC1.1-E1 | PASS | 41 archivos propuestos; SHA-256 reconciliados |

Indicadores de recuperación:
- DEV: 12 casos; Hit@3 = 1.0; MRR@3 = 0.9583.
- TEST: 11 casos; Hit@3 = 1.0; MRR@3 = 1.0;
  abstención fuera de dominio = 1.0.
- Corpus: 20 fichas educativas y 14 fuentes referenciadas.

Limitaciones y pendientes:
- El conjunto de evaluación es reducido y no constituye validación externa.
- La correspondencia literal de citas no garantiza corrección clínica.
- La revisión independiente por profesionales de RM y física médica sigue pendiente.
- pip-audit excluyó el paquete local no publicado en PyPI.
- Gitleaks sin hallazgos no demuestra ausencia absoluta de secretos.
- El resultado remoto de GitHub Actions para RC1.1 todavía no existe.
- No se ha autorizado el merge ni el despliegue público de RC1.1.

Estado: controles locales aprobados dentro del alcance descrito;
publicación RC1.1 pendiente.

## RC1.1-N4 - Candidato de accesibilidad visual

Se propone el nombre MRI-RAG-HELPER, temas claro/oscuro nativos, modo oscuro inicial de baja luminosidad y agrupación visual de citas por ficha. Los controles automatizados del candidato RC17-B2-R5 aprobaron 189 pruebas, Ruff y Bandit (sin hallazgos ni advertencias). La inspección manual de accesibilidad visual, navegación por teclado, contraste y temas claro/oscuro continúa pendiente. La auditoría clínica externa y la publicación también permanecen pendientes.


## Evidencia complementaria RC1.1 - B5-B9 (2026-11-07)

- Commit de referencia: `1f4a748ac40a1c0a7179e6c858d1d7f6e8661548`.
- Firma SSH: verificada por GitHub (`verified: true`, `reason: valid`).
- Suite local comunicada para la iteración: 207 pruebas aprobadas.
- Corpus registrado: 20 fichas educativas y 15 referencias.
- PR #1: dos controles `quality` aprobados antes del ajuste documental.
- La revisión clínica por pares y la inspección manual integral de
  accesibilidad continúan pendientes.

Esta sección es complementaria y no modifica los resultados
históricos de las etapas RC0 y RC1.1 anteriores. El nuevo commit
documental requerirá una ejecución independiente de los controles CI.
