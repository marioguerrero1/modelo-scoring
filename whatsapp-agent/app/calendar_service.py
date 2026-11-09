"""Google Calendar mediante una cuenta de servicio.

El dueño comparte su calendario con el correo de la cuenta de servicio
("Hacer cambios en eventos") y las citas aparecen directamente en él.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

SCOPES = ["https://www.googleapis.com/auth/calendar"]
# Propiedad privada con la que marcamos de qué número de WhatsApp es cada cita.
PROP_TELEFONO = "wa_phone"


@dataclass(frozen=True)
class Cita:
    id: str
    titulo: str
    inicio: datetime
    fin: datetime


class Calendario(Protocol):
    def ocupados(self, desde: datetime, hasta: datetime) -> list[tuple[datetime, datetime]]: ...
    def crear_cita(self, titulo: str, descripcion: str, inicio: datetime, fin: datetime, telefono: str) -> Cita: ...
    def citas_de(self, telefono: str, desde: datetime) -> list[Cita]: ...
    def cancelar_cita(self, id_cita: str, telefono: str) -> bool: ...


class GoogleCalendar:
    def __init__(self, archivo_credenciales: str, calendar_id: str, zona_horaria: str):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(archivo_credenciales, scopes=SCOPES)
        self._svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
        self._cal = calendar_id
        self._tz = zona_horaria

    def ocupados(self, desde: datetime, hasta: datetime) -> list[tuple[datetime, datetime]]:
        cuerpo = {
            "timeMin": desde.isoformat(),
            "timeMax": hasta.isoformat(),
            "timeZone": self._tz,
            "items": [{"id": self._cal}],
        }
        resp = self._svc.freebusy().query(body=cuerpo).execute()
        cal = resp["calendars"][self._cal]
        if cal.get("errors"):
            raise RuntimeError(f"Google Calendar no pudo leer el calendario: {cal['errors']}")
        return [(datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])) for b in cal.get("busy", [])]

    def crear_cita(self, titulo: str, descripcion: str, inicio: datetime, fin: datetime, telefono: str) -> Cita:
        evento = {
            "summary": titulo,
            "description": descripcion,
            "start": {"dateTime": inicio.isoformat(), "timeZone": self._tz},
            "end": {"dateTime": fin.isoformat(), "timeZone": self._tz},
            "extendedProperties": {"private": {PROP_TELEFONO: telefono}},
        }
        creado = self._svc.events().insert(calendarId=self._cal, body=evento).execute()
        return Cita(id=creado["id"], titulo=titulo, inicio=inicio, fin=fin)

    def citas_de(self, telefono: str, desde: datetime) -> list[Cita]:
        resp = (
            self._svc.events()
            .list(
                calendarId=self._cal,
                timeMin=desde.isoformat(),
                privateExtendedProperty=f"{PROP_TELEFONO}={telefono}",
                singleEvents=True,
                orderBy="startTime",
                maxResults=20,
            )
            .execute()
        )
        citas = []
        for e in resp.get("items", []):
            if "dateTime" not in e.get("start", {}):
                continue
            citas.append(
                Cita(
                    id=e["id"],
                    titulo=e.get("summary", "Cita"),
                    inicio=datetime.fromisoformat(e["start"]["dateTime"]),
                    fin=datetime.fromisoformat(e["end"]["dateTime"]),
                )
            )
        return citas

    def cancelar_cita(self, id_cita: str, telefono: str) -> bool:
        """Borra la cita solo si pertenece a ese teléfono. False si no existe o no es suya."""
        from googleapiclient.errors import HttpError

        try:
            evento = self._svc.events().get(calendarId=self._cal, eventId=id_cita).execute()
        except HttpError as e:
            if e.resp.status in (404, 410):
                return False
            raise
        dueno = evento.get("extendedProperties", {}).get("private", {}).get(PROP_TELEFONO)
        if dueno != telefono or evento.get("status") == "cancelled":
            return False
        self._svc.events().delete(calendarId=self._cal, eventId=id_cita).execute()
        return True
