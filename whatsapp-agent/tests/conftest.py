from datetime import datetime
from types import SimpleNamespace

import pytest

from app.calendar_service import Cita
from app.config import cargar_negocio
from app.store import Store


@pytest.fixture
def negocio():
    return cargar_negocio("business.yaml")


@pytest.fixture
def store():
    return Store(":memory:")


class CalendarioFalso:
    def __init__(self):
        self.citas: dict[str, tuple[Cita, str]] = {}
        self.bloqueos: list[tuple[datetime, datetime]] = []

    def ocupados(self, desde, hasta):
        todos = self.bloqueos + [(c.inicio, c.fin) for c, _ in self.citas.values()]
        return [(a, b) for a, b in todos if a < hasta and desde < b]

    def crear_cita(self, titulo, descripcion, inicio, fin, telefono):
        cita = Cita(id=f"ev{len(self.citas) + 1}", titulo=titulo, inicio=inicio, fin=fin)
        self.citas[cita.id] = (cita, telefono)
        return cita

    def citas_de(self, telefono, desde):
        return [c for c, t in self.citas.values() if t == telefono and c.fin >= desde]

    def cancelar_cita(self, id_cita, telefono):
        if id_cita in self.citas and self.citas[id_cita][1] == telefono:
            del self.citas[id_cita]
            return True
        return False


@pytest.fixture
def calendario():
    return CalendarioFalso()


def texto(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_, nombre, entrada):
    return SimpleNamespace(type="tool_use", id=id_, name=nombre, input=entrada)


def respuesta(stop_reason, *bloques):
    return SimpleNamespace(stop_reason=stop_reason, content=list(bloques))


class ClaudeFalso:
    """Imita client.beta.messages.create devolviendo respuestas preparadas."""

    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        # Copia superficial: la lista de mensajes se sigue modificando durante el turno.
        self.llamadas.append({**kwargs, "messages": list(kwargs["messages"])})
        return self._respuestas.pop(0)
