import hashlib
import hmac

from app.whatsapp import extraer_mensajes, firma_valida, partir


def payload(mensajes, pnid="PN1", field="messages"):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "field": field,
                        "value": {
                            "metadata": {"phone_number_id": pnid},
                            "contacts": [{"wa_id": "5215500000000", "profile": {"name": "Ana"}}],
                            "messages": mensajes,
                        },
                    }
                ]
            }
        ]
    }


def test_extrae_texto_y_nombre():
    m = extraer_mensajes(
        payload([{"id": "wamid.1", "from": "5215500000000", "type": "text", "text": {"body": " Hola "}}]), "PN1"
    )
    assert len(m) == 1 and m[0].texto == "Hola" and m[0].nombre == "Ana" and m[0].telefono == "5215500000000"


def test_no_texto_y_otros_numeros():
    audio = [{"id": "wamid.2", "from": "5215500000000", "type": "audio", "audio": {"id": "x"}}]
    assert extraer_mensajes(payload(audio), "PN1")[0].texto == ""
    assert extraer_mensajes(payload(audio, pnid="OTRO"), "PN1") == []
    # Los webhooks de estado (entregado/leído) no traen "messages"
    assert extraer_mensajes({"entry": [{"changes": [{"field": "messages", "value": {"statuses": [{}]}}]}]}, "PN1") == []


def test_firma():
    cuerpo = b'{"a":1}'
    buena = "sha256=" + hmac.new(b"secreto", cuerpo, hashlib.sha256).hexdigest()
    assert firma_valida("secreto", cuerpo, buena)
    assert not firma_valida("secreto", cuerpo + b" ", buena)
    assert not firma_valida("secreto", cuerpo, None)
    assert not firma_valida("otro", cuerpo, buena)


def test_partir():
    assert partir("hola") == ["hola"]
    trozos = partir(("palabra " * 1200).strip())
    assert len(trozos) > 1 and all(len(t) <= 4000 for t in trozos)
    assert " ".join(trozos) == ("palabra " * 1200).strip()
