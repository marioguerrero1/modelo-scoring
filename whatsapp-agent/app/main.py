"""Servidor web: recibe los webhooks de WhatsApp y responde con el agente."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response

from .agent import MSG_ERROR, Agente
from .calendar_service import GoogleCalendar
from .config import cargar_negocio, cargar_settings
from .store import Store
from .whatsapp import MensajeEntrante, WhatsApp, extraer_mensajes, firma_valida

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("agente")

MSG_SOLO_TEXTO = "Por ahora solo puedo leer mensajes de texto 🙏 ¿Me escribes lo que necesitas?"


class Estado:
    """Dependencias de la app. Los tests lo reemplazan con dobles."""

    def __init__(self, settings, wa, agente: Agente, store: Store):
        self.settings = settings
        self.wa = wa
        self.agente = agente
        self.store = store
        # Un candado por cliente: sus mensajes se atienden en orden, uno a la vez.
        self.candados: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def crear_estado() -> Estado:
    s = cargar_settings()
    if s.faltantes:
        raise SystemExit(f"Faltan variables de entorno: {', '.join(s.faltantes)} (ver .env.example)")
    negocio = cargar_negocio(s.business_config)
    store = Store(s.database_path)
    wa = WhatsApp(s.whatsapp_token, s.whatsapp_phone_number_id, s.whatsapp_graph_version)
    calendario = GoogleCalendar(
        s.google_service_account_file, s.google_calendar_id, negocio.zona_horaria, s.google_service_account_json
    )

    notificar = None
    if s.owner_whatsapp:

        async def notificar(texto: str) -> None:
            await wa.enviar_texto(s.owner_whatsapp, texto)

    agente = Agente(
        negocio, calendario, store, modelo=s.claude_model, esfuerzo=s.claude_effort, notificar_dueno=notificar
    )
    return Estado(s, wa, agente, store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "estado"):
        app.state.estado = crear_estado()
        log.info("Agente listo para %s", app.state.estado.agente.negocio.nombre)
    yield
    await app.state.estado.wa.cerrar()


app = FastAPI(title="Agente de WhatsApp", lifespan=lifespan)


@app.get("/")
async def salud():
    return {"ok": True}


@app.get("/webhook")
async def verificar(request: Request):
    """Verificación inicial del webhook que hace Meta al configurarlo."""
    q = request.query_params
    estado: Estado = request.app.state.estado
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == estado.settings.whatsapp_verify_token:
        return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Token de verificación incorrecto")


@app.post("/webhook")
async def recibir(request: Request, tareas: BackgroundTasks):
    estado: Estado = request.app.state.estado
    cuerpo = await request.body()
    if not firma_valida(estado.settings.whatsapp_app_secret, cuerpo, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="Firma inválida")
    try:
        payload = json.loads(cuerpo)
    except ValueError:
        raise HTTPException(status_code=400, detail="JSON inválido") from None

    for mensaje in extraer_mensajes(payload, estado.settings.whatsapp_phone_number_id):
        # Meta reintenta si tardamos: respondemos 200 de inmediato y evitamos duplicados.
        if estado.store.marcar_procesado(mensaje.id):
            tareas.add_task(atender, estado, mensaje)
    return {"ok": True}


async def atender(estado: Estado, m: MensajeEntrante) -> None:
    async with estado.candados[m.telefono]:
        try:
            await estado.wa.marcar_leido(m.id)
            if not m.texto:
                respuesta = MSG_SOLO_TEXTO
            else:
                respuesta = await estado.agente.responder(m.telefono, m.nombre, m.texto)
            await estado.wa.enviar_texto(m.telefono, respuesta)
        except Exception:
            log.exception("Error atendiendo el mensaje %s de %s", m.id, m.telefono)
            try:
                await estado.wa.enviar_texto(m.telefono, MSG_ERROR)
            except Exception:
                log.exception("Tampoco se pudo enviar el mensaje de error")
