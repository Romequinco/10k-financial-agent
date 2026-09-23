# Medición, sistema final, informe y presentación

> Requisitos: R10–R15 · Lee antes: [01](01_requisitos_y_contratos.md),
> [11](11_skill_mejora_retrieval.md) y [12](12_skill_evaluadores.md).

Actualización operativa de 21-sep-2026, con nota de 22-sep-2026: el notebook 06 y `middleware_final()` ya están
implementados y probados sin red, y `final` tiene una ejecución oficial en `resultados/final/` (mismo modelo que
`resultados/baseline_nexn25pro/`, una sola tanda). El resto de esta guía describe el procedimiento seguido y
sigue vigente para repetir o ampliar la medición.

## 1. Tres sistemas, tres significados

| Sistema | Componentes | Etiqueta canónica | Uso |
| --- | --- | --- | --- |
| `baseline` | Agente y retrieval denso original | `baseline` | Referencia histórica; no sobrescribir |
| `candidato_07` | Agente y retrieval mejorado | `candidato_07` | Comparación provisional sin guardrails |
| `final` | Retrieval mejorado + `middleware_final()` | `final` | Medido oficialmente; sigue fallando con un error claro si `middleware_final()` no diera una pila válida |

`final` nunca se sustituye por baseline ni por candidato. Comparar `final` con un modelo distinto del histórico
exige re-medir el baseline con ese mismo modelo bajo una etiqueta nueva (`resultados/baseline_nexn25pro/`); el
`resultados/baseline/` original no se toca.

`resultados/experimentos/` contiene diagnósticos. El 12/13 manual no es una fila válida de la tabla R11 porque no
procede de una configuración autónoma del agente.

## 2. Qué existe ahora

- Baseline histórico (`ling-3.0-flash-fin:free`): `resultados/baseline/` y `resultados/baseline_huecos/`, congelados.
- Baseline del modelo entregado (`nex-n2.5-pro:free`): `resultados/baseline_nexn25pro/` y su `_huecos`.
- Candidato: `resultados/candidato_07/` y su `_huecos`, retrieval mejorado sin guardrails.
- **Final (sistema entregado):** `resultados/final/` y `resultados/final_huecos/`, más las réplicas de varianza
  `resultados/final_r2_t1/` y `final_r2_t2/` con sus `_huecos`.
- **Sistema entregado (notebook 08, `gemini-3.8-flash`):** `resultados/final_entregado/` y
  `final_entregado_huecos/`, con su par del R11 en `baseline_entregado/` y `baseline_entregado_huecos/`.
  Son las medidas sobre el código publicado y las únicas que deben ir en la tabla del R11 del informe.
- **Ablación de proveedor (notebook 08, par con código idéntico entre sí):** `resultados/final_pago/`,
  `final_pago_huecos/`, `baseline_pago/` y `baseline_pago_huecos/`, más las re-puntuaciones `final_jp/` y
  `final_jp_huecos/` (mismas predicciones de `final`, juez de pago; solo `puntuaciones.jsonl` y `resumen.json`).
- Retrieval: `resultados/retrieval/5976eb180c38/`, ejecución completa sin fallos de reescritura.

Las cifras históricas del baseline se leen de su `resumen.json`; no se recalculan a mano. Las métricas del candidato
y del final se publican únicamente después de existir sus artefactos completos.

## 3. Ejecución reproducible

Instalación y pruebas en PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Configurar OPENROUTER_API_KEY sin versionarla
.venv\Scripts\python.exe -m pytest -q
```

Ejecución real del candidato sobre todas las preguntas:

```powershell
.venv\Scripts\python.exe -c "from agente10k.evaluacion import evaluar; evaluar('golden/golden_propio.jsonl', etiqueta='candidato_07', sistema='candidato_07')"
```

No se define `AGENTE10K_MODO_ACOTADO`: ese modo (solo la primera herramienta, sin `ToolStrategy`) es únicamente para
el banco de modelos del notebook 02 y no es válido para resultados oficiales ni reproduce `candidato_07`.

`evaluar()` no vuelve a llamar al modelo si ya existe `predicciones.jsonl` para la etiqueta y su `manifest.json`
coincide en golden (hash), sistema, modelo, límite y retrieval; commit, árbol sucio y diff solo producen un aviso.
Esto hace regenerable la puntuación, pero también obliga a usar una etiqueta nueva cuando se quiere una repetición
independiente. Los artefactos anteriores al manifest se bendicen sin tocar sus predicciones con
`evaluadores.bendecir_legacy`. El baseline canónico no se retira ni sobrescribe.

El sistema final se mide así (ya ejecutado; repetirlo exige una etiqueta nueva):

```powershell
.venv\Scripts\python.exe -c "from agente10k.evaluacion import evaluar; evaluar('golden/golden_propio.jsonl', etiqueta='final', sistema='final')"
.venv\Scripts\python.exe -c "from agente10k.evaluacion import evaluar; evaluar('golden/golden_huecos.jsonl', etiqueta='final_huecos', sistema='final')"
```

### Medir con otro modelo (ablación de proveedor)

Se fijan **las dos** variables. Cambiar solo `AGENTE10K_MODELO` arrastra el juez al modelo nuevo y el resultado
deja de ser atribuible al agente:

```powershell
$env:AGENTE10K_MODELO      = "openrouter:google/gemini-3.8-flash"
$env:AGENTE10K_MODELO_JUEZ = "openrouter:google/gemini-3.8-flash"
$env:AGENTE10K_PLAZO_S     = "300"

.venv\Scripts\python.exe -m agente10k golden/golden_propio.jsonl --etiqueta final_pago            --sistema final
.venv\Scripts\python.exe -m agente10k golden/golden_huecos.jsonl --etiqueta final_pago_huecos     --sistema final
.venv\Scripts\python.exe -m agente10k golden/golden_propio.jsonl --etiqueta baseline_pago         --sistema baseline
.venv\Scripts\python.exe -m agente10k golden/golden_huecos.jsonl --etiqueta baseline_pago_huecos  --sistema baseline
```

El baseline pareado no es opcional: sin él, `final_pago` no puede entrar en ninguna tabla del R11. Después se
iguala el juez de la tanda gratuita, sin volver a llamar al agente:

```powershell
.venv\Scripts\python.exe -c "from agente10k import evaluadores as e; j=e.crear_juez('openrouter:google/gemini-3.8-flash'); [e.repuntuar(o, juez=j, guardar_en=d) for o,d in (('final','final_jp'),('final_huecos','final_jp_huecos'))]; j.guardar()"
```

Lanzar varias tandas en paralelo contra la misma clave provoca 429: así se perdió una pregunta de
`baseline_pago`. Si el resultado tiene que ser limpio, se ejecutan en serie. Los 400 (`BadRequestResponseError`)
son otra cosa y aparecen también en serie, solo con el sistema `baseline`: el modelo entregado rechaza algunas
llamadas con salida estructurada. El sistema `final` no los produjo en 60 preguntas medidas.

**Congelar `src/` antes de medir.** El 23-sep el retrieval cambió dos veces mientras se medía y las dos veces
dejó obsoletas las tandas de `final`. Se comprueba con `git diff <commit-del-manifiesto> HEAD -- src/`, no
mirando solo el campo `retrieval` del manifiesto, que puede coincidir y aun así describir otro código.

La CLI acepta `baseline`, `candidato_07` y `final`:

```powershell
.venv\Scripts\python.exe -m agente10k golden/golden_propio.jsonl --etiqueta final --sistema final
```

Si `middleware_final()` no diera una pila válida, `--sistema final` falla con un error explícito antes de crear
artefactos; el candidato se ejecuta con `--sistema candidato_07` o con la API Python, sin falsear `final`.

### Banderas diagnósticas y modo sin referencia

`puntuaciones.jsonl` lleva columnas `diag_*` que **no cambian la nota oficial**, pero señalan laxitudes del
evaluador: cita de menos de 6 palabras, ticker o ejercicio de la respuesta distintos de los de la pregunta,
`cifra_base` ausente en una comparativa, y `chunk_id` inexistente o de otra empresa o ejercicio. `resumen.json`
las cuenta en `banderas_diagnosticas` (`k/n` sobre las filas donde aplican).

Con las ciegas del día 24 sin respuestas esperadas, las filas salen como `familia="sin_referencia"` y `acierto`
queda en None (no se inventa una referencia ni una trayectoria «esperada»). Se calcula lo verificable: cita existente
y vista, coherencia fuente↔trayectoria, cifra frente a XBRL cuando hay ticker, ejercicio y concepto (`sr_cifra_xbrl`),
abstención, llamadas, latencia y tokens; el agregado va en `resumen["sin_referencia"]`.

Si no hay juez, o alguna extractiva/comparativa no es evaluable, el resumen sale `parcial=True` y `micro`/`macro`
quedan en None; `micro_parcial` (sobre las evaluables) y `micro_cota_inferior` (las no evaluables cuentan como fallo)
se dan aparte. `resumen.json` incluye también mediana y p90 de latencia y de tokens, tokens de entrada y salida
medios, y llamadas al modelo además de las llamadas a herramienta.

## 4. Tabla R11

`tabla_comparativa()` lee los artefactos existentes y devuelve una fila no disponible para los ausentes. Esto
permite que el notebook 07 se ejecute offline antes de generar el candidato.

```python
from agente10k.evaluacion import tabla_comparativa

provisional = tabla_comparativa(("baseline", "candidato_07"))
definitiva = tabla_comparativa(("baseline", "final"))
```

La tabla contiene:

- aciertos y tasas por familia;
- micro y macro;
- recall@5 aislado y, aparte, recall observado dentro del agente;
- coste USD cuando el proveedor lo informa;
- tokens, latencia media/mediana y llamadas por pregunta;
- errores y abstenciones indebidas;
- columnas `mejor_*`, solo si hay al menos dos resultados disponibles.

No se reemplaza un coste ausente por cero. `recall@5` es la métrica aislada persistida; `recall_agente` es un
diagnóstico de los fragmentos realmente vistos durante la respuesta.

## 5. Lectura de las métricas actuales

### Baseline oficial guardado

| Métrica | Valor |
| --- | ---: |
| Numéricas | 7/7 |
| Extractivas | 0/6 |
| Comparativas | 0/7 |
| Micro | 0,35 |
| Latencia media | 9,85 s |
| Tokens medios | 23.638,25 |
| Llamadas medias | 3,3 |
| Coste USD | No disponible |

El artefacto corresponde al commit `bb24fb4` y al modelo que figura en su `resumen.json`. El golden de huecos
obtuvo 3/6.

### Retrieval oficial aislado

| Paso | Recall@5 |
| --- | ---: |
| Denso | 2/13 |
| + filtro | 4/13 |
| + BM25/RRF | 5/13 |
| + reescritura | 5/13 |

La reescritura no mejoró recall@5 respecto a BM25 en esta ejecución, aunque sí cambió otras posiciones. Es un
resultado válido que debe explicarse; no se sustituye por el techo oráculo ni por consultas manuales.

## 6. Notebook 07 antes del 06

El notebook debe poder hacer lo siguiente con `EJECUTAR=False`:

1. comprobar golden y artefactos disponibles;
2. mostrar que `candidato_07` puede construirse con retrieval mejorado;
3. comprobar que `final` está protegido mientras falta el 06;
4. leer el resumen oficial de retrieval;
5. cargar la comparación provisional sin inventar ceros para resultados ausentes;
6. explicar qué pasos convierten candidato en final.

Con `EJECUTAR=True` debe evaluar las 20 preguntas mediante OpenRouter y guardar `resultados/candidato_07/`.
La ejecución real se hace para todas las preguntas, no sobre una selección favorable.

## 7. Integración posterior del 06

El cierre debe requerir únicamente:

1. implementar y probar `middleware_final()`;
2. comprobar límite de llamadas y retroalimentación XBRL;
3. montar `final` con retrieval mejorado y middleware no vacío;
4. ejecutar golden propio y huecos bajo etiquetas finales;
5. regenerar `tabla_comparativa(("baseline", "final"))`;
6. actualizar notebook, README e informe con los valores reales;
7. repetir suite, escaneo de claves y ensayo en clon limpio.

Si para conectar el 06 hay que reescribir retrieval o evaluación, el punto de extensión no está suficientemente
aislado.

## 8. Qué no funcionó y cómo se registra

Cada experimento debe conservar fecha, commit, hipótesis, configuración, métrica antes/después, coste o latencia y
decisión. Son especialmente relevantes:

- reescritura sin mejora de recall@5 frente a BM25;
- filtros oráculo frente a filtros obtenidos sin golden;
- errores o reintentos del proveedor;
- consultas manuales que muestran techo pero no generalizan;
- cambios que ganan unas preguntas y pierden otras;
- **decisión de proveedor (23-sep-2026, notebook 08).** Hipótesis: el techo que queda es del proveedor
  gratuito. Configuración: sistema `final`, mismo golden, mismo código y juez igualado; solo cambia el modelo.
  Resultado en dos partes, y conviene no mezclarlas:
  - **Fiabilidad y latencia: confirmado con holgura.** 0 preguntas perdidas en las dos tandas de pago (40
    preguntas) frente a entre 0 y 7 plazos agotados por tanda del gratuito; latencia mediana 21 s frente a
    31–172 s. Coste real 0,0191 USD por pregunta.
  - **Acierto: refutado.** La primera tanda de pago dio 75 % de micro y la réplica dio 60 %, con el mismo
    modelo, el mismo código y `temperature=0`; tres preguntas cambian de veredicto (g3-012, g3-013, g3-016)
    sin que ninguna de las dos perdiera una sola pregunta por plazo. Con n=2 no se puede afirmar que el de
    pago acierte más, y no se afirma.
  - Decisión: **se promueve a sistema entregado por fiabilidad**, no por acierto, y así debe defenderse.
  - Resultado en contra: la subida de huecos de 3/6 a 6/6, atribuida a la regla de universo, la consigue
    también el baseline de pago **sin guardrails**, así que el mérito del guardrail no es exclusivo.
  - Error metodológico cometido y corregido, que merece contarse: la primera versión comparaba contra
    `resultados/final/`, medido en un commit anterior al merge que reescribió el retrieval y el prompt de
    `search_filings`. Tenía tres variables, no una. Se rehízo con `final_libre_actual`, una tanda del
    gratuito sobre el mismo código exacto. **Comprobar el commit del manifiesto, no solo su campo
    `retrieval`, es ahora parte del protocolo.**

Un experimento exploratorio puede orientar el diagnóstico, pero no sustituye la ejecución canónica ni se presenta
como resultado final.

## 9. Preguntas ciegas del día 24

Las diez preguntas ciegas son hold-out: se ejecutan una sola vez con el commit entregado y no se itera contra ellas.
Si llegan en JSONL compatible:

```powershell
.venv\Scripts\python.exe -m agente10k ciegas.jsonl --etiqueta ciegas --sistema final
```

Se informa el delta frente al golden por familia y por causa de fallo. Si no traen anclas, el recall se marca «—»;
si no traen herramienta esperada, se documenta el criterio aplicado. Los errores permanecen como evidencia y no
se corrigen después de ver el conjunto.

## 10. Informe y presentación

El PDF debe permitir presentar en ocho minutos:

1. problema, corpus y cuatro herramientas;
2. diseño baseline → retrieval mejorado → guardrails;
3. tabla R11 y lectura de calidad, coste, latencia y llamadas;
4. escalera de retrieval y diferencia entre medición aislada y extremo a extremo;
5. enrutado, verificación XBRL y tratamiento de huecos;
6. dos o tres experimentos que no funcionaron;
7. protocolo y resultado de ciegas;
8. limitaciones: n=20, variabilidad del proveedor y métricas ausentes.

No se afirma significación estadística con veinte preguntas. Las métricas desconocidas se muestran como tales y se
indica el commit, modelo y fecha de cada ejecución.

## 11. Ensayo en clon limpio

Antes de etiquetar y publicar el final:

```powershell
git clone <url-del-repo> clon-10k
Set-Location clon-10k
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m agente10k golden/golden_propio.jsonl --etiqueta final --sistema final
```

Comprobar además:

- hashes del corpus e importación desde este checkout;
- modelo y `temperature=0`;
- ninguna clave en árbol, historial o salidas de notebook;
- `baseline` intacto y `final` completo;
- comandos y enlaces de la documentación;
- JSON válido y ejecución offline del notebook 07;
- repo accesible desde el equipo de presentación y saldo de OpenRouter.

## 12. Puertas de cierre

- [ ] R04 y R05 probados con el middleware del 06.
- [ ] Golden propio y huecos ejecutados para `final`.
- [ ] Tabla baseline/final regenerada con todos los campos disponibles.
- [ ] Resultados finales y commit identificados; baseline preservado.
- [ ] Clon limpio probado sin editar código.
- [ ] Escaneo de claves vacío.
- [ ] PDF entregado antes del 23-sep a las 23:59.
- [ ] Presentación ensayada en ocho minutos.
- [ ] Protocolo de ciegas preparado.
