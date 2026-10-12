# PantheraEDGE ↔ VIGÍA: contrato de integración (prototipo)

Origen: `vigia.zip` compartido por el equipo (sketch ESP32, botón PIR, microSD y subida multipart). Wokwi: https://wokwi.com/projects/477095065944902657

## Responsabilidades

- **VIGÍA / nodo de Manuel**: simula la cámara Browning, SD, sensor PIR y subida de capturas por Wi-Fi.
- **PantheraEDGE**: recibe eventos autenticados y muestra el estado del enlace. Una pasarela celular/5G es una integración FUTURA; el sketch no mide ni utiliza 5G.
- **PantheraID**: ejecuta MegaDetector cuando un investigador sube imágenes/videos válidos. No se ejecuta automáticamente durante la ingesta VIGÍA.
- **Investigación**: metadatos, validación científica y contexto Sentinel. **PantheraMONITORING**: panel de registros de la sesión.

## Contrato de recepción

Endpoint: `POST /api/edge/vigia/capture` por **HTTPS**, con encabezado `X-Panthera-Node-Token`. Los campos multipart reproducen el sketch existente:

| Campo | Tipo | Uso |
|---|---|---|
| `cam_id` | texto | identificador de cámara |
| `trigger` | texto | por ejemplo `pir` |
| `ts` | texto ISO 8601 | hora DECLARADA por el nodo |
| `lat`, `lon` | números WGS84 | ubicación DECLARADA de la cámara; no del animal |
| `frames` | archivo JPG (máx. 12 MiB) | fotografía recibida solo en memoria |

Respuesta HTTP 200: `accepted`, `event_id`, `duplicate`, `saved:false`, `analyzed:false`.

Los eventos se deduplican por cámara+nombre+hash y guardan en memoria del proceso (últimos 20), sin imagen. **Una respuesta 200 no prueba decodificación de la fotografía, ni detección de fauna, ni tránsito 5G.** El JPG de ejemplo del botón Wokwi es artificial y NO equivale a una fotografía válida para MegaDetector.

## Configuración segura del operador

1. Definir en el entorno Python `PANTHERA_VIGIA_INGEST_TOKEN` (clave fuerte para el ESP32 / pasarela). Sin esta clave, la recepción responde HTTP 503.
2. Definir otra clave diferente `PANTHERA_VIGIA_DASHBOARD_TOKEN` para permitir consultar datos de campo desde la interfaz. No distribuir la clave del nodo a los investigadores.
3. Mantener Codespaces/puertos privados; si se expone un servicio público, debe ser una instancia protegida con HTTPS y controles de red. No publicar la ubicación de cámaras sensibles.
4. En VIGÍA, reemplazar el host provisional `edge.example.com`, el puerto 80 y la ruta `/capture` por la dirección HTTPS de `/api/edge/vigia/capture` y añadir el encabezado `X-Panthera-Node-Token`. Esto requiere cambiar su cliente HTTP; NO basta con cambiar la constante del host.
5. Para revisar la última captura, el panel usa `GET /api/edge/vigia/status` (sin metadatos sensibles) y `GET /api/edge/vigia/latest` con `X-Panthera-Dashboard-Token` (clave escrita en la sesión actual de la interfaz; no se guarda en almacenamiento del navegador).

También existe el puente anterior `GET /api/edge/bridge`, configurado mediante `PANTHERA_EDGE_BRIDGE_URL`, para consumir un evento JSON remoto firmado con HMAC. Es un mecanismo **distinto** de la subida multipart de VIGÍA.

## Pendientes antes de producción

- Obtener de Manuel el endpoint operativo, forma de autenticación y confirmación de que puede modificar el sketch o configurar un gateway.
- Validar fotografías JPEG reales, cola de procesamiento, almacenamiento cifrado/autorizado, política de retención y vínculo verificable con PantheraID.
- Conectar eventos validados a PantheraMONITORING (actualmente solo registros en memoria de la sesión del navegador).
- Medir o integrar de verdad el enlace 5G/4G; los valores de 5G de la app son solo estimaciones configurables.
- Probar recepción real desde Wokwi/ESP32 y efectos de desconexión, tiempos de espera y reintentos.
