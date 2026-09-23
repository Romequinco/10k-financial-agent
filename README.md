# 10k-financial-agent

Agente de investigación financiera sobre informes 10-K de la SEC. Combina hechos XBRL, retrieval sobre el texto,
enrutado de herramientas y evaluación reproducible para NVDA, MSFT, AAPL, GOOGL, META y AMZN (FY2024 y FY2025).

Práctica de *LLMs aplicados a Finanzas* del máster MIAX. Enunciado: [docs/00_enunciado.md](docs/00_enunciado.md).

## Grupo

- Óscar Romero Quincoces
- Daniel García López
- Fernando Dapena Tauste

## Estado a 22-sep-2026

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

Como el proveedor gratuito varía mucho de una hora a otra y `temperature=0` **no** es determinista con él, el
sistema final se mide varias veces. La ejecución oficial es `resultados/final/`; las réplicas están en
`resultados/final_r2_t*`:

| Ejecución | numérica | extractiva | comparativa | hueco | micro | latencia media | errores |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `final` (oficial) | 7/7 | **4/6** | 1/7 | 6/6 | 60 % | 168,8 s | 6 |
| `final_r2_t1` | 7/7 | 1/6 | **4/7** | 6/6 | 60 % | 43,4 s | 0 |
| `final_r2_t2` | 7/7 | 0/6 | **5/7** | 6/6 | 60 % | 79,0 s | 3 |
| `baseline_nexn25pro` | 7/7 | 0/6 | 0/7 | 3/6 | 35 % | 97,8 s | 7 |

Lectura honesta, que es el resultado más importante de esta ronda:

- Con el mismo modelo, el sistema final **gana en todas las familias** frente al agente de partida: comparativas
  0/7 → hasta 5/7, extractivas 0/6 → hasta 4/6, huecos 3/6 → 6/6 en las tres réplicas.
- **Cada familia supera el aprobado en al menos una réplica, pero nunca las cuatro a la vez**, y el motivo está
  medido: el proveedor gratuito descarta entre 0 y 6 preguntas por tanda al agotarse el plazo de 300 s. Donde no
  las descarta, la familia aprueba. La variabilidad de las comparativas la explican los plazos agotados; la de
  las extractivas, que el modelo elige frases distintas en cada pasada.
- Dos extractivas (g3-009 y g3-010) fallan en casi todas las tandas porque el juez no da por equivalente la frase
  citada con la `respuesta_esperada` del golden, que apunta a otra frase del mismo pasaje.
- Los `PlazoAgotado` agotados **cuentan como fallo del sistema** y nunca salen del denominador: el límite real de
  este agente hoy no es su razonamiento, sino la fiabilidad del proveedor gratuito.

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

## Estructura

```text
src/agente10k/     paquete: datos, tools, retrieval, agente, guardrails y evaluación
notebooks/         recorrido 00–08; lógica reutilizable en src/
golden/            golden_propio.jsonl y golden_huecos.jsonl
resultados/        ejecuciones, rankings, cachés y experimentos
tests/             contratos y pruebas sin red
data/              corpus e índice FAISS del curso
docs/              requisitos, teoría, guías y protocolo de entrega
```

## Convenciones de resultados

- `resultados/baseline/`: evidencia histórica; no sobrescribir.
- `resultados/candidato_07/`: ejecución provisional completa, siempre descrita como «sin guardrails».
- `resultados/final/`: se crea únicamente cuando el middleware del 06 esté implementado y probado.
- `resultados/retrieval/<huella>/`: escalera aislada y reproducible de retrieval.
- `resultados/experimentos/`: diagnósticos exploratorios; no se presentan como métrica del sistema.

No se versionan `.env`, `.venv/`, claves ni material de `docs/raw/`. Véanse el
[índice de documentación](docs/README.md), la [matriz R01–R15](docs/01_requisitos_y_contratos.md) y el
[protocolo de medición y entrega](docs/13_skill_medicion_informe_presentacion.md).
