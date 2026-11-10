"""Configuración: variables de entorno y datos del negocio (business.yaml)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


@dataclass(frozen=True)
class Servicio:
    nombre: str
    duracion_min: int
    precio: str = ""
    descripcion: str = ""


@dataclass(frozen=True)
class Negocio:
    nombre: str
    zona_horaria: str
    servicios: list[Servicio]
    # horario[0] = lunes ... horario[6] = domingo; cada día es una lista de (apertura, cierre)
    horario: list[list[tuple[time, time]]]
    descripcion: str = ""
    direccion: str = ""
    telefono_contacto: str = ""
    info_adicional: str = ""
    estilo: str = "Amable y breve."
    intervalo_min: int = 30
    anticipacion_min_horas: float = 2
    max_dias_adelante: int = 30

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.zona_horaria)

    def servicio(self, nombre: str) -> Servicio | None:
        buscado = nombre.strip().casefold()
        for s in self.servicios:
            if s.nombre.casefold() == buscado:
                return s
        return None


def _hora(texto: str) -> time:
    h, m = str(texto).split(":")
    return time(int(h), int(m))


def cargar_negocio(ruta: str | Path) -> Negocio:
    datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
    horario_raw = datos.get("horario") or {}
    desconocidos = set(horario_raw) - set(DIAS)
    if desconocidos:
        raise ValueError(f"Días no reconocidos en 'horario': {sorted(desconocidos)} (usa {DIAS})")
    horario = []
    for dia in DIAS:
        tramos = [(_hora(a), _hora(b)) for a, b in (horario_raw.get(dia) or [])]
        for a, b in tramos:
            if a >= b:
                raise ValueError(f"Horario inválido el {dia}: {a} debe ser antes de {b}")
        horario.append(sorted(tramos))
    servicios = [Servicio(**s) for s in datos.get("servicios") or []]
    if not servicios:
        raise ValueError("business.yaml debe definir al menos un servicio")
    citas = datos.get("citas") or {}
    negocio = Negocio(
        nombre=datos["nombre"],
        zona_horaria=datos["zona_horaria"],
        servicios=servicios,
        horario=horario,
        descripcion=datos.get("descripcion", ""),
        direccion=datos.get("direccion", ""),
        telefono_contacto=datos.get("telefono_contacto", ""),
        info_adicional=datos.get("info_adicional", ""),
        estilo=datos.get("estilo", "Amable y breve."),
        intervalo_min=int(citas.get("intervalo_min", 30)),
        anticipacion_min_horas=float(citas.get("anticipacion_min_horas", 2)),
        max_dias_adelante=int(citas.get("max_dias_adelante", 30)),
    )
    negocio.tz  # valida la zona horaria al arrancar
    return negocio


@dataclass(frozen=True)
class Settings:
    whatsapp_token: str
    whatsapp_phone_number_id: str
    whatsapp_verify_token: str
    whatsapp_app_secret: str
    google_calendar_id: str
    google_service_account_file: str = "service-account.json"
    google_service_account_json: str = ""
    whatsapp_graph_version: str = "v23.0"
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "medium"
    business_config: str = "business.yaml"
    owner_whatsapp: str = ""
    database_path: str = "data/agent.db"
    faltantes: list[str] = field(default_factory=list)


def cargar_env_file(ruta: str = ".env") -> None:
    """Carga un .env sencillo (CLAVE=valor) sin pisar variables ya definidas."""
    p = Path(ruta)
    if not p.exists():
        return
    for linea in p.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valor = valor.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(clave.strip(), valor)


def cargar_settings() -> Settings:
    cargar_env_file()
    env = os.environ.get
    requeridas = {
        "WHATSAPP_TOKEN": env("WHATSAPP_TOKEN", ""),
        "WHATSAPP_PHONE_NUMBER_ID": env("WHATSAPP_PHONE_NUMBER_ID", ""),
        "WHATSAPP_VERIFY_TOKEN": env("WHATSAPP_VERIFY_TOKEN", ""),
        "WHATSAPP_APP_SECRET": env("WHATSAPP_APP_SECRET", ""),
        "GOOGLE_CALENDAR_ID": env("GOOGLE_CALENDAR_ID", ""),
    }
    return Settings(
        whatsapp_token=requeridas["WHATSAPP_TOKEN"],
        whatsapp_phone_number_id=requeridas["WHATSAPP_PHONE_NUMBER_ID"],
        whatsapp_verify_token=requeridas["WHATSAPP_VERIFY_TOKEN"],
        whatsapp_app_secret=requeridas["WHATSAPP_APP_SECRET"],
        google_calendar_id=requeridas["GOOGLE_CALENDAR_ID"],
        google_service_account_file=env("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account.json"),
        google_service_account_json=env("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
        whatsapp_graph_version=env("WHATSAPP_GRAPH_VERSION", "v23.0"),
        claude_model=env("CLAUDE_MODEL", "claude-opus-5-5"),
        claude_effort=env("CLAUDE_EFFORT", "medium"),
        business_config=env("BUSINESS_CONFIG", "business.yaml"),
        owner_whatsapp=env("OWNER_WHATSAPP", ""),
        database_path=env("DATABASE_PATH", "data/agent.db"),
        faltantes=[k for k, v in requeridas.items() if not v],
    )
