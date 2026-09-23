# 10k-financial-agent

Agente de investigación financiera sobre informes 10-K de la SEC. Combina hechos XBRL, retrieval sobre el texto,
enrutado de herramientas y evaluación reproducible para NVDA, MSFT, AAPL, GOOGL, META y AMZN (FY2024 y FY2025).

Práctica de *LLMs aplicados a Finanzas* del máster MIAX. Enunciado: [docs/00_enunciado.md](docs/00_enunciado.md).

## Grupo

- Óscar Romero Quincoces
- Daniel García López
- Fernando Dapena Tauste

## Estado a 23-sep-2026

Las fases 00–05 están implementadas y verificadas: corpus, cuatro herramientas, agente baseline, golden set,
evaluadores y escalera de retrieval. `guardrails.middleware_final()` (06) está implementado: límite de llamadas,
verificador XBRL determinista, cita por frase numerada, `fuente` derivada de la trayectoria y reparación cuando
falta la respuesta estructurada, todo probado sin red. El sistema `final` (retrieval mejorado + esos guardrails)
ya se monta y se ha medido con una ejecución oficial real; `candidato_07` sigue disponible como referencia sin
guardrails.

| Sistema | Qué ejecuta | Resultados | Estado |
| --- | --- | --- | --- |
| `baseline` | Herramientas y retrieval denso original | `resultados/baseline/` | Medido y preservado (histórico, `ling-3.0-flash-fin:free`) |
| `candidato_07` | Mismo agente con retrieval mejorado | `resultados/candidato_07/` | Provisional, sin guardrails |
| `final` | Retrieval mejorado + guardrails del 06 | `resultados/final/` | Medido; ejecución oficial con `nex-n2.5-pro:free` |

El baseline histórico (`ling-3.0-flash-fin:free`) obtuvo 7/7 numéricas, 0/6 extractivas y 0/7 comparativas
(micro 35 %), con 9,85 s, 23.638 tokens y 3,3 llamadas de media por pregunta. Son métricas del artefacto fechado
el 18-sep y commit `bb24fb4`; el coste USD quedó sin dato del proveedor. Se conserva sin tocar.

Una comparación con otro modelo exige re-medir el baseline con ese modelo. Con `nex-agi/nex-n2.5-pro:free` en
las dos filas y el mismo golden, `resultados/baseline_nexn25pro/` obtuvo 7/20 (micro 35 %) y 3/6 huecos, frente
al sistema `final`. La tabla del enunciado la genera `evaluacion.tabla_r11()`, con coste y latencia como
columnas y el mejor valor marcado.

El mismo par existe medido con un modelo de pago, `google/gemini-3.8-flash`: `resultados/baseline_pago/` y
`resultados/final_pago/`. Es el **anexo de ablación de proveedor** del [notebook 09](notebooks/09_anexo_proveedor.ipynb),
no el sistema entregado.

Como el proveedor gratuito varía mucho de una hora a otra y `temperature=0` **no** es determinista con él, el
sistema final se mide varias veces. La ejecución oficial es `resultados/final/`; las réplicas están en
`resultados/final_r2_t*`:

| Ejecución | numérica | extractiva | comparativa | hueco | micro | latencia media | errores | USD/pregunta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `final` (oficial, entregado) | 7/7 | **4/6** | 1/7 | 6/6 | 60 % | 168,8 s | 6 | 0,00 |
| `final_r2_t1` | 7/7 | 1/6 | 4/7 | 6/6 | 60 % | 43,4 s | 0 | 0,00 |
| `final_r2_t2` | 7/7 | 0/6 | **5/7** | 6/6 | 60 % | 79,0 s | 3 | 0,00 |
| `baseline_nexn25pro` | 7/7 | 0/6 | 0/7 | 3/6 | 35 % | 97,8 s | 7 | 0,00 |

Lectura honesta, que es el resultado más importante de esta ronda:

- Con el mismo modelo, el sistema final **gana en todas las familias** frente al agente de partida: comparativas
  0/7 → hasta 5/7, extractivas 0/6 → hasta 4/6, huecos 3/6 → 6/6 en las tres réplicas.
- **Cada familia supera el aprobado en al menos una réplica, pero nunca las cuatro a la vez**, y el motivo está
  medido: el proveedor gratuito descarta entre 0 y 6 preguntas por tanda al agotarse el plazo de 300 s. Donde no
  las descarta, la familia aprueba. La variabilidad de las comparativas la explican los plazos agotados; la de
  las extractivas, que el modelo elige frases distintas en cada pasada.
- Dos extractivas (g3-009 y g3-010) fallan en casi todas las tandas porque el juez no da por equivalente la frase
  citada con la `respuesta_esperada` del golden, que apunta a otra frase del mismo pasaje.
- El coste sale `0,00` porque el proveedor gratuito no informa de ninguno, no porque el agente sea gratis. La
  regla que lo decide queda escrita en `coste_fuente` de cada `resumen.json`.
- Los `PlazoAgotado` agotados **cuentan como fallo del sistema** y nunca salen del denominador. De ahí salía la
  hipótesis de esta ronda: que el límite de este agente no es su razonamiento sino la fiabilidad del proveedor
  gratuito.

### Anexo: cuánto de ese techo es del proveedor

Esa hipótesis era un argumento, no una medida, y medida resulta ser cierta solo a medias. El
[notebook 09](notebooks/09_anexo_proveedor.ipynb) la pone a prueba repitiendo la misma medición con **una sola
variable distinta**: el modelo. Sistema, golden, retrieval, prompts, guardrails, plazo y juez se quedan fijos;
el juez se iguala re-puntuando la tanda gratuita con el de pago (`final_jp`), que da exactamente la misma nota
y descarta que el salto venga de un corrector más blando.

| Ejecución | numérica | extractiva | comparativa | hueco | micro | latencia mediana | errores | USD/pregunta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `final_jp` (gratuito, juez de pago) | 7/7 | 4/6 | 1/7 | 6/6 | 60 % | 171,8 s | 6 | 0,00 |
| `final_pago` (`gemini-3.8-flash`) | 7/7 | 4/6 | **4/7** | 6/6 | **75 %** | **21,6 s** | **0** | 0,0191 |
| `baseline_pago` (`gemini-3.8-flash`) | 7/7 | 0/6 | 0/7 | 6/6 | 35 % | 14,6 s | 3 | 0,0118 |

Qué se aprende, y en las dos direcciones:

- De las ocho preguntas que falla el sistema entregado, **cuatro son del proveedor y cuatro son nuestras**. Las
  cuatro recuperadas (g3-014, g3-016, g3-017, g3-019) son exactamente las cuatro que se quedaron sin respuesta
  por plazo agotado: la atribución es completa.
- Las cuatro irreductibles no las arregla ningún proveedor. g3-009 y g3-010 son el desacuerdo entre la frase
  citada y la del golden —confirmado con un segundo juez—, y g3-018 y g3-020 exigen un razonamiento que el
  modelo no hace (el split 10:1 de NVIDIA, una nota al pie sobre caja restringida). **El techo real del agente
  hoy es 16/20.**
- `recall_agente` sube de 0,77 a 0,92 con el mismo retrieval determinista: lo que mejora no es el buscador sino
  la consulta que el agente le pasa.
- **En contra nuestra:** `baseline_pago_huecos` acierta 6/6 sin ningún guardrail, frente a los 3/6 de
  `baseline_nexn25pro_huecos`. La subida de huecos que atribuimos a la regla de universo también la logra el
  modelo por sí solo; el guardrail hace falta con el proveedor que usamos, pero su mérito no es exclusivo.
- `baseline_pago` perdió 3 preguntas por errores 400 y 429 porque las cuatro tandas se lanzaron en paralelo
  contra la misma clave. Eso penaliza al baseline y por tanto **favorece** a `final_pago`; queda declarado en el
  notebook. No afecta al par `final_jp`/`final_pago`, donde hubo 0 errores.

La ejecución oficial y completa de retrieval `5976eb180c38` mide 13 preguntas con ancla. Su recall@5 pasa de
2/13 en el denso a 4/13 con filtro y 5/13 con BM25; la reescritura conserva 5/13. El 12/13 obtenido en un
experimento manual de `resultados/experimentos/` es diagnóstico exploratorio, no rendimiento del agente ni cifra
del sistema final.

## Instalación en Windows

```powershell
git clone https://github.com/Romequinco/10k-financial-agent.git
cd 10k-financial-agent
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Rellenar OPENROUTER_API_KEY en .env
.venv\Scripts\python.exe -m pytest -q
```

Se requiere Python 3.12 o superior. Hay que ejecutar siempre el intérprete del `.venv` creado en este checkout;
una instalación editable de otra copia del repositorio puede importar código obsoleto.

## Uso

```python
from agente10k import responder, evaluar

respuesta = responder("¿Cuál fue el revenue de NVIDIA en FY2025?")   # sistema "final" por defecto
tabla = evaluar("golden/golden_propio.jsonl", etiqueta="mi_tanda", sistema="final")
```

`responder()` usa `final` por defecto, con el modelo de `config.MODELO_ID`. Tanto `final` como
`candidato_07` buscan con BM25: el agente prepara palabras clave en inglés y filtros de empresa/ejercicio,
sin `item`. El baseline denso sigue disponible con `sistema="baseline"` para reproducir la referencia.
Tras actualizar el código, reinicia el kernel. Las nuevas evaluaciones requieren otra etiqueta para
evitar reutilizar las predicciones del híbrido anterior.

Ejecución completa desde PowerShell:

```powershell
.venv\Scripts\python.exe -c "from agente10k.evaluacion import evaluar; evaluar('golden/golden_propio.jsonl', etiqueta='mi_tanda', sistema='final')"
.venv\Scripts\python.exe -c "from agente10k.evaluacion import tabla_r11; print(tabla_r11(('baseline_nexn25pro','final')).to_string(index=False))"
```

`responder()` usa el sistema `final` por defecto, que es el que se entrega: así las diez preguntas ciegas se
ejecutan sin tocar código, como pide el enunciado. El modelo por defecto es `nex-agi/nex-n2.5-pro:free`
(`AGENTE10K_MODELO` lo cambia), el mismo con el que están medidos `final` y `baseline_nexn25pro`.

Para medir con otro modelo no hace falta tocar código, solo el entorno. Las dos variables van juntas: si se
cambia `AGENTE10K_MODELO` sin cambiar `AGENTE10K_MODELO_JUEZ`, el juez pasa a ser el modelo nuevo por arrastre
y la comparación deja de ser atribuible al agente. Así se midió el anexo del 09:

```powershell
$env:AGENTE10K_MODELO      = "openrouter:google/gemini-3.8-flash"
$env:AGENTE10K_MODELO_JUEZ = "openrouter:google/gemini-3.8-flash"
.venv\Scripts\python.exe -m agente10k golden/golden_propio.jsonl --etiqueta final_pago --sistema final
```

Las órdenes oficiales no llevan ninguna variable de entorno especial. `AGENTE10K_MODO_ACOTADO=1` existe solo para
el banco de modelos del notebook 02: ejecuta únicamente la primera herramienta, no usa `ToolStrategy` y no
reproduce `candidato_07`, así que **no es válido para resultados oficiales**.

`evaluar()` reutiliza `predicciones.jsonl` si ya existe para la etiqueta y coinciden el hash del golden, el
sistema, el modelo, el límite y el retrieval de su `manifest.json` (el commit y el árbol sucio solo dan un aviso).
Para una ejecución nueva se debe elegir una etiqueta nueva o retirar deliberadamente el artefacto anterior; nunca se
sobrescribe el baseline congelado. Una tanda cortada continúa por id al repetir la orden. Sin `juez`, `evaluar()`
crea uno (`AGENTE10K_MODELO_JUEZ` o el modelo del agente); si no puede, avisa y el resumen queda `parcial`, sin
`micro` ni `macro`.

La CLI acepta `baseline`, `candidato_07` y `final`:

```powershell
.venv\Scripts\python.exe -m agente10k golden/golden_propio.jsonl --etiqueta candidato_07 --sistema candidato_07
```

`--sistema final` (el valor por defecto) ya monta retrieval mejorado + los guardrails del 06 y gasta API real.
Si `middleware_final()` no devolviera una pila válida, terminaría con un error explícito (código 2) antes de
crear ningún artefacto, sin sustituir `final` por el baseline ni por el candidato.

## Notebooks

Cada notebook se puede abrir de forma independiente. Los que llaman a OpenRouter usan `EJECUTAR = False` por defecto.

| Nº | Contenido | Estado |
| --- | --- | --- |
| 00 | Entorno, integridad y exploración de datos | Completado |
| 01 | Cuatro herramientas y búsqueda densa | Completado |
| 02 | Agente baseline, salida estructurada y trazas | Completado |
| 03 | Golden propio (20) y golden de huecos (6) | Completado |
| 04 | Evaluadores y baseline guardado | Completado |
| 05 | Filtro, BM25 + denso, RRF y reescritura | Completado |
| 06 | Límite de llamadas y verificación XBRL | Completado; demo sin red |
| 07 | Candidato, comparación baseline/candidato/final | Completado; `final` con datos oficiales |
| 08 | Diez preguntas ciegas del día 24 | Estructura lista; pendiente de recibirlas |
| 09 | Anexo: ablación de proveedor (modelo de pago) | Completado; datos reales |

## Estructura

```text
src/agente10k/     paquete: datos, tools, retrieval, agente, guardrails y evaluación
notebooks/         recorrido 00–09; lógica reutilizable en src/
golden/            golden_propio.jsonl y golden_huecos.jsonl
resultados/        ejecuciones, rankings, cachés y experimentos
tests/             contratos y pruebas sin red
data/              corpus e índice FAISS del curso
docs/              requisitos, teoría, guías y protocolo de entrega
```

## Convenciones de resultados

El nombre de una carpeta de `resultados/` es `<sistema>[_<variante>][_r2_t<n>][_jp][_huecos]`:

| Parte | Qué significa |
| --- | --- |
| `<sistema>` | `baseline`, `candidato_07` o `final`: qué agente se ejecutó |
| `_<variante>` | Con qué modelo: sin sufijo es el histórico, `_nexn25pro` el gratuito actual, `_pago` el de pago |
| `_r2_t<n>` | Réplica de la misma configuración, para estimar la varianza del proveedor |
| `_jp` | **Re-puntuación**, no una ejecución: las mismas predicciones vistas por otro juez (`repuntuar()`) |
| `_huecos` | El golden de huecos en vez del golden propio. `tabla_r11()` lo busca como `<etiqueta>_huecos` |

- `resultados/baseline/` y `resultados/baseline_huecos/`: evidencia histórica congelada; no se sobrescriben
  (`ejecutar_golden` lo impide para cualquier etiqueta que empiece por `baseline`).
- `resultados/candidato_07/`: ejecución provisional completa, siempre descrita como «sin guardrails».
- `resultados/final/`: la ejecución oficial del sistema entregado.
- `resultados/retrieval/<huella>/`: escalera aislada y reproducible de retrieval.
- `resultados/experimentos/`: diagnósticos exploratorios; no se presentan como métrica del sistema.

Una etiqueta `_jp` contiene solo `puntuaciones.jsonl` y `resumen.json` (con el campo `repuntuado_de`), nunca
`predicciones.jsonl`: es una fila de *puntuación*, no de *ejecución*, y no debe mezclarse con las demás en la
tabla principal del R11.

No se versionan `.env`, `.venv/`, claves ni material de `docs/raw/`. Véanse el
[índice de documentación](docs/README.md), la [matriz R01–R15](docs/01_requisitos_y_contratos.md) y el
[protocolo de medición y entrega](docs/13_skill_medicion_informe_presentacion.md).
