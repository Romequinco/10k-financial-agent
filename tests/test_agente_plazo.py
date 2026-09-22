"""Plazo duro por pregunta: una petición colgada del proveedor no debe bloquear la tanda."""
import contextvars
import time

import pytest

from agente10k import agente

VARIABLE = contextvars.ContextVar("prueba_plazo", default="vacia")


class Lento:
    def invoke(self, entrada, config=None):
        time.sleep(3)
        return {"messages": []}


class Rapido:
    def invoke(self, entrada, config=None):
        return {"messages": [], "eco": entrada["q"], "contexto": VARIABLE.get()}


class Roto:
    def invoke(self, entrada, config=None):
        raise ValueError("fallo del proveedor")


def test_plazo_agotado_lanza_y_no_espera_a_la_llamada():
    inicio = time.perf_counter()
    with pytest.raises(agente.PlazoAgotado):
        agente._invocar_con_plazo(Lento(), {"q": 1}, {}, 0.2)
    assert time.perf_counter() - inicio < 1.5


def test_resultado_normal_y_contexto_visible_en_el_hilo():
    VARIABLE.set("pregunta-en-curso")
    salida = agente._invocar_con_plazo(Rapido(), {"q": "hola"}, {}, 5)
    assert salida["eco"] == "hola" and salida["contexto"] == "pregunta-en-curso"


def test_los_errores_del_agente_se_propagan_tal_cual():
    with pytest.raises(ValueError, match="fallo del proveedor"):
        agente._invocar_con_plazo(Roto(), {}, {}, 5)


def test_plazo_cero_o_none_invoca_directamente():
    assert agente._invocar_con_plazo(Rapido(), {"q": "x"}, {}, 0)["eco"] == "x"
    assert agente._invocar_con_plazo(Rapido(), {"q": "y"}, {}, None)["eco"] == "y"
