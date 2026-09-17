# Pruebas internas de retrieval desde consultas en ingles

Fecha: 17 de septiembre de 2026. Experimento separado del notebook 05 y de sus resultados oficiales.

## Resultado

Se probaron 36 combinaciones iniciales y 10 variantes adicionales sobre las 13 preguntas con ancla. Dos variantes llegaron a **12/13 (92,3 %) en top-5**. Una alternativa con limpieza generica del texto y extraccion de empresa/ejercicio desde la pregunta llego a **10/13 (76,9 %)**, sin filtro por seccion.

Esto muestra potencial de mejora al formular consultas y usar filtros. No demuestra ese rendimiento en preguntas nuevas ni en el agente completo: las traducciones y reformulaciones son manuales, el golden era conocido y se compararon multiples variantes.

## Comparaciones

Todas las filas usan como maximo cinco fragmentos para el acierto principal, los mismos embeddings y el mismo indice del repositorio. No se altero ninguna ancla.

| Consulta | Backend | Filtros | Aciertos@5 |
| --- | --- | --- | --- |
| Traduccion literal | Denso | Ninguno | 5/13 (38,5 %) |
| Traduccion literal | Denso | Empresa y FY del golden | 6/13 (46,2 %) |
| Traduccion literal | Denso | Empresa, FY e item del golden | 7/13 (53,8 %) |
| Limpieza generica de la traduccion | Denso | Empresa y FY extraidos de la pregunta | 10/13 (76,9 %) |
| Consulta breve de palabras clave | BM25 | Empresa y FY del golden | 11/13 (84,6 %) |
| Consulta breve de palabras clave | BM25 | Empresa, FY e item del golden | 12/13 (92,3 %) |
| Consulta reformulada/expandida | Denso | Empresa, FY e item del golden | 12/13 (92,3 %) |
| Consulta reformulada/expandida | Hibrido RRF | Empresa, FY e item del golden | 10/13 (76,9 %) |
| Tres consultas fusionadas | Hibrido RRF | Empresa, FY e item del golden | 8/13 (61,5 %) |

Los filtros del golden son oraculo. En la alternativa de limpieza generica, se verifico por separado que alias de empresa y regex de ejercicios extraen los filtros correctos en 13/13 preguntas. En comparativas se toma el FY mas reciente. Esto no demuestra recuperar evidencia de ambos ejercicios.

## Que cambia en las consultas

Ejemplo: la pregunta traducida de ingresos de Microsoft se convierte en `total revenue growth drivers` para BM25 o `revenue increased decreased reasons management discussion` para el denso. Las mismas reformulaciones se usan para las preguntas de ingresos de NVDA y GOOGL. No se introducen nombres de segmentos, cifras ni frases de las anclas como pistas.

Empresa y ejercicio se aplican como filtros. No se exige que la similitud semantica los respete por aparecer en el texto de la consulta.

La variante generica elimina palabras de formulacion de preguntas, empresas y ejercicios mediante una lista fija comun a todas las preguntas. No contiene una regla diferente por id. Su traduccion de entrada sigue siendo manual.

## Sensibilidad y limites

- Cambiar las consultas por otra parafrasis razonable dio 9/13 con denso y 7/13 con BM25, usando los mismos filtros completos. Por tanto, **92,3 % es el mejor resultado observado, no una garantia estable**.
- Las dos variantes de 12/13 fallan en `g3-020`, la comparabilidad del BPA de NVIDIA. El ancla cae en posicion 7 con BM25 breve y fuera del top-20 con denso expandido. La traduccion literal densa con filtros si la recuperaba en posicion 1: mejorar el total puede introducir regresiones.
- La alternativa generica de 10/13 falla en `g3-009` (riesgo de proveedores), `g3-012` (competencia/antitrust) y `g3-020` (BPA).
- Los 12 aciertos de las mejores variantes tambien pasan la comprobacion de empresa, FY e item del golden. No se deben a encontrar el ancla en otro ejercicio.
- La seccion 7A de Apple FY2024 tiene solo dos fragmentos. Con el filtro de seccion, su top-5 es trivial.
- Cada pregunta representa 7,7 puntos porcentuales. El conjunto no es un holdout; la seleccion de variantes puede sobreajustarlo.
- Encontrar una frase no certifica la calidad de la respuesta ni resuelve las limitaciones semanticas de algunas anclas del golden.

## Coste y comprobaciones

No hubo llamadas a API ni descargas de modelos. Se uso el modelo BGE ya disponible en la cache local.

Se reprodujeron los 26 rankings de las dos mejores variantes usando directamente `buscar_denso()` y `buscar_bm25()` del proyecto, obteniendo igualdad exacta con el experimento. La alternativa con filtros extraidos del texto reprodujo sus 13 rankings previos.

Con recursos cargados, 39 busquedas por backend y top-5: denso expandido, media 16,75 ms y mediana 12,98 ms; BM25 breve, media 0,48 ms y mediana 0,48 ms. Son tiempos del backend local: **excluyen traduccion, preparacion de consultas, arranque y agente**. No son una comparacion de latencia extremo a extremo con las tablas oficiales.

## Decisiones que quedan

1. Probar traduccion + limpieza generica + filtros extraidos del texto: menor complejidad, resultado observado 10/13. Falta automatizar/medir la traduccion y definir el tratamiento completo de comparativas.
2. Probar reformulacion especifica para busqueda: potencial de 12/13, pero hay que conseguir que el modelo genere consultas igualmente buenas y evaluar su sensibilidad, errores y coste.
3. Elegir denso, BM25 o hibrido segun resultados adicionales. La fusion y el multiquery no mejoraron de forma consistente en este conjunto.
4. Validar una configuracion fijada en preguntas nuevas antes de presentar una mejora generalizable. Conservar los resultados del 05 como referencia.

## Archivos y reproduccion

- `consultas.json`: traducciones, consultas breves y expansiones de la primera fase.
- `protocolo.json`: preguntas, configuracion, versiones y huellas de archivos.
- `resumen.csv`, `detalle.csv`, `rankings.json`: las 36 variantes iniciales.
- `resumen_segunda_fase.csv`, `detalle_segunda_fase.csv`, `rankings_segunda_fase.json`: las 10 variantes adicionales.
- `filtros_desde_pregunta.json`: consultas, filtros y rankings de la alternativa generica.
- `verificacion.json`: igualdad de rankings y medicion de tiempos.

Desde la raiz del repo, con el entorno del proyecto:

```powershell
python -B resultados/experimentos/ingles_20260917/experimento.py
python -B resultados/experimentos/ingles_20260917/comprobaciones.py
python -B resultados/experimentos/ingles_20260917/extraccion_desde_pregunta.py
```

La primera ejecucion fija y guarda las consultas antes de medir. La segunda fase fue disenada tras observar la primera y esta identificada como exploratoria. Los scripts solo escriben en esta carpeta experimental.
