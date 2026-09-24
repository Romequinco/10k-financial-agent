# 10k-financial-agent · Grupo 3 · Entrega

> **Esta rama (`main`) contiene únicamente la entrega:** la presentación en PDF y las respuestas en JSON
> a las diez preguntas ciegas. **El código, los notebooks, los datos, los tests y el resto de resultados
> están en la rama [`codigo`](https://github.com/Romequinco/10k-financial-agent/tree/codigo).**

## Qué hay en `main`

| Fichero | Contenido |
| --- | --- |
| `Presentacion_Grupo3_10K.pdf` | La presentación / informe de la práctica |
| `ciegas/preguntas.jsonl` | Las 10 preguntas ciegas recibidas el día 24, con su respuesta esperada |
| `ciegas/resumen.json` | Métricas agregadas de las 10 preguntas ciegas (acierto micro/macro, por familia, latencia, tokens, coste) |
| `ciegas/puntuaciones.jsonl` | Una línea por pregunta ciega con la evaluación de cifra, cita y trayectoria |
| `ciegas/manifest.json` | Con qué sistema, modelo y commit se generaron (sistema `final`, `google/gemini-3.8-flash`, temperatura 0) |

Resultado en las ciegas: **8/10 (micro 0,80; macro 0,88)**. Numéricas 1/1, extractivas 3/3,
comparativas 2/4 y huecos 2/2, sin errores de ejecución.

## Ramas

| Rama | Qué contiene |
| --- | --- |
| `main` | Solo la entrega (este README, el PDF y los JSON de las ciegas) |
| `codigo` | El repositorio completo: `src/agente10k`, notebooks 00–09, `data/`, `golden/`, `resultados/`, `docs/`, `tests/` e `informe/` (fuentes del PDF) |
| `backup` | Copia de seguridad del repositorio completo, idéntica a `codigo` en el momento de la entrega |

Para ejecutar o revisar el agente: `git checkout codigo` y seguir su `README.md`.
