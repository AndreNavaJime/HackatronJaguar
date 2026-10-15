# PantheraSENSE — integración en pruebas (no desplegada)

**Prototipo independiente de Andrea Navarro Jiménez.** Esta rama agrega un receptor de datos **simulados** del ESP32 Wokwi y un panel de consulta en PantheraEDGE. No modifica el trabajo de Manuel ni cambia `pantheraid-v2` en producción.

## Arquitectura

`Wokwi ESP32 + DHT22 → HTTPS POST /api/sense/ingest → FastAPI (Render) → GET /api/sense/latest → PantheraEDGE (Vercel)`

- `POST /api/sense/ingest`: requiere `X-PantheraSense-Key`, aceptará **únicamente** `simulation:true` y el esquema de datos de PantheraSENSE.
- `GET /api/sense/latest`: consulta de solo lectura que muestra únicamente datos virtuales no sensibles. Se refresca automáticamente cada 15 segundos.
- Almacena como máximo 30 mediciones **en memoria de un solo proceso**. Se pierde al reiniciar o suspender Render, o si hay varios procesos/instancias. No equivale a almacenamiento en PostgreSQL.
- No recibe ni publica coordenadas, imágenes, videos o ubicaciones científicas. No proporciona evidencia de conectividad 5G real.
- El endpoint se **niega a aceptar datos** si no está definida la variable de entorno `PANTHERASENSE_INGEST_KEY`.

## Requisitos antes de desplegar

1. Confirmar el espacio de trabajo Render y el servicio de pruebas correspondiente; **no desplegar automáticamente sobre producción**.
2. En Render definir la variable de entorno secreta `PANTHERASENSE_INGEST_KEY` con al menos 16 caracteres aleatorios generados por el responsable (preferiblemente más de 32).
3. Publicar y verificar el receptor FastAPI en un ambiente de pruebas. `GET /api/sense/latest` debería devolver `status: "waiting"` inicialmente.
4. En una **copia de pruebas no compartida** del proyecto de Wokwi, usar [sketch.ino](sketch.ino). Cambiar la constante `API_KEY` por el mismo secreto temporal y apuntar `API_URL` al receptor autorizado.
5. No publicar ese sketch con la clave real, ni compartir su URL de Wokwi mientras contenga la clave: una clave embebida en firmware o proyecto público **no es un secreto seguro**. Rotarla después de la prueba.
6. Iniciar Wokwi y comprobar HTTP 202 en el monitor serial. Después revisar la interfaz de pruebas PantheraEDGE; verás temperaturas, humedades y hora de recepción.
7. Solo tras comprobarlo todo y aprobarlo expresamente, valorar la migración al frontend y backend de producción.

## Verificación automática y local

```bash
cd v2/backend
python -m pytest -q test_sense_api.py
cd ../frontend
npm install
npm run build
```

## Limitaciones y próximos pasos

Este es un prototipo de integración para enseñanza. `client.setInsecure()` en el sketch omite verificar el certificado HTTPS **solo en Wokwi**; antes de fabricar un equipo real, se necesita verificación TLS, credenciales rotables no extraíbles, limitación de solicitudes, autenticación de acceso, almacenamiento persistente, sincronización y gestión de fallos de red. El ESP32 simulado no mide variables de campo ni utiliza 5G.

**Estado:** implementación preparada exclusivamente en la rama `pantherasense-integration`; pendiente de confirmar Render y probar de extremo a extremo contra un servicio desplegado.
