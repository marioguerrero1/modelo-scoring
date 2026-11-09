from datetime import date, datetime

from app.scheduling import horarios_disponibles, motivo_no_agendable


def dt(negocio, *a):
    return datetime(*a, tzinfo=negocio.tz)


def test_dia_libre_respeta_horario_partido(negocio):
    ahora = dt(negocio, 2026, 11, 9, 8, 0)  # lunes
    libres = horarios_disponibles(negocio, date(2026, 11, 10), 60, [], ahora)
    horas = [f"{h:%H:%M}" for h in libres]
    # 09-14 y 16-19 con citas de 60 min cada 30 min: la última de la mañana empieza 13:00
    assert horas[0] == "09:00" and "13:00" in horas and "13:30" not in horas
    assert "14:00" not in horas and "16:00" in horas and horas[-1] == "18:00"


def test_excluye_ocupados_y_anticipacion(negocio):
    ahora = dt(negocio, 2026, 11, 10, 9, 15)
    ocupado = [(dt(negocio, 2026, 11, 10, 12, 0), dt(negocio, 2026, 11, 10, 13, 0))]
    horas = [f"{h:%H:%M}" for h in horarios_disponibles(negocio, date(2026, 11, 10), 30, ocupado, ahora)]
    # 2 h de anticipación -> nada antes de 11:15
    assert horas[0] == "11:30"
    assert "12:00" not in horas and "12:30" not in horas and "13:00" in horas


def test_domingo_cerrado(negocio):
    ahora = dt(negocio, 2026, 11, 9, 8, 0)
    assert horarios_disponibles(negocio, date(2026, 11, 15), 30, [], ahora) == []


def test_motivos(negocio):
    ahora = dt(negocio, 2026, 11, 9, 8, 0)
    assert motivo_no_agendable(negocio, dt(negocio, 2026, 11, 10, 10, 0), 30, ahora) is None
    assert "fuera del horario" in motivo_no_agendable(negocio, dt(negocio, 2026, 11, 10, 14, 30), 30, ahora)
    assert "fuera del horario" in motivo_no_agendable(negocio, dt(negocio, 2026, 11, 10, 13, 30), 60, ahora)
    assert "anticipación" in motivo_no_agendable(negocio, dt(negocio, 2026, 11, 9, 9, 0), 30, ahora)
    assert "días a futuro" in motivo_no_agendable(negocio, dt(negocio, 2027, 1, 12, 10, 0), 30, ahora)
