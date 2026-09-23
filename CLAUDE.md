# 10k-financial-agent

Práctica MIAX: agente trazable sobre informes 10-K. Mandan `docs/00_enunciado.md` y
`docs/01_requisitos_y_contratos.md`. Se trabaja directamente en `main` y se hace `git pull --ff-only` antes de
empezar y antes de publicar cambios.

## Estado operativo

- 00–05: implementados. Golden propio de 20 preguntas y golden de 6 huecos validados; baseline y escalera de
  retrieval guardados.
- 06: `guardrails.middleware_final()` implementado y probado sin red (límites, verificador XBRL, cita por frase
  numerada, `fuente` derivada, reparación y camino rápido). Notebook 06 con demo sin red.
- 07: `candidato_07` integra el retrieval mejorado sin guardrails; `final` monta retrieval mejorado + guardrails,
  medido oficialmente. Las réplicas `final_r2_t*` sirven para estimar la varianza del proveedor gratuito.
- 08: estructura lista; pendiente de recibir las diez preguntas ciegas.
- 09: anexo de ablación de proveedor, con datos reales. Repite la medición de `final` cambiando solo el modelo
  (`google/gemini-3.8-flash`, de pago) e iguala el juez re-puntuando la tanda gratuita (`final_jp`). Resultado:
  micro 60 % → 75 %; las cuatro preguntas recuperadas son las cuatro que tenían `PlazoAgotado`, y quedan cuatro
  irreductibles (g3-009, g3-010, g3-018, g3-020). No es el sistema entregado.

Sistemas admitidos por la API interna:

| Sistema | Retrieval | Guardrails | Carpeta canónica |
| --- | --- | --- | --- |
| `baseline` | Denso original | No | `resultados/baseline/` |
| `cascada` | Denso original | No | Etiqueta experimental |
| `candidato_07` | Mejorado | No | `resultados/candidato_07/` |
| `final` | Mejorado | Sí | `resultados/final/` |

No se permite degradar `candidato_07` o `final` a baseline. `resultados/final/` solo se crea con la ejecución
oficial (`evaluar(..., etiqueta="final", sistema="final")`), con el mismo modelo y `temperature=0` que el baseline
al que se compare. La columna «Carpeta canónica» no agota las etiquetas: un mismo sistema tiene varias si cambia
el modelo, y todas siguen siendo `sistema="final"`.

Una comparación evaluada exige el mismo modelo en las dos filas. Hay tres modelos medidos y **tres pares
válidos**; cruzarlos no lo es:

| Modelo | Baseline | Final |
| --- | --- | --- |
| `ling-3.0-flash-fin:free` (histórico) | `resultados/baseline/` | — |
| `nex-agi/nex-n2.5-pro:free` (`config.MODELO_ID`, el entregado) | `resultados/baseline_nexn25pro/` | `resultados/final/` |
| `google/gemini-3.8-flash` (de pago, anexo del 09) | `resultados/baseline_pago/` | `resultados/final_pago/` |

`tabla_r11()` avisa y no remarca ningún ganador si las filas no comparten modelo. Ojo: compara el modelo del
**agente**, no el del **juez**, porque `_fila_comparativa()` no expone ese campo. Comparar `final` con `final_jp`
pasaría el aviso sin ser una comparación de sistemas; ese control se hace a mano en el notebook 09.

Parámetros de ejecución, todos con variable de entorno: plazo duro por pregunta `AGENTE10K_PLAZO_S` (300 s),
reintentos del cliente `AGENTE10K_MAX_RETRIES` (1) e intentos por pregunta `evaluadores.INTENTOS_FILA` (2, solo
ante fallo de infraestructura). El peor caso de una pregunta queda acotado; los `PlazoAgotado` agotados cuentan
como fallo del sistema y nunca salen del denominador.

## Estructura y responsabilidades

- `src/agente10k/config.py`: rutas, modelos y clave.
- `src/agente10k/datos.py`: carga y verificación del corpus.
- `src/agente10k/herramientas.py`: cuatro herramientas públicas y adaptación de retrieval.
- `src/agente10k/retrieval.py`: denso, filtros, BM25, RRF y reescritura.
- `src/agente10k/agente.py`: `RespuestaFinanciera`, construcción de sistemas y `responder()`.
- `src/agente10k/guardrails.py`: límite de llamadas y verificación XBRL del 06.
- `src/agente10k/evaluadores.py`: ejecución, puntuación y persistencia.
- `src/agente10k/evaluacion.py`: fachada pública, golden, retrieval y tablas.
- `notebooks/`: demostración y análisis; la lógica compartida vive en `src/`.

## Reglas invariantes

1. No cambiar nombres o parámetros obligatorios de `list_available`, `get_xbrl_fact`, `search_filings`,
   `read_section`, `responder(pregunta)` ni `evaluar(ruta_jsonl)`. Solo se añaden parámetros con valor por defecto.
2. Mantener los ocho campos obligatorios de `RespuestaFinanciera` y todos los campos oficiales del golden.
3. Usar rutas de `agente10k.config`; no depender del directorio de ejecución.
4. Modelo fijado y `temperature=0` en comparaciones evaluadas.
5. Claves únicamente en entorno o `.env`, nunca en código, notebooks o resultados.
6. `data/` es de solo lectura. `resultados/baseline/` no se sobrescribe.
7. Distinguir siempre resultados oficiales, provisionales y exploratorios. El 12/13 manual de retrieval no es una
   métrica del agente.
8. Los notebooks deben ejecutar con `EJECUTAR=False` sin red y sin artefactos opcionales.
9. Antes de un commit: pruebas pertinentes, JSON válido de notebooks y revisión de `git diff`.
10. Los mensajes de commit son neutros y en español; no se añaden coautorías ni menciones ajenas al grupo.

## Comandos de verificación

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -c "import json,glob; [json.load(open(p, encoding='utf-8')) for p in glob.glob('notebooks/*.ipynb')]; print('JSON válido')"
.venv\Scripts\python.exe -c "from agente10k.evaluacion import cargar_golden, validar_golden; from agente10k import config; p=cargar_golden(config.GOLDEN/'golden_propio.jsonl'); assert not validar_golden(p); print('golden válido')"
git status --short
```

El 06 está completo y `resultados/final/` es la ejecución oficial del sistema entregado. Una medición nueva usa
siempre una **etiqueta nueva** (`evaluar(..., etiqueta="mi_tanda", sistema="final")`), nunca una existente: el
`manifest.json` bloquea la reutilización si no coinciden golden, sistema, modelo, límite y retrieval, y las
etiquetas que empiezan por `baseline` están protegidas contra sobrescritura.

Para medir con otro modelo se fijan **las dos** variables, `AGENTE10K_MODELO` y `AGENTE10K_MODELO_JUEZ`: si solo
se cambia la primera, el juez cambia por arrastre y el resultado deja de ser atribuible al agente. Para igualar
el juez de una tanda ya medida sin volver a llamar al agente, `evaluadores.repuntuar(origen, juez=..., guardar_en=...)`,
que nunca escribe en la carpeta de origen.

Aviso conocido: `manifest_ejecucion()` ya no escribe `paso_aislado`, que es lo que `_recall_aislado()` necesita,
así que la columna `recall@5` de `tabla_r11()` sale vacía para toda etiqueta creada con el código actual. Para
comparar modelos la columna informativa es `recall_agente`, que sí viaja en el resumen.
