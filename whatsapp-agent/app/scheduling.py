"""Cálculo de horarios disponibles. Lógica pura (sin red) para que sea fácil de probar.

El modelo nunca hace aritmética de fechas: pide los huecos a estas funciones.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .config import Negocio

Intervalo = tuple[datetime, datetime]


def se_traslapan(a_inicio: datetime, a_fin: datetime, b_inicio: datetime, b_fin: datetime) -> bool:
    return a_inicio < b_fin and b_inicio < a_fin


def dentro_de_horario(negocio: Negocio, inicio: datetime, fin: datetime) -> bool:
    """True si [inicio, fin] cae completo dentro de un tramo del horario de ese día."""
    if inicio.date() != fin.date():
        return False
    for abre, cierra in negocio.horario[inicio.weekday()]:
        if abre <= inicio.time() and fin.time() <= cierra:
            return True
    return False


def motivo_no_agendable(negocio: Negocio, inicio: datetime, duracion_min: int, ahora: datetime) -> str | None:
    """Devuelve por qué no se puede agendar en `inicio`, o None si las reglas lo permiten.

    No revisa el calendario; solo horario del negocio, anticipación y ventana máxima.
    """
    fin = inicio + timedelta(minutes=duracion_min)
    if inicio < ahora + timedelta(hours=negocio.anticipacion_min_horas):
        return (
            "Ese horario ya pasó o está demasiado próximo "
            f"(se requiere al menos {negocio.anticipacion_min_horas:g} h de anticipación)."
        )
    if inicio.date() > ahora.date() + timedelta(days=negocio.max_dias_adelante):
        return f"Solo se puede agendar hasta {negocio.max_dias_adelante} días a futuro."
    if not dentro_de_horario(negocio, inicio, fin):
        return "Ese horario está fuera del horario de atención."
    return None


def horarios_disponibles(
    negocio: Negocio,
    dia: date,
    duracion_min: int,
    ocupados: list[Intervalo],
    ahora: datetime,
) -> list[datetime]:
    """Inicios posibles para una cita de `duracion_min` en `dia`, respetando lo ocupado."""
    tz = negocio.tz
    paso = timedelta(minutes=negocio.intervalo_min)
    duracion = timedelta(minutes=duracion_min)
    libres: list[datetime] = []
    for abre, cierra in negocio.horario[dia.weekday()]:
        inicio = datetime.combine(dia, abre, tzinfo=tz)
        limite = datetime.combine(dia, cierra, tzinfo=tz)
        while inicio + duracion <= limite:
            fin = inicio + duracion
            if motivo_no_agendable(negocio, inicio, duracion_min, ahora) is None and not any(
                se_traslapan(inicio, fin, o_ini, o_fin) for o_ini, o_fin in ocupados
            ):
                libres.append(inicio)
            inicio += paso
    return libres
