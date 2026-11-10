import asyncio
from datetime import datetime

from app.agent import MSG_NO_PUEDO, TOOLS, Agente, construir_system

from .conftest import ClaudeFalso, respuesta, texto, tool_use

TEL = "5215500000000"


def crear(negocio, calendario, store, respuestas, **kw):
    claude = ClaudeFalso(respuestas)
    ahora = datetime(2026, 11, 9, 8, 0, tzinfo=negocio.tz)  # lunes
    agente = Agente(negocio, calendario, store, cliente=claude, reloj=lambda: ahora, **kw)
    return agente, claude


def test_flujo_completo_agenda_cita(negocio, calendario, store):
    agente, claude = crear(
        negocio,
        calendario,
        store,
        [
            respuesta("tool_use", tool_use("t1", "consultar_disponibilidad", {"fecha": "2026-11-10", "servicio": "Consulta"})),
            respuesta(
                "tool_use",
                tool_use("t2", "agendar_cita", {"servicio": "consulta", "inicio": "2026-11-10T10:00", "nombre_cliente": "Ana", "notas": ""}),
            ),
            respuesta("end_turn", texto("Listo, Ana. Te espero el martes 10 a las 10:00.")),
        ],
    )
    salida = asyncio.run(agente.responder(TEL, "Ana", "Quiero una consulta mañana a las 10"))
    assert "martes 10" in salida

    # Se creó el evento con la duración del servicio y ligado al teléfono
    (cita, tel), = calendario.citas.values()
    assert tel == TEL and cita.titulo == "Consulta — Ana"
    assert (cita.inicio.hour, cita.fin.hour, cita.fin.minute) == (10, 10, 30)

    # El resultado de la primera herramienta llegó al modelo con los huecos
    resultado = claude.llamadas[1]["messages"][-1]["content"][0]
    assert resultado["tool_use_id"] == "t1" and "09:00" in resultado["content"] and not resultado["is_error"]

    # El historial guarda solo texto y se reenvía en el siguiente turno
    assert store.historial(TEL) == [("Quiero una consulta mañana a las 10", salida)]


def test_parametros_de_la_peticion(negocio, calendario, store):
    agente, claude = crear(negocio, calendario, store, [respuesta("end_turn", texto("Hola"))])
    store.guardar_turno(TEL, "hola", "¡Hola! ¿En qué te ayudo?")
    asyncio.run(agente.responder(TEL, "Ana", "¿Cuánto cuesta?"))
    k = claude.llamadas[0]
    assert k["model"] == "claude-opus-5-5" and k["fallbacks"] == "default"
    assert k["thinking"] == {"type": "adaptive"} and k["output_config"] == {"effort": "medium"}
    assert [m["role"] for m in k["messages"]] == ["user", "assistant", "user"]
    assert "lunes 9 de noviembre" in k["system"][1]["text"] and TEL in k["system"][1]["text"]
    assert "$500 MXN" in k["system"][0]["text"] and "domingo: cerrado" in k["system"][0]["text"]
    assert all(t["strict"] and t["input_schema"]["additionalProperties"] is False for t in TOOLS)


def test_no_agenda_horario_ocupado_ni_fuera_de_horario(negocio, calendario, store):
    tz = negocio.tz
    calendario.bloqueos.append((datetime(2026, 11, 10, 10, 0, tzinfo=tz), datetime(2026, 11, 10, 11, 0, tzinfo=tz)))
    agente, _ = crear(negocio, calendario, store, [])
    base = {"servicio": "Consulta", "nombre_cliente": "Ana", "notas": ""}
    r, err = asyncio.run(agente._ejecutar(TEL, "agendar_cita", {**base, "inicio": "2026-11-10T10:30"}))
    assert err and "ya no está disponible" in r
    r, err = asyncio.run(agente._ejecutar(TEL, "agendar_cita", {**base, "inicio": "2026-11-15T10:00"}))
    assert err and "fuera del horario" in r
    r, err = asyncio.run(agente._ejecutar(TEL, "agendar_cita", {**base, "servicio": "Masaje", "inicio": "2026-11-10T12:00"}))
    assert err and "Consulta, Asesoría" in r
    assert calendario.citas == {}


def test_dos_clientes_no_toman_el_mismo_horario(negocio, calendario, store):
    agente, _ = crear(negocio, calendario, store, [])
    args = {"servicio": "Consulta", "inicio": "2026-11-10T12:00", "nombre_cliente": "X", "notas": ""}

    async def carrera():
        return await asyncio.gather(
            agente._ejecutar("111", "agendar_cita", args), agente._ejecutar("222", "agendar_cita", args)
        )

    resultados = asyncio.run(carrera())
    assert sorted(err for _, err in resultados) == [False, True]
    assert len(calendario.citas) == 1


def test_listar_y_cancelar_solo_las_propias(negocio, calendario, store):
    agente, _ = crear(negocio, calendario, store, [])
    args = {"servicio": "Consulta", "inicio": "2026-11-10T12:00", "nombre_cliente": "Ana", "notas": "primera vez"}
    asyncio.run(agente._ejecutar(TEL, "agendar_cita", args))
    lista, _ = asyncio.run(agente._ejecutar(TEL, "listar_mis_citas", {}))
    assert "id ev1" in lista and "martes 10 de noviembre, 12:00" in lista
    assert "no tiene citas" in asyncio.run(agente._ejecutar("999", "listar_mis_citas", {}))[0]
    assert asyncio.run(agente._ejecutar("999", "cancelar_cita", {"id_cita": "ev1"}))[1] is True
    assert asyncio.run(agente._ejecutar(TEL, "cancelar_cita", {"id_cita": "ev1"})) == ("Cita cancelada.", False)
    assert calendario.citas == {}


def test_solicitar_humano_avisa_al_dueno(negocio, calendario, store):
    avisos = []

    async def notificar(t):
        avisos.append(t)

    agente, _ = crear(negocio, calendario, store, [], notificar_dueno=notificar)
    r, err = asyncio.run(agente._ejecutar(TEL, "solicitar_humano", {"motivo": "Queja por cobro"}))
    assert not err and "Se avisó" in r and "Queja por cobro" in avisos[0] and TEL in avisos[0]


def test_refusal_no_se_guarda_como_error(negocio, calendario, store):
    agente, _ = crear(negocio, calendario, store, [respuesta("refusal")])
    assert asyncio.run(agente.responder(TEL, "", "…")) == MSG_NO_PUEDO


def test_system_estable(negocio):
    assert construir_system(negocio) == construir_system(negocio)
