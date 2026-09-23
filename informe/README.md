# informe/ — la presentación en PDF

El entregable del aula virtual. El enunciado pide «un informe en pdf» (§5) y luego dice que
«se presentará el pdf entregado en el aula virtual» (§6), así que es un único documento que
funciona como informe leído y como presentación proyectada.

**Salida:** `Presentacion_Grupo3_10K.pdf` — 20 páginas de 1280×720 px (16:9 exacto).
Portada, 12 páginas de contenido, una de cierre y 6 anexos.

## Regenerarlo

```powershell
.venv\Scripts\python.exe informe\datos_informe.py   # resultados/ -> datos.json
.venv\Scripts\python.exe informe\figuras.py         # datos.json  -> figuras/*.svg
.venv\Scripts\python.exe informe\construir.py       # plantilla   -> PDF
```

El último paso necesita Google Chrome instalado: se usa su modo sin ventana para imprimir el
HTML a PDF. No hace falta ninguna dependencia extra.

## Qué hace cada fichero

| Fichero | Para qué |
| --- | --- |
| `datos_informe.py` | Lee `resultados/`, `golden/` y el corpus y vuelca todas las cifras en `datos.json`: métricas por sistema, matriz pregunta a pregunta, etapas del evaluador de cita, llamadas por herramienta, contadores del guardrail, escalera de búsqueda con su techo y dos trazas completas de ejemplo |
| `figuras.py` | Genera las ocho figuras en SVG a partir de `datos.json` |
| `plantilla.html` | La estructura y el texto de las 20 páginas |
| `estilos.css` | Maquetación de impresión; cada página tiene 508 px de cuerpo útil |
| `construir.py` | Incrusta estilos, figuras y las dos tablas generadas, y llama a Chrome |
| `presentacion.html` | Resultado intermedio, autocontenido: se abre en cualquier navegador |

## La regla que gobierna esto

**Ninguna cifra del PDF está escrita a mano.** Todas salen de `resultados/` a través de
`datos.json`, y las dos tablas generadas (la escalera de búsqueda y las trece ejecuciones)
las construye `construir.py`. Si se vuelve a medir una ejecución, basta con repetir los tres
comandos de arriba.

La única excepción está marcada en el código: los cuatro valores de coste en tokens de
`f1_herramientas` vienen de la medición de clase sobre este mismo corpus, no de un artefacto
de `resultados/`.

Lo que sí se escribe a mano es el texto: titulares, explicaciones y notas.

## Si se cambia el texto

Editar `plantilla.html` y volver a ejecutar `construir.py`. Conviene mirar el PDF después:
cada página recorta lo que se salga (`overflow: hidden`), así que un párrafo de más puede
desaparecer sin avisar. Las páginas más ajustadas son la 8 (escalera), la 9 (enrutado) y el
anexo 4 (la tabla de trece filas).

Los números de página los lleva un contador de CSS, así que no hay que tocarlos al insertar o
quitar una lámina. Las referencias cruzadas del texto («página 8», «anexo 4») sí son manuales.

## Estructura de las 20 páginas

| | |
| --- | --- |
| Portada | título, grupo y repositorio; sin más |
| 1–2 | el problema, el corpus con sus trampas y las cuatro herramientas |
| 3–4 | la arquitectura del agente y los tres cambios que hicimos |
| **5** | **la tabla punto de partida vs final que exige el enunciado**, con recall@k |
| 6–7 | pregunta a pregunta con el embudo de la cita, y una traza completa |
| 8–9 | la escalera de búsqueda y el enrutado entre los cuatro caminos |
| 10–11 | la decisión de proveedor y el registro de lo que no funcionó |
| 12 | cierre |
| 13 | la tabla del hold-out, publicada vacía el día antes |
| 14 | portadilla de anexos |
| 15–19 | anexos: cómo medimos, las siete que fallamos, las trece ejecuciones, reproducción y glosario |

El PDF lleva texto justificado con partición automática en los párrafos anchos; los bloques
estrechos y los que contienen varios literales de código van en bandera (clase `bandera`),
porque justificarlos abría demasiado los espacios.
