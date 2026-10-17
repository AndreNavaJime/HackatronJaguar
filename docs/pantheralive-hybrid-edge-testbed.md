# PantheraLIVE híbrido — EDGE + LIVE / prototipo testbed 5G

La implementación permite **dos tipos de prueba** y separa lo que funciona en
un navegador de la operación desatendida en un dispositivo de campo.

## Modo LIVE — transmisión desde cámara de campo (prueba con página abierta)

1. En PantheraLIVE, escoger **LIVE · Cámara remota**.
2. Ingresar la dirección **HTTPS WHEP** de un gateway WebRTC compatible y
   previamente autorizado por el propietario de la cámara. No usar contraseñas
   en la URL. El gateway debe permitir CORS para el origen PantheraLAB y HTTPS.
3. Pulsar **Conectar cámara de campo**. PantheraLAB recibe el video en el
   navegador del investigador mediante WebRTC.
4. Al recibir los primeros fotogramas, se carga automáticamente COCO-SSD Lite,
   que detecta provisionalmente las clases comunes (perro, gato, ave, etc.)
   **en el navegador**; no envía el video a Render para inferencia.
5. Si se detecta posible animal, el navegador inicia MediaRecorder y archiva
   un clip de hasta 19 segundos en **IndexedDB local**, donde el investigador
   puede conservar, reproducir, descargar, eliminar o exportar los metadatos
   reales del clip en JSON. Puede habilitar un aviso del navegador cuando la
   pestaña permanezca abierta, además de los avisos dentro de PantheraLAB.
6. Para probar con Josefina, también existe **EDGE · Cámara de este dispositivo**.
   Al activar la cámara del móvil, el detector se inicia automáticamente;
   deja de ser necesario pulsar el botón de activación del detector por separado.

**Límites:** no funciona con la página cerrada ni con la pantalla apagada.
Si Chrome suspende el video, se detiene la grabación. No hay notificación push
remota desatendida, ni almacenamiento permanente en Render, ni detección de
jaguar/especies silvestres validada. WHEP no es RTSP: una cámara RTSP puede
necesitar una pasarela privada RTSP → WHEP/WebRTC.

## Modo EDGE — captura autónoma en el gateway (requiere hardware)

El script `tools/edge_agent/pantheraedge_capture.py` es un agente externo,
no un proceso que se ejecute en el servidor gratuito de Render. Su entrada es
USB, RTSP o una cámara accesible desde el gateway. Requiere Python y
OpenCV en ese equipo:

```bash
python -m pip install opencv-python-headless

# Preparar un detector local en 127.0.0.1:8000 que tenga habilitado
# MegaDetector y responda POST /api/live/wildlife-frame.
python tools/edge_agent/pantheraedge_capture.py \
  --source 0 \
  --camera-id CT_TESTBED_01 \
  --study-id ESTUDIO_TEST \
  --output ./clips_privados
```

**Advertencia:** una instalación estándar del backend gratuito de Render
NO tiene MegaDetector activado. El agente requiere un detector real instalado
en el gateway o en una máquina dentro de la misma red segura a la que se
accede por `localhost` mediante un proxy local protegido. Si el detector
responde error, el agente **no convierte movimiento de hojas/lluvia en eventos
de fauna**. No incluye una detección alternativa falsa.

El gateway hace lo siguiente:

- lee continuamente fotogramas (por defecto, 8 muestras de video/s);
- guarda los últimos 3 s de video en RAM como pre-roll;
- consulta el detector **local** cada 1,5 s (sin subir fotogramas a Render);
- graba automáticamente solo si se detecta un posible animal y no una persona;
- corta el evento después de 5 s sin nuevas detecciones o a los 24 s,
  descartando clips que contengan una detección de persona;
- guarda MP4 **local** y un JSON lado a lado con hora UTC, código de cámara,
  clase preliminar, puntuación, tamaño, duración y estado «pendiente»;
- funciona sin navegador abierto, sujeto a que el equipo de campo, cámara y
  modelo estén encendidos y operativos.

El formato MP4 usa el codec básico `mp4v` de OpenCV: podría requerir
transcodificación H.264/WebM para reproducirse en algunos navegadores. No
subir automáticamente a un alojamiento público.

**Operación de campo:** el agente necesita supervisión (systemd u otra),
espacio suficiente y retención. Por defecto no borra evidencia sin autorización;
no cifra automáticamente el disco. Se recomienda disco cifrado, cuenta del
sistema restringida, revisión de los permisos de directorios y sistema
de respaldos antes de grabar imágenes sensibles. No almacenar RTSP con claves
en comandos compartidos, repositorios o registros públicos.

## Integración que aún no está activada

Para una auténtica operación multiinstitucional, con un investigador
recibiendo notificaciones desde otra ubicación **sin tener abierta la app**,
faltan componentes con acceso seguro:

1. cuenta de cámara/gateway o credencial de servicio rotatoria, nunca escrita
   en el frontend;
2. ingesta autentificada de JSON de eventos con IDs únicos y tiempos UTC,
   control de repetición, colas offline y confirmación de recepción;
3. almacenamiento privado persistente de videos con políticas por
   organización/estudio, retención y auditoría de revisión;
4. notificaciones push/correo a científicos autorizados con control de
   suscripción, sin revelar localizaciones sensibles;
5. conexión de clips conservados a las capturas de PantheraMONITORING y
   a los informes científicos, con procedencia y revisión humana;
6. detector de fauna silvestre evaluado científicamente (COCO-SSD no sirve
   para afirmar «jaguar» ni para reidentificación por rosetas).

El plan gratuito de Render es adecuado para servir la interfaz/API de
prueba, **no** como plataforma de almacenamiento persistente de clips o
inferencia neuronal y recepción de streams simultáneos 24/7. Estas conexiones
solo deben activarse cuando haya credenciales y servicios autorizados.

## Ensayos testbed 5G medibles

Los clips descargados incluyen eventos JSON (`panthera-live-clip-v1`) con
`clip_bytes`, `duration_ms`, `source`, `camera_id` y
`network_measurement: false`: **son mediciones de archivo, no latencia ni
ancho de banda real**. Para comparar 5G frente a 4G/Wi-Fi se debe medir:

- marca temporal de detección en el EDGE y de recepción confirmada por cloud;
- tamaño/bytes transmitidos de video completo frente a clips filtrados;
- pérdidas, repeticiones de eventos y latencia extremo a extremo;
- consumo energético y continuidad durante desconexiones;
- falsos positivos/falsos negativos evaluados con imágenes etiquetadas.

No atribuir ventajas medidas de 5G a cifras simuladas del panel anterior.

**PantheraFIRE sigue en el último módulo y fuera de este flujo.**
