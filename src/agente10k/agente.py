"""Agente baseline: herramientas 10-K, salida estructurada y ejecución trazable."""
from __future__ import annotations

import threading
import contextvars
import threading
import time
import uuid
import re
import os
from typing import Any, Literal

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.callbacks import get_usage_metadata_callback
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field, create_model

from agente10k import config, retrieval
from agente10k import herramientas as modulo_herramientas
from agente10k.herramientas import TOOLS, crear_search_filings


class RespuestaFinanciera(BaseModel):
    """Respuesta trazable a una pregunta sobre los 10-K disponibles."""

    # CONTRATO (enunciado §7): se pueden añadir campos, no quitar ni renombrar estos ocho.
    respuesta: str = Field(description="Respuesta breve y directa, en español.")
    cifra: float | None = Field(default=None, description="Valor XBRL sin escalar; null si no aplica.")
    unidad: str | None = Field(default=None, description="Unidad XBRL, por ejemplo USD o USD/shares.")
    ticker: str | None = Field(default=None, description="Ticker del corpus.")
    ejercicio: int | None = Field(default=None, description="Ejercicio fiscal de cifra.")
    fuente: Literal["xbrl", "texto", "ambas", "ninguna"] = Field(
        description="Origen: XBRL, texto, ambos o ninguna si el dato no está en el corpus.")
    cita: str | None = Field(default=None, description="Frase literal del informe que respalda la respuesta.")
    chunk_id: str | None = Field(default=None, description="Identificador del fragmento citado.")
    # Opcionales: ayudan con comparativas sin modificar el contrato.
    concept_xbrl: str | None = Field(default=None, description="Concepto us-gaap que respalda cifra.")
    ejercicio_base: int | None = Field(default=None, description="Ejercicio previo en una comparativa.")
    cifra_base: float | None = Field(default=None, description="Cifra sin escalar del ejercicio previo.")
    # Solo lo usa el sistema final (observaciones con frases numeradas ⟨n⟩); ver _esquema_respuesta().
    frase_ids: list[int] | None = Field(
        default=None,
        description="Números ⟨n⟩ de las frases visibles de search_filings/read_section que respaldan la "
                    "respuesta (1 o 2). El sistema rellena cita y chunk_id; no copies el texto.")


CAMPOS_SOLO_FINAL = ("frase_ids",)
# Esquema que ve el modelo en baseline, cascada y candidato_07: el contrato original sin campos del final,
# para que su herramienta estructurada siga siendo idéntica a la de los resultados ya congelados.
RespuestaSinFrases = create_model(
    "RespuestaFinanciera", __doc__=RespuestaFinanciera.__doc__,
    **{nombre: (campo.annotation, campo) for nombre, campo in RespuestaFinanciera.model_fields.items()
       if nombre not in CAMPOS_SOLO_FINAL},
)


def _esquema_respuesta(sistema: str) -> type[BaseModel]:
    """El sistema final añade ``frase_ids``; el resto conserva el esquema original."""
    return RespuestaFinanciera if sistema == "final" else RespuestaSinFrases


SYSTEM_PROMPT ="""Eres un analista financiero que responde preguntas sobre informes 10-K de NVDA, MSFT, AAPL, GOOGL, META y AMZN, para FY2024 y FY2025. Usa ÚNICAMENTE las herramientas disponibles.

Universo
- FY es el ejercicio fiscal, no necesariamente el año de presentación. Los items disponibles son 1A (riesgos), 7 (MD&A), 7A (riesgo de mercado) y 8 (estados y notas).

Enrutado
- Toda cifra debe venir de get_xbrl_fact. No copies como cifra un número encontrado en un fragmento.
- Para riesgos, estrategia y explicaciones usa search_filings: consulta en inglés, vocabulario de 10-K y filtros ticker, fiscal_year e item cuando se conozcan.
- Usa read_section solo si search_filings no localiza el pasaje: devuelve mucho más texto.
- Usa list_available únicamente si no sabes si una empresa, ejercicio o sección pertenece al corpus.

Ausencias y comparativas
- Si get_xbrl_fact informa que la empresa no reportó el concepto, o falta empresa/ejercicio, responde fuente="ninguna" y cifra=null. Nunca estimes ni calcules un dato no reportado.
- En comparativas, consulta el mismo concepto para ambos ejercicios. cifra y ejercicio son los más recientes; cifra_base y ejercicio_base, los anteriores. Explica la variación en prosa.

Salida
- Responde breve y en español. cifra conserva exactamente el valor sin escalar y la unidad de get_xbrl_fact; concept_xbrl identifica el concepto.
- fuente es xbrl, texto, ambas o ninguna. Si usas texto, cita debe ser una frase LITERAL de un fragmento leído y chunk_id debe ser el del fragmento.
"""

# Extensión exclusiva del candidato y del sistema final. SYSTEM_PROMPT permanece
# intacto para que el baseline congelado conserve exactamente su configuración.
TRAZABILIDAD_CANDIDATO = """

Trazabilidad obligatoria del candidato
- En preguntas extractivas, responde solo con afirmaciones respaldadas por la evidencia leída. Debes copiar en cita UNA frase literal completa de search_filings o read_section y devolver exactamente el chunk_id que encabeza ese fragmento. No parafrasees, unas ni completes la cita, y no añadas afirmaciones textuales que esa cita no respalde.
- En preguntas comparativas que pidan cifras y una explicación, llama a get_xbrl_fact para ambos ejercicios y a search_filings para la explicación. Devuelve cifra y ejercicio para el año reciente, cifra_base y ejercicio_base para el anterior, fuente="ambas", una frase literal completa que respalde la explicación y su chunk_id exacto.
- Si en cualquier pregunta utilizaste search_filings o read_section como evidencia, fuente no puede ser "xbrl": usa "texto" si no hay XBRL y "ambas" si también lo hay. Completa siempre cita y chunk_id con el mismo fragmento leído.
- Antes de emitir RespuestaFinanciera, comprueba que cita aparece literalmente bajo chunk_id en una observación de herramienta y que todos los campos anteriores están completos cuando corresponda.
- Si get_xbrl_fact indica que un dato no existe, no lo estimes, no lo derives y no lo calcules a partir del texto. Devuelve cifra=null y fuente="ninguna".
"""
SYSTEM_PROMPT_CANDIDATO = SYSTEM_PROMPT + TRAZABILIDAD_CANDIDATO

# Extensión exclusiva del sistema final: sus observaciones numeran las frases (⟨n⟩) y el modelo devuelve
# frase_ids en lugar de copiar texto. No se usa en candidato_07, que no numera nada.
TRAZABILIDAD_FINAL = """

Trazabilidad obligatoria del sistema final
- Las observaciones de search_filings y read_section llevan un número ⟨n⟩ delante de cada frase. Para respaldar una respuesta de texto NO copies frases: devuelve en frase_ids el número de la frase visible que dice lo mismo que tu respuesta (dos números solo si hacen falta dos frases distintas). El sistema completa cita y chunk_id. Elige una frase que afirme lo que respondes, no una que solo trate el mismo tema.
- Responde en una o dos frases que solo reformulen lo que dicen las frases elegidas: un verificador comprueba cada frase de tu respuesta contra la cita y descarta lo que la cita no implique por completo. No añadas causalidad, valoraciones ni resúmenes de otras partes del texto; no nombres la empresa ni el ejercicio si la frase elegida no los contiene (di «la compañía»); conserva los términos de la frase (si dice «driven by X», no lo cambies por «impulsado por la demanda de X»); sin meta-frases ni relato de pasos.
- Una pregunta de cifra se resuelve con una llamada a get_xbrl_fact (una por ejercicio en comparativas), sin search_filings. Usa como máximo 4 llamadas a herramientas en total y no repitas una llamada idéntica.
- En comparativas: pide LAS TRES llamadas en un ÚNICO mensaje (get_xbrl_fact del ejercicio reciente, get_xbrl_fact del anterior y search_filings de la explicación), no una detrás de otra; con sus tres resultados ya puedes responder. Devuelve cifra y ejercicio del año reciente, cifra_base y ejercicio_base del anterior y fuente="ambas". En frase_ids pon la frase que explica la variación y, si existe una frase visible que contiene las cifras de ambos años o su variación, también esa (máximo dos). En la prosa menciona solo cifras que aparezcan en las frases elegidas y, si proceden de una tabla, atribúyelas solo a los años o etiquetas que la propia frase muestre; las cifras de XBRL van en cifra y cifra_base.
- cifra procede solo de get_xbrl_fact. Un número leído en un fragmento va en la prosa, nunca en cifra. Si usaste search_filings o read_section como evidencia, fuente no puede ser "xbrl".
- Si get_xbrl_fact indica que un dato no existe, no lo estimes, no lo derives ni lo calcules a partir del texto: cifra=null, fuente="ninguna" y responde solo que no está reportado.
- Comprobación de universo, solo sobre la empresa y el ejercicio, nunca sobre el concepto: si el ticker o el ejercicio de la pregunta NO aparecen en la lista del apartado Universo, tu PRIMERA llamada debe ser list_available para confirmar que no están en el corpus; con esa confirmación ya respondes cifra=null y fuente="ninguna". Si el ticker y el ejercicio SÍ aparecen en esa lista, no llames a list_available: resuelve la pregunta con get_xbrl_fact aunque sospeches que el concepto no está reportado, porque si un concepto está reportado lo decide get_xbrl_fact y no list_available.
"""
SYSTEM_PROMPT_FINAL = SYSTEM_PROMPT + TRAZABILIDAD_FINAL

FALLBACK = {"respuesta": "No se pudo completar la respuesta.", "fuente": "ninguna"}
NOMBRES_HERRAMIENTAS = {herramienta.name for herramienta in TOOLS}
MAX_REINTENTOS_CASCADA = 2
ESPERA_REINTENTO_S = 0.25


class SistemaFinalNoDisponible(RuntimeError):
    """El sistema final no puede montarse hasta que estén listos sus guardrails."""


def _herramientas_mejoradas() -> list:
    """Conserva el contrato de cuatro tools y sustituye solo el retrieval textual."""
    buscador = crear_search_filings("final")
    return [buscador if herramienta.name == "search_filings" else herramienta for herramienta in TOOLS]


def _prompt_sistema(sistema: str) -> str:
    """Mantiene congelado el prompt baseline y refuerza solo candidato/final."""
    if sistema in {"baseline", "cascada"}:
        return SYSTEM_PROMPT
    if sistema == "candidato_07":
        return SYSTEM_PROMPT_CANDIDATO
    if sistema == "final":
        return SYSTEM_PROMPT_FINAL
    raise ValueError(
        "Sistema desconocido. Usa 'baseline', 'cascada', 'candidato_07' o 'final'."
    )


def _componentes_sistema(sistema: str) -> tuple[list, tuple]:
    """Resuelve herramientas y middleware sin crear clientes ni alterar el baseline."""
    if sistema in {"baseline", "cascada"}:
        return list(TOOLS), ()
    if sistema == "candidato_07":
        return _herramientas_mejoradas(), ()
    if sistema == "final":
        # Importación diferida: el 07 puede funcionar mientras el 06 siga pendiente.
        from agente10k import guardrails

        try:
            middleware = tuple(guardrails.middleware_final())
        except NotImplementedError as exc:
            raise SistemaFinalNoDisponible(
                "El sistema 'final' requiere los guardrails del notebook 06. "
                "Usa 'candidato_07' para evaluar retrieval sin guardrails."
            ) from exc
        if not middleware:
            raise SistemaFinalNoDisponible(
                "El sistema 'final' requiere una pila de guardrails no vacía."
            )
        return _herramientas_mejoradas(), middleware
    raise ValueError(
        "Sistema desconocido. Usa 'baseline', 'cascada', 'candidato_07' o 'final'."
    )


def _configuracion_modelo(
    sistema: str, modelo: str | None = None, fallbacks: tuple[str, ...] | list[str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Devuelve principal y orden de disponibilidad sin mezclarlo con la evaluación."""
    if sistema in {"baseline", "candidato_07", "final"}:
        return modelo or config.MODELO_ID, ()
    if sistema == "cascada":
        orden = (modelo, *fallbacks) if modelo and fallbacks is not None else config.CASCADA_MODELOS
        if modelo:
            orden = (modelo, *(item for item in orden if item != modelo))
        return orden[0], orden[1:]
    raise ValueError(
        "Sistema desconocido. Usa 'baseline', 'cascada', 'candidato_07' o 'final'."
    )


def construir_agente(
    sistema: str = "baseline", *, modelo: str | None = None,
    fallbacks: tuple[str, ...] | list[str] | None = None,
):
    """Monta baseline, candidato, final protegido o cascada de disponibilidad."""
    principal, suplentes = _configuracion_modelo(sistema, modelo, fallbacks)
    herramientas, middleware = _componentes_sistema(sistema)
    return create_agent(
        model=config.crear_modelo(principal, fallbacks=suplentes), tools=herramientas,
        system_prompt=_prompt_sistema(sistema), middleware=middleware,
        response_format=ToolStrategy(schema=_esquema_respuesta(sistema)), checkpointer=InMemorySaver(),
    )


# Un agente por (sistema, modelo, suplentes): el cliente y el grafo se reutilizan entre preguntas. Es seguro
# porque cada pregunta usa su propio thread_id (el InMemorySaver aísla el estado) y los middleware no
# guardan estado propio (lo derivan de los mensajes). La clave incluye el constructor para que un doble
# de prueba no reciba un agente construido con otro.
_CACHE_AGENTES: dict[tuple, Any] = {}
_BLOQUEO_CACHE = threading.Lock()
_CONSTRUCTOR_REAL = construir_agente
_PRECALENTADOS: set[str] = set()
SISTEMAS_RETRIEVAL_MEJORADO = {"candidato_07", "final"}


def limpiar_cache_agentes() -> None:
    """Olvida los agentes construidos (p. ej. tras cambiar la clave o el modelo por entorno)."""
    with _BLOQUEO_CACHE:
        _CACHE_AGENTES.clear()
        _PRECALENTADOS.clear()


def _agente_para(sistema: str, opciones_modelo: dict[str, Any], usar_cache: bool = True):
    """Devuelve el agente del sistema, construyéndolo una sola vez cuando la caché está activa."""
    clave = (sistema, opciones_modelo.get("modelo"), tuple(opciones_modelo.get("fallbacks") or ()),
             construir_agente)
    with _BLOQUEO_CACHE:
        if usar_cache and clave in _CACHE_AGENTES:
            return _CACHE_AGENTES[clave]
        agente = construir_agente(sistema, **opciones_modelo)
        if usar_cache:
            _CACHE_AGENTES[clave] = agente
        # Carga BGE/FAISS/BM25 una vez por proceso, no en cada pregunta. No se hace si el constructor es un
        # doble de prueba (no debe cargar modelos reales) ni para sistemas con retrieval original.
        if (construir_agente is _CONSTRUCTOR_REAL and sistema in SISTEMAS_RETRIEVAL_MEJORADO
                and sistema not in _PRECALENTADOS):
            _PRECALENTADOS.add(sistema)
            precalentar = getattr(retrieval, "precalentar", None)
            if callable(precalentar):
                try:
                    precalentar()
                except Exception:  # no debe tumbar la pregunta: solo pierde el calentamiento
                    pass
        return agente


def _trayectoria(mensajes: list[Any]) -> list[dict[str, Any]]:
    """Extrae llamadas reales, sin deduplicar y sin contar la herramienta sintética."""
    return [
        {"name": llamada["name"], "args": llamada.get("args", {}), "id": llamada.get("id")}
        for mensaje in mensajes if isinstance(mensaje, AIMessage)
        for llamada in (mensaje.tool_calls or []) if llamada.get("name") in NOMBRES_HERRAMIENTAS
    ]


def _uso_en_mensajes(mensajes: list[Any]) -> dict[str, int]:
    """Suma los metadatos de uso que haya adjuntado el proveedor."""
    usos = [getattr(mensaje, "usage_metadata", None) or {} for mensaje in mensajes]
    total = {clave: sum(int(uso.get(clave, 0) or 0) for uso in usos)
             for clave in ("input_tokens", "output_tokens", "total_tokens")}
    return total | {"cache_read": sum(int((uso.get("input_token_details") or {}).get("cache_read", 0) or 0)
                                       for uso in usos)}


def _respuesta_valida(salida: Any) -> RespuestaFinanciera:
    if isinstance(salida, RespuestaFinanciera):
        return salida
    if isinstance(salida, BaseModel):     # p. ej. RespuestaSinFrases (esquema de baseline/candidato)
        return RespuestaFinanciera.model_validate(salida.model_dump())
    if isinstance(salida, dict):
        return RespuestaFinanciera.model_validate(salida)
    return RespuestaFinanciera(**FALLBACK)


def _modelo_real(mensajes: list[Any], solicitado: str) -> str:
    """Lee el id devuelto por el proveedor, o conserva el solicitado si no lo informa."""
    for mensaje in reversed(mensajes):
        if isinstance(mensaje, AIMessage) and isinstance(mensaje.response_metadata, dict):
            metadatos = mensaje.response_metadata
            for clave in ("model_name", "model", "model_id"):
                if metadatos.get(clave):
                    return str(metadatos[clave])
    return solicitado


def _misma_identidad_modelo(izquierda: str, derecha: str) -> bool:
    return izquierda.removeprefix("openrouter:") == derecha.removeprefix("openrouter:")


def _error_recuperable(exc: Exception) -> bool:
    """Identifica fallos transitorios que justifican reintentar la cascada.

    La lista es deliberadamente conservadora: no se reintenta una salida inválida,
    una herramienta mal llamada ni un error de programación. OpenRouter ya prueba
    los modelos alternativos dentro de una llamada; estos reintentos cubren un
    límite temporal o una caída que afecte a toda esa llamada.
    """
    texto = f"{type(exc).__name__}: {exc}".lower()
    indicadores = (
        "429", "rate limit", "rate_limit", "too many requests", "timeout",
        "timed out", "temporarily", "temporary", "service unavailable", "503",
        "502", "504", "connection reset", "connection aborted", "network error",
    )
    return any(indicador in texto for indicador in indicadores)


def _respuesta_acotada(pregunta: str, herramienta: str | None, args: dict[str, Any],
                       evidencia: str, texto_final: str) -> RespuestaFinanciera:
    """Construye el contrato desde una ejecución de herramienta ya trazada."""
    if herramienta == "get_xbrl_fact":
        # El punto final de la frase no forma parte del número («... cifra: 7.46.»); admite negativos.
        numero = re.search(r"Valor sin escalar para el campo cifra: (-?\d+(?:\.\d+)?)", evidencia)
        unidad = re.search(r"= -?[\d,.]+ ([A-Za-z/]+) \(", evidencia)
        return RespuestaFinanciera(
            respuesta=texto_final, cifra=float(numero.group(1)) if numero else None,
            unidad=unidad.group(1) if unidad else None, ticker=args.get("ticker"),
            ejercicio=args.get("fiscal_year"), fuente="xbrl", concept_xbrl=args.get("concept"),
        )
    if herramienta in {"search_filings", "read_section"}:
        chunk = re.search(r"\[([^\]]+)\]", evidencia)
        cita = evidencia.split("\n", 1)[-1].strip() if evidencia else None
        return RespuestaFinanciera(
            respuesta=texto_final, ticker=args.get("ticker"), ejercicio=args.get("fiscal_year"),
            fuente="texto", cita=cita, chunk_id=chunk.group(1) if chunk else None,
        )
    return RespuestaFinanciera(respuesta=texto_final, fuente="ninguna")


def _ejecutar_openrouter_acotado(
    pregunta: str, solicitado: str, suplentes: tuple[str, ...], sistema: str, thread_id: str,
    herramientas: list | None = None, prompt: str | None = None,
) -> dict[str, Any]:
    """Una decisión de herramienta y una respuesta final, sin bucle LangGraph.

    Se conserva el agente (LLM decide herramienta) y la trazabilidad, pero se
    evita el conflicto observado entre ToolStrategy y algunos proveedores gratis.
    """
    inicio = time.perf_counter()
    herramientas = herramientas or list(TOOLS)
    prompt = _prompt_sistema(sistema) if prompt is None else prompt
    nombres_herramientas = {herramienta.name for herramienta in herramientas}
    modelo = config.crear_modelo(solicitado, fallbacks=suplentes).bind_tools(herramientas)
    primero = modelo.invoke([SystemMessage(content=prompt), HumanMessage(content=pregunta)])
    llamadas = [llamada for llamada in (primero.tool_calls or [])
                if llamada.get("name") in nombres_herramientas]
    evidencia = ""
    observaciones: list[dict[str, Any]] = []
    mensajes: list[Any] = [primero]
    if llamadas:
        llamada = llamadas[0]
        herramienta = next(item for item in herramientas if item.name == llamada["name"])
        evidencia = str(herramienta.invoke(llamada.get("args", {})))
        tool_message = ToolMessage(content=evidencia, tool_call_id=llamada["id"], name=llamada["name"])
        mensajes.append(tool_message)
        final = modelo.invoke([SystemMessage(content=prompt), HumanMessage(content=pregunta), primero, tool_message])
        mensajes.append(final)
        if llamada["name"] in {"search_filings", "read_section"}:
            observaciones.append({"name": llamada["name"], "tool_call_id": llamada["id"], "content": evidencia})
        respuesta = _respuesta_acotada(pregunta, llamada["name"], llamada.get("args", {}), evidencia, str(final.content))
    else:
        respuesta = _respuesta_acotada(pregunta, None, {}, "", str(primero.content))
    modelo_real = _modelo_real(mensajes, solicitado)
    orden = (solicitado, *suplentes)
    posicion = next((i for i, item in enumerate(orden, 1) if _misma_identidad_modelo(modelo_real, item)), None)
    costes = [m.response_metadata.get("cost") for m in mensajes if isinstance(m, AIMessage) and isinstance(m.response_metadata, dict)]
    coste = sum(float(x) for x in costes if x is not None) or None
    return {
        "respuesta": respuesta, "error": None, "thread_id": thread_id,
        "intentos": 1, "reintentos": 0, "errores_intentos": [],
        "tool_calls": [{"name": x["name"], "args": x.get("args", {}), "id": x.get("id")} for x in llamadas],
        "n_llamadas": len(llamadas), "llamadas_modelo": sum(isinstance(x, AIMessage) for x in mensajes),
        "uso": {}, "uso_mensajes": _uso_en_mensajes(mensajes), "usd": coste, "usd_openrouter": coste,
        "latencia_s": time.perf_counter() - inicio, "modelo": solicitado, "modelo_solicitado": solicitado,
        "modelo_real": modelo_real, "hubo_fallback": posicion is not None and posicion > 1,
        "posicion_cascada": posicion, "errores_esquema": 0, "observaciones": observaciones,
    }


# Plazo duro por pregunta. Los proveedores gratuitos pueden dejar una petición en cola indefinidamente (OpenRouter
# manda comentarios de keep-alive y el timeout de lectura de httpx no salta): una sola pregunta bloqueó 34 minutos
# una tanda. Al agotarse, se abandona el hilo, se rescata lo que hubiera en el checkpoint y se sigue.
# 300 s y no 150: medido sobre las 7 comparativas, con 150 s se cortaban respuestas que el proveedor
# acababa devolviendo bien (una petición tardó 226 s y respondió HTTP 200). Con 300 s desaparecen los
# plazos agotados y la tanda de 26 preguntas solo cuesta ~2 min más; 420 s no recupera ninguna más.
PLAZO_PREGUNTA_S = float(os.environ.get("AGENTE10K_PLAZO_S", "300"))


class PlazoAgotado(TimeoutError):
    """La pregunta superó el plazo global (AGENTE10K_PLAZO_S)."""


def _invocar_con_plazo(agente, entrada: dict, cfg: dict, plazo: float | None):
    if not plazo or plazo <= 0:
        return agente.invoke(entrada, config=cfg)
    contexto = contextvars.copy_context()          # conserva ContextVars (pregunta actual, callback de uso)
    caja: dict[str, Any] = {}

    def _correr() -> None:
        try:
            caja["resultado"] = contexto.run(agente.invoke, entrada, config=cfg)
        except BaseException as exc:  # noqa: BLE001 - se relanza en el hilo principal
            caja["error"] = exc

    hilo = threading.Thread(target=_correr, name="agente10k-pregunta", daemon=True)
    hilo.start()
    hilo.join(plazo)
    if hilo.is_alive():
        raise PlazoAgotado(f"plazo de {plazo:.0f} s agotado")
    if "error" in caja:
        raise caja["error"]
    return caja["resultado"]


def ejecutar(
    pregunta: str, sistema: str = "baseline", *, modelo: str | None = None,
    fallbacks: tuple[str, ...] | list[str] | None = None, usar_cache: bool = True,
) -> dict:
    """Ejecuta una pregunta en hilo nuevo; devuelve fallback y diagnóstico ante cualquier fallo.

    ``usar_cache`` reutiliza el agente ya construido para ese sistema/modelo. El resultado incluye ``guard``
    (reintentos, degradaciones, reparaciones y causa de los guardrails; vacío si el sistema no los tiene).
    """
    thread_id = f"q-{uuid.uuid4()}"
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}
    solicitado, suplentes = _configuracion_modelo(sistema, modelo, fallbacks)
    if (solicitado.startswith("openrouter:") and os.environ.get("AGENTE10K_MODO_ACOTADO") == "1"
            and sistema != "final"):
        herramientas, _ = _componentes_sistema(sistema)
        errores: list[str] = []
        max_intentos = 1 + MAX_REINTENTOS_CASCADA if sistema == "cascada" else 1
        for intento in range(1, max_intentos + 1):
            try:
                salida = _ejecutar_openrouter_acotado(
                    pregunta, solicitado, suplentes, sistema, thread_id, herramientas,
                    _prompt_sistema(sistema),
                )
                salida.update({"intentos": intento, "reintentos": intento - 1, "errores_intentos": errores})
                return salida
            except Exception as exc:
                fallo = f"{type(exc).__name__}: {exc}"
                errores.append(fallo)
                if intento < max_intentos and _error_recuperable(exc):
                    time.sleep(ESPERA_REINTENTO_S * intento)
                    continue
                return {
                "respuesta": RespuestaFinanciera(**FALLBACK), "error": fallo, "thread_id": thread_id,
                "intentos": intento, "reintentos": intento - 1, "errores_intentos": errores, "tool_calls": [],
                "n_llamadas": 0, "llamadas_modelo": 0, "uso": {}, "uso_mensajes": _uso_en_mensajes([]),
                "usd": None, "usd_openrouter": None, "latencia_s": 0.0, "modelo": solicitado,
                "modelo_solicitado": solicitado, "modelo_real": solicitado, "hubo_fallback": False,
                "posicion_cascada": 1, "errores_esquema": 0, "observaciones": [],
                }
    opciones_modelo = {}
    if modelo is not None:
        opciones_modelo["modelo"] = modelo
    if fallbacks is not None:
        opciones_modelo["fallbacks"] = fallbacks
    agente = _agente_para(sistema, opciones_modelo, usar_cache)
    resultado: dict[str, Any] = {}
    error: str | None = None
    errores_intentos: list[str] = []
    intentos = 0
    # Contrato con herramientas.py: la pregunta viaja en un ContextVar para que search_filings pueda inferir
    # ticker/FY/item cuando el modelo no los pasa. Solo en los sistemas con retrieval mejorado (el baseline
    # congelado no la recibe) y se limpia al terminar para no filtrarla a la pregunta siguiente.
    fijar = getattr(modulo_herramientas, "fijar_pregunta_actual", lambda texto: None)
    fija_pregunta = sistema in SISTEMAS_RETRIEVAL_MEJORADO
    inicio = time.perf_counter()
    # El callback captura uso de todas las vueltas del modelo. Con dobles offline
    # queda vacío, que es preferible a inventar tokens o USD.
    with get_usage_metadata_callback() as callback:
        while True:
            intentos += 1
            try:
                if fija_pregunta:
                    fijar(pregunta)
                resultado = _invocar_con_plazo(
                    agente, {"messages": [{"role": "user", "content": pregunta}]}, cfg, PLAZO_PREGUNTA_S)
                break
            except Exception as exc:  # Error final trazable; no se silencia.
                error_actual = f"{type(exc).__name__}: {exc}"
                errores_intentos.append(error_actual)
                puede_reintentar = (
                    sistema == "cascada" and _error_recuperable(exc)
                    and intentos <= MAX_REINTENTOS_CASCADA
                )
                if puede_reintentar:
                    time.sleep(ESPERA_REINTENTO_S * intentos)
                    continue
                error = error_actual
                try:
                    resultado = getattr(agente.get_state(cfg), "values", None) or {}
                except Exception:
                    resultado = {}
                break
            finally:
                if fija_pregunta:
                    fijar("")
    latencia = time.perf_counter() - inicio
    mensajes = resultado.get("messages", [])
    modelo_real = _modelo_real(mensajes, solicitado)
    orden_cascada = (solicitado, *suplentes)
    posicion_cascada = next((indice for indice, candidato in enumerate(orden_cascada, start=1)
                              if _misma_identidad_modelo(modelo_real, candidato)), None)
    salida = resultado.get("structured_response")
    guard = dict(resultado.get("guard") or {})
    if salida is None and sistema == "final" and mensajes:
        # Excepción del grafo (p. ej. recursion_limit) o cierre sin respuesta: se rescata lo que hay en el
        # estado (último texto del modelo + ledger XBRL) en lugar de devolver el FALLBACK vacío.
        try:
            from agente10k import guardrails

            rescatada, guard_rescate = guardrails.rescatar_respuesta(mensajes)
            salida, guard = rescatada, guard | guard_rescate
        except Exception as exc:
            guard["rescate_fallido"] = f"{type(exc).__name__}: {exc}"
    elif salida is not None and error is not None and sistema == "final" and mensajes:
        # El grafo reventó DESPUÉS de que el modelo respondiera (p. ej. red en la vuelta de reintento): esa
        # structured_response puede ser la que el verificador rechazó. Se verifica ahora, sin otra vuelta.
        try:
            from agente10k import guardrails

            salida, guard_verificado = guardrails.revisar_sin_reintento(mensajes, salida, guard)
            guard = guard | guard_verificado
        except Exception as exc:
            guard["verificacion_fallida"] = f"{type(exc).__name__}: {exc}"
    try:
        respuesta = _respuesta_valida(salida)
    except Exception as exc:
        respuesta = RespuestaFinanciera(**FALLBACK)
        error = error or f"Salida estructurada inválida: {type(exc).__name__}: {exc}"
    if resultado.get("structured_response") is None:
        error = error or "sin structured_response"

    costes = [mensaje.response_metadata.get("cost") for mensaje in mensajes
              if isinstance(mensaje, AIMessage) and isinstance(mensaje.response_metadata, dict)]
    tool_calls = _trayectoria(mensajes)
    uso = {nombre: dict(metadatos) for nombre, metadatos in callback.usage_metadata.items()}
    # El precio fiable en esta fase es el que OpenRouter incluya en el mensaje.
    # La tabla de precios versionada se añadirá con la evaluación; hasta entonces
    # no se estima USD cuando el proveedor no lo ha comunicado.
    coste_proveedor = sum(float(coste) for coste in costes if coste is not None) or None
    return {
        "respuesta": respuesta, "error": error, "thread_id": thread_id,
        "intentos": intentos, "reintentos": intentos - 1,
        "errores_intentos": errores_intentos,
        "tool_calls": tool_calls, "n_llamadas": len(tool_calls),
        "llamadas_modelo": sum(isinstance(mensaje, AIMessage) for mensaje in mensajes),
        "uso": uso, "uso_mensajes": _uso_en_mensajes(mensajes),
        "usd": coste_proveedor, "usd_openrouter": coste_proveedor,
        "latencia_s": latencia, "modelo": solicitado,
        "modelo_solicitado": solicitado, "modelo_real": modelo_real,
        "hubo_fallback": posicion_cascada is not None and posicion_cascada > 1,
        "posicion_cascada": posicion_cascada,
        "errores_esquema": sum(isinstance(mensaje, ToolMessage) and
                                "Failed to parse structured output" in str(mensaje.content)
                                for mensaje in mensajes),
        # Sin marcas ⟨n⟩: el modelo vio las frases numeradas, pero lo que se guarda (y evalúa) es el texto
        # original de la herramienta, para no partir las anclas.
        "observaciones": [
            {"name": mensaje.name, "tool_call_id": mensaje.tool_call_id, "content": _texto_original(mensaje)}
            for mensaje in mensajes if isinstance(mensaje, ToolMessage)
            and mensaje.name in {"search_filings", "read_section"}
        ],
        "guard": guard,
    }


def _texto_original(mensaje: ToolMessage) -> str:
    """Observación tal como la devolvió la herramienta: el original guardado o, si no, sin marcas ⟨n⟩."""
    original = getattr(mensaje, "artifact", None)
    return original if isinstance(original, str) else re.sub(r"⟨\d+⟩ ?", "", str(mensaje.content))


def responder(
    pregunta: str, sistema: str = "baseline", *, modelo: str | None = None,
    fallbacks: tuple[str, ...] | list[str] | None = None,
) -> RespuestaFinanciera:
    """CONTRATO R10: devuelve siempre una ``RespuestaFinanciera`` válida."""
    return ejecutar(pregunta, sistema, modelo=modelo, fallbacks=fallbacks)["respuesta"]
