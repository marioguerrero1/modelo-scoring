"""Cliente de WhatsApp Cloud API (Meta): envío de mensajes y lectura de webhooks."""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)
MAX_LARGO = 4000  # WhatsApp admite 4096 caracteres por mensaje de texto


@dataclass(frozen=True)
class MensajeEntrante:
    id: str
    telefono: str
    nombre: str
    tipo: str
    texto: str  # vacío si no es un mensaje de texto


def firma_valida(app_secret: str, cuerpo: bytes, cabecera: str | None) -> bool:
    """Valida X-Hub-Signature-256 para asegurar que el webhook viene de Meta."""
    if not cabecera or not cabecera.startswith("sha256="):
        return False
    esperada = hmac.new(app_secret.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, cabecera.removeprefix("sha256="))


def extraer_mensajes(payload: dict, phone_number_id: str) -> list[MensajeEntrante]:
    """Saca los mensajes de clientes de un webhook (ignora estados de entrega y otros números)."""
    mensajes: list[MensajeEntrante] = []
    for entry in payload.get("entry", []):
        for cambio in entry.get("changes", []):
            valor = cambio.get("value", {})
            if cambio.get("field") != "messages":
                continue
            if valor.get("metadata", {}).get("phone_number_id") != phone_number_id:
                continue
            nombres = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in valor.get("contacts", [])}
            for m in valor.get("messages", []):
                tipo = m.get("type", "")
                if tipo == "text":
                    texto = m.get("text", {}).get("body", "")
                elif tipo == "button":
                    texto = m.get("button", {}).get("text", "")
                elif tipo == "interactive":
                    inter = m.get("interactive", {})
                    texto = (inter.get("button_reply") or inter.get("list_reply") or {}).get("title", "")
                else:
                    texto = ""
                if not m.get("id") or not m.get("from"):
                    continue
                mensajes.append(
                    MensajeEntrante(
                        id=m["id"],
                        telefono=m["from"],
                        nombre=nombres.get(m["from"], ""),
                        tipo=tipo,
                        texto=texto.strip(),
                    )
                )
    return mensajes


def partir(texto: str, limite: int = MAX_LARGO) -> list[str]:
    """Divide un texto largo en trozos enviables, cortando en saltos de línea cuando se puede."""
    trozos = []
    while len(texto) > limite:
        corte = texto.rfind("\n", 0, limite)
        if corte < limite // 2:
            corte = texto.rfind(" ", 0, limite)
        if corte < limite // 2:
            corte = limite
        trozos.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip()
    if texto:
        trozos.append(texto)
    return trozos


class WhatsApp:
    def __init__(self, token: str, phone_number_id: str, version: str = "v23.0"):
        self._url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        self._http = httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=20)

    async def cerrar(self) -> None:
        await self._http.aclose()

    async def _post(self, cuerpo: dict) -> None:
        r = await self._http.post(self._url, json={"messaging_product": "whatsapp", **cuerpo})
        if r.is_error:
            log.error("WhatsApp respondió %s: %s", r.status_code, r.text[:500])
            r.raise_for_status()

    async def enviar_texto(self, telefono: str, texto: str) -> None:
        for trozo in partir(texto):
            await self._post({"to": telefono, "type": "text", "text": {"body": trozo, "preview_url": False}})

    async def marcar_leido(self, id_mensaje: str) -> None:
        """Doble palomita azul + indicador de 'escribiendo…'. Es cosmético: si falla, seguimos."""
        try:
            await self._post(
                {"status": "read", "message_id": id_mensaje, "typing_indicator": {"type": "text"}}
            )
        except httpx.HTTPError:
            log.warning("No se pudo marcar como leído %s", id_mensaje)
