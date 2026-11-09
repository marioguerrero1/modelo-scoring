import hashlib
import hmac
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import Estado, app
from app.store import Store

from .test_whatsapp import payload


class WaFalso:
    def __init__(self):
        self.enviados, self.leidos = [], []

    async def enviar_texto(self, tel, texto):
        self.enviados.append((tel, texto))

    async def marcar_leido(self, id_):
        self.leidos.append(id_)

    async def cerrar(self):
        pass


class AgenteFalso:
    def __init__(self):
        self.recibidos = []

    async def responder(self, tel, nombre, texto):
        self.recibidos.append((tel, nombre, texto))
        return f"eco: {texto}"


def cliente():
    settings = SimpleNamespace(whatsapp_verify_token="vt", whatsapp_app_secret="sec", whatsapp_phone_number_id="PN1")
    wa, agente = WaFalso(), AgenteFalso()
    app.state.estado = Estado(settings, wa, agente, Store(":memory:"))
    return TestClient(app), wa, agente


def post(c, cuerpo: dict, secreto="sec"):
    datos = json.dumps(cuerpo).encode()
    firma = "sha256=" + hmac.new(secreto.encode(), datos, hashlib.sha256).hexdigest()
    return c.post("/webhook", content=datos, headers={"X-Hub-Signature-256": firma})


def test_verificacion():
    c, _, _ = cliente()
    with c:
        ok = c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "123"})
        assert ok.status_code == 200 and ok.text == "123"
        assert c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "mal"}).status_code == 403


def test_mensaje_responde_una_sola_vez():
    c, wa, agente = cliente()
    cuerpo = payload([{"id": "wamid.1", "from": "5215500000000", "type": "text", "text": {"body": "Hola"}}])
    with c:
        assert post(c, cuerpo).status_code == 200
        assert post(c, cuerpo).status_code == 200  # reintento de Meta
    assert agente.recibidos == [("5215500000000", "Ana", "Hola")]
    assert wa.enviados == [("5215500000000", "eco: Hola")] and wa.leidos == ["wamid.1"]


def test_firma_invalida_y_audio():
    c, wa, agente = cliente()
    audio = payload([{"id": "wamid.9", "from": "5215500000000", "type": "audio", "audio": {"id": "x"}}])
    with c:
        assert post(c, audio, secreto="otro").status_code == 401
        assert wa.enviados == []
        assert post(c, audio).status_code == 200
    assert agente.recibidos == [] and "solo puedo leer mensajes de texto" in wa.enviados[0][1]
