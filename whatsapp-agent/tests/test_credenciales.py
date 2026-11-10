import base64
import json

import pytest

from app.calendar_service import leer_credenciales

CLAVE = {"type": "service_account", "client_email": "x@y.iam.gserviceaccount.com"}


def test_acepta_json_y_base64():
    crudo = json.dumps(CLAVE)
    assert leer_credenciales(f"  {crudo}\n") == CLAVE
    assert leer_credenciales(base64.b64encode(crudo.encode()).decode()) == CLAVE


@pytest.mark.parametrize("malo", ["no es json", "{roto", '{"type": "authorized_user"}', "[1]"])
def test_rechaza_valores_invalidos(malo):
    with pytest.raises(ValueError, match="GOOGLE_SERVICE_ACCOUNT_JSON"):
        leer_credenciales(malo)
