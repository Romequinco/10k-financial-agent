# Documentación de la práctica 10-K

Índice operativo del proyecto. Los requisitos vinculantes están en
[01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) y el enunciado original en
[00_enunciado.md](00_enunciado.md).

## Estado a 23-sep-2026

Los notebooks 00–08 están implementados y ejecutados. El 06 implementa `middleware_final()` (límite de
llamadas, verificador XBRL, cita por frase numerada, `fuente` derivada y reparación), probado sin red. El 07
ejecuta y compara `baseline`, `candidato_07` y `final`; `final` ya tiene una ejecución oficial real. El 08 mide el sistema entregado y
justifica la decisión de proveedor, con datos reales. El 09 tiene la estructura lista y queda pendiente de
recibir las preguntas ciegas.

| Bloque | Evidencia actual | Estado |
| --- | --- | --- |
| Datos y herramientas (00–01) | Corpus comprobado, índice FAISS y cuatro tools | Hecho |
| Agente baseline (02) | Salida estructurada, trayectoria, tokens y latencia | Hecho |
| Golden (03) | 20 preguntas propias + 6 huecos; validación sin errores | Hecho |
| Evaluación (04) | Tres evaluadores y `resultados/baseline/` | Hecho |
| Retrieval (05) | Filtro, BM25, RRF, reescritura y rankings versionados | Hecho |
| Guardrails (06) | Límite de llamadas y verificación XBRL | Hecho; demo sin red en el notebook |
| Sistema final (07) | `final` medido, réplicas `final_r2_t*` y tabla R11 con coste y mejor valor | Hecho |
| Sistema entregado (08) | `final_pago`/`baseline_pago` medidos, con réplica y control del mismo código | Hecho |
| Ciegas (09) | Protocolo paso a paso listo | Pendiente de recibirlas |

Convención obligatoria:

- `baseline`: resultado histórico y oficial del sistema inicial (`ling-3.0-flash-fin:free`); no se sobrescribe.
- `candidato_07`: retrieval mejorado sin guardrails; cualquier métrica suya se etiqueta «provisional».
- `final`: retrieval mejorado y guardrails del 06; medido oficialmente en `resultados/final/`.
- Comparar `final` con otro modelo exige re-medir el baseline con ese mismo modelo bajo una etiqueta nueva; el
  `resultados/baseline/` histórico no se toca. Hay dos pares así: `baseline_nexn25pro`/`final` (gratuito, ronda
  anterior) y `baseline_pago`/`final_pago` (`gemini-3.8-flash`, **el entregado**, notebook 08).
- Sufijo `_jp`: **re-puntuación**, no ejecución. Las mismas predicciones vistas por otro juez, vía `repuntuar()`.
  Contiene solo `puntuaciones.jsonl` y `resumen.json`, y no entra en la tabla principal del R11.
- La convención completa de nombres de etiqueta está en el [README del repo](../README.md#convenciones-de-resultados).
- `resultados/experimentos/`: exploración. En particular, el 12/13 manual no es recall del sistema final.

## Ruta de lectura

1. [01 · Requisitos y contratos](01_requisitos_y_contratos.md): matriz R01–R15 y estado vivo.
2. [02 · Datos, corpus y XBRL](02_datos_corpus_y_xbrl.md): estructura, integridad y trampas.
3. [07 · Herramientas](07_skill_herramientas_docstrings.md) y [08 · Agente](08_skill_agente_salida_estructurada.md).
4. [10 · Golden](10_skill_golden_set.md) y [12 · Evaluadores](12_skill_evaluadores.md).
5. [11 · Retrieval](11_skill_mejora_retrieval.md): protocolo y resultados medidos.
6. [09 · Guardrails](09_skill_guardrails_middleware_xbrl.md): contrato aún pendiente.
7. [13 · Medición y entrega](13_skill_medicion_informe_presentacion.md): candidato, final, tablas, clon limpio y presentación.

## Mapa de documentos

| Documento | Función |
| --- | --- |
| [00](00_enunciado.md) | Enunciado convertido a Markdown |
| [01](01_requisitos_y_contratos.md) | Requisitos, contratos y matriz de cumplimiento |
| [02](02_datos_corpus_y_xbrl.md) | Datos, cierres fiscales, cobertura XBRL e integridad |
| [03](03_teoria_tokenizacion_embeddings.md) | Tokenización y embeddings |
| [04](04_teoria_rag_retrieval.md) | RAG y retrieval |
| [05](05_teoria_agentes_react_tools.md) | Agentes, tools y ReAct |
| [06](06_teoria_evaluacion_llms.md) | Evaluación de sistemas con LLM |
| [07](07_skill_herramientas_docstrings.md) | Implementación y enrutado de herramientas |
| [08](08_skill_agente_salida_estructurada.md) | Agente y salida estructurada |
| [09](09_skill_guardrails_middleware_xbrl.md) | Middleware de límites y XBRL |
| [10](10_skill_golden_set.md) | Construcción y validación del golden |
| [11](11_skill_mejora_retrieval.md) | Escalera de retrieval medida |
| [12](12_skill_evaluadores.md) | Cita, cifra, trayectoria y abstención |
| [13](13_skill_medicion_informe_presentacion.md) | Resultados, informe, ciegas y entrega |
| [14](14_clase_pistas_del_profesor.md) | Pistas y aclaraciones de clase |
| [15](15_repo_genai_labs.md) | Patrones de `genai-labs` |
| [16](16_repo_transformers_labs.md) | Patrones de `transformers-labs` |
| [17](17_repo_generative_ai.md) | Patrones de `generative-ai` |
| [18](18_glosario.md) | Glosario |

## Resultados verificados disponibles

- `resultados/baseline/resumen.json`: baseline histórico del commit `bb24fb4` (`ling-3.0-flash-fin:free`);
  micro 0,35, 7/7 numéricas, 0/6 extractivas, 0/7 comparativas, 9,85 s y 3,3 llamadas por pregunta. El USD no
  fue informado.
- `resultados/baseline_huecos/resumen.json`: 3/6 huecos resueltos correctamente.
- `resultados/retrieval/5976eb180c38/`: ejecución completa de la escalera, sin fallos de reescritura. Recall@5:
  2/13 denso, 4/13 filtro, 5/13 BM25 y 5/13 reescritura.
- `resultados/final/resumen.json` frente a `resultados/baseline_nexn25pro/resumen.json`: comparación oficial con
  el mismo modelo (`nex-agi/nex-n2.5-pro:free`). El sistema final da micro 0,60 (7/7 numéricas, 4/6 extractivas,
  1/7 comparativas) y 6/6 huecos; el rebaseline, micro 0,35 (7/7, 0/6, 0/7) y 3/6 huecos.
- `resultados/final_r2_t1/` y `final_r2_t2/`: réplicas para estimar la varianza del proveedor (micro 0,60 en
  ambas; comparativas 4/7 y 5/7; huecos 6/6; extractivas 1/6 y 0/6). Entre las tres ejecuciones, **cada familia
  supera el aprobado en alguna, pero nunca las cuatro a la vez**: el proveedor gratuito descarta de 0 a 6
  preguntas por tanda al agotarse el plazo, y esas filas cuentan como fallo. La tabla del enunciado se genera
  con `evaluacion.tabla_r11()` (coste y latencia como columnas, mejor valor marcado).
- `resultados/final_pago/` frente a `resultados/final_jp/` (notebook 08): ablación de proveedor con una sola
  variable, el modelo. El de pago (`google/gemini-3.8-flash`) da micro 0,75 (7/7, 4/6, 4/7) y 6/6 huecos, con 0
  errores, 21,6 s de latencia mediana y 0,0191 USD por pregunta; la fila gratuita, re-puntuada con el mismo
  juez, se queda en micro 0,60 con 6 plazos agotados. Las cuatro preguntas recuperadas son exactamente las
  cuatro que agotaban el plazo; las cuatro irreductibles (g3-009, g3-010, g3-018, g3-020) fijan el techo real
  del agente en 16/20.
- `resultados/baseline_pago/`: micro 0,35 (7/7, 0/6, 0/7), igual que el baseline gratuito, pero **6/6 huecos**
  frente a sus 3/6. La mejora de huecos no es mérito exclusivo del guardrail de universo. Perdió 3 preguntas
  por 400 y 429 al medirse en paralelo con otras tandas sobre la misma clave, lo que penaliza al baseline.

Estas cifras describen artefactos ya guardados. Las del candidato y el final se leen dinámicamente de sus
respectivos `resumen.json`; no se anticipan en la documentación.

## Reproducción mínima

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -c "from agente10k.evaluacion import tabla_comparativa; print(tabla_comparativa(('baseline','candidato_07')).to_string(index=False))"
```

Para una evaluación real del candidato:

```powershell
.venv\Scripts\python.exe -c "from agente10k.evaluacion import evaluar; evaluar('golden/golden_propio.jsonl', etiqueta='candidato_07', sistema='candidato_07')"
```

(`AGENTE10K_MODO_ACOTADO` es solo del banco de modelos del notebook 02; no es válido para resultados oficiales.)

## Qué se versiona

Se versionan código, notebooks, `golden/`, resultados reproducibles, documentación y corpus. No se versionan
`.env`, `.venv/`, claves, `docs/raw/` ni duplicados del dataset. Los bytes de `data/` se preservan mediante
`.gitattributes`, porque los hashes y offsets de las anclas dependen de ellos.
