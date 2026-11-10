# Agente de atención al cliente por WhatsApp

Un asistente que responde a tus clientes por WhatsApp, resuelve sus dudas con la información de tu
negocio y **agenda, consulta y cancela citas directamente en tu Google Calendar**.

```
Cliente ──WhatsApp──▶ Meta (Cloud API) ──webhook──▶ este servidor ──▶ Claude (decide y redacta)
                                                         │
                                                         └──▶ Google Calendar (tu calendario)
```

## Qué hace

- Contesta preguntas (precios, horarios, dirección, políticas) usando solo lo que pongas en `business.yaml`.
- Revisa tu calendario real antes de ofrecer horarios: nunca ofrece uno ocupado ni fuera de tu horario.
- Crea la cita en tu calendario con nombre, servicio y WhatsApp del cliente.
- Permite al cliente ver y cancelar **sus propias** citas (para reagendar: cancela y agenda otra).
- Si el cliente pide hablar con una persona o hay una queja, te avisa a tu WhatsApp (`OWNER_WHATSAPP`).
- Recuerda la conversación reciente de cada cliente (últimos 15 intercambios, 72 h).

Por ahora solo entiende mensajes de texto; a audios, fotos, etc. responde pidiendo que escriban.

## Puesta en marcha

Necesitas tres cuentas: Anthropic (Claude), Meta for Developers (WhatsApp) y Google Cloud (Calendar).

### 1. Datos de tu negocio

Edita `business.yaml`: nombre, horario, servicios (con duración y precio), políticas y tono.
El agente no sabe nada que no esté ahí; si le preguntan otra cosa, ofrece pasar con una persona.

### 2. Claude

Crea una API key en <https://platform.claude.com> y ponla en `ANTHROPIC_API_KEY`.

### 3. Google Calendar

1. En <https://console.cloud.google.com> crea un proyecto y habilita **Google Calendar API**.
2. En *IAM y administración → Cuentas de servicio* crea una cuenta de servicio y descarga su clave JSON.
   Guárdala como `service-account.json` en esta carpeta (no se sube a git).
3. En Google Calendar abre *Configuración → tu calendario → Compartir con personas específicas* y
   agrega el correo de la cuenta de servicio (`...@...iam.gserviceaccount.com`) con permiso
   **"Hacer cambios en eventos"**.
4. Pon en `GOOGLE_CALENDAR_ID` el ID del calendario (para el calendario principal es tu correo de Gmail).

Todo lo que ya tengas en ese calendario cuenta como ocupado, así que el agente no encima citas con
tus otros compromisos.

### 4. WhatsApp (Meta Cloud API)

1. En <https://developers.facebook.com> crea una app de tipo *Business* y agrega el producto **WhatsApp**.
2. En *WhatsApp → Configuración de la API* copia el **Phone number ID** → `WHATSAPP_PHONE_NUMBER_ID`.
   (Meta te da un número de prueba; para producción registra tu propio número.)
3. Crea un **token permanente** (Business Settings → Usuarios del sistema → generar token con los
   permisos `whatsapp_business_messaging` y `whatsapp_business_management`) → `WHATSAPP_TOKEN`.
   El token temporal de la consola caduca en 24 h.
4. En *Configuración de la app → Básica* copia el **App Secret** → `WHATSAPP_APP_SECRET`.
5. Inventa un texto cualquiera para `WHATSAPP_VERIFY_TOKEN`.

### 5. Ejecutar

```bash
cp .env.example .env        # y rellena los valores
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

O con Docker:

```bash
docker build -t agente-whatsapp .
docker run -p 8000:8000 --env-file .env \
  -v "$PWD/service-account.json:/srv/service-account.json:ro" -v agente-data:/data agente-whatsapp
```

El servidor debe ser accesible por **HTTPS público**. Para probar en tu computadora sirve un túnel
(`ngrok http 8000` o `cloudflared tunnel --url http://localhost:8000`); para producción, cualquier
hosting que mantenga un proceso corriendo (Railway, Render, Fly.io, un VPS…) con un disco persistente
para `DATABASE_PATH`.

### 6. Conectar el webhook

En Meta: *WhatsApp → Configuración → Webhook*:

- **URL de devolución de llamada**: `https://TU-DOMINIO/webhook`
- **Token de verificación**: el mismo valor de `WHATSAPP_VERIFY_TOKEN`
- Suscríbete al campo **`messages`**.

Escribe al número desde tu WhatsApp y el agente debería responder.

## Cosas que conviene saber

- **Ventana de 24 horas**: WhatsApp solo deja enviar mensajes libres a quien te escribió en las últimas
  24 h. El agente siempre responde dentro de esa ventana. Pero el aviso a `OWNER_WHATSAPP` solo te
  llega si tú le has escrito al número del negocio en las últimas 24 h; si no, queda en los logs del
  servidor. (Para avisos garantizados o recordatorios de cita hace falta una plantilla aprobada por Meta.)
- **Versión de la Graph API**: `WHATSAPP_GRAPH_VERSION` viene en `v23.0`; si Meta la retira, cámbiala
  por la vigente.
- **Costo**: cada mensaje del cliente es una o varias llamadas a Claude. Puedes cambiar el modelo con
  `CLAUDE_MODEL` (por ejemplo `claude-sonnet-5-5` o `claude-haiku-5-5`, más económicos) y el nivel de
  razonamiento con `CLAUDE_EFFORT` (`low` responde más rápido y barato).
- **Privacidad**: las conversaciones se guardan en SQLite (`DATABASE_PATH`) y se envían a la API de
  Claude para generar la respuesta. Inclúyelo en tu aviso de privacidad.
- **Un solo proceso**: el control de duplicados y de horarios simultáneos vive en memoria/SQLite local.
  Ejecuta una sola instancia (un worker).

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```

Las pruebas usan dobles de WhatsApp, Claude y Google Calendar: verifican la lógica de horarios, el
webhook (firma, duplicados) y el flujo de agenda sin llamar a servicios externos.

## Estructura

| Archivo | Qué contiene |
|---|---|
| `business.yaml` | Datos de tu negocio (lo único que normalmente editas) |
| `app/main.py` | Servidor y webhook de WhatsApp |
| `app/agent.py` | Instrucciones del agente, herramientas y ciclo con Claude |
| `app/scheduling.py` | Cálculo de horarios disponibles |
| `app/calendar_service.py` | Google Calendar |
| `app/whatsapp.py` | Envío y lectura de mensajes de WhatsApp |
| `app/store.py` | Historial de conversaciones (SQLite) |
