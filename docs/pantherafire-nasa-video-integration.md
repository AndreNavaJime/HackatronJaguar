# PantheraFIRE · integración de datos externos y revisión visual (fase 1)

## Separación de fuentes

**PantheraFIRE sigue siendo el último módulo**. A partir de esta entrega,
la interfaz muestra tres flujos *claramente diferentes*:

1. **NASA EONET v3 · eventos reportados**: catálogo público consultado
   mediante el backend PantheraLAB, con regiones Mundo, Centroamérica y
   Costa Rica y ventanas de 7, 30 o 90 días. La respuesta distingue
   eventos abiertos/cerrados en el **catálogo** y cita la fuente original.
   Los datos son reales y externos, pero no equivalen a focos térmicos
   recién detectados ni a un monitoreo continuo de cada cámara.
2. **Cámara PantheraFIRE**: vista local y WebRTC/WHEP. Si el operador instala
   el modelo PyroEngine de forma autorizada en un servidor compatible,
   se puede activar voluntariamente el envío de fotogramas para análisis.
   **El servicio gratuito de Render no tiene ese detector configurado**,
   por lo que este modo no afirma detección neuronal de incendios.
3. **Laboratorio visual de videos (local)**: ahora accesible mediante
   un panel avanzado expandible, sin necesidad de encender fuego.
   Analiza fotogramas con reglas simples de colores rojizos y
   variación de regiones grises. **No usa IA entrenada**, no confirma
   fuego ni humo, y puede generar falsos positivos por luz, niebla,
   nubes, suelo y movimiento ambiental. El archivo no se sube.
4. **Wokwi MQ-2**: señal digital **simulada** de gases combustibles,
   separada de los datos EONET y de cámaras. Jamás confirma un incendio.

## Datos oficiales utilizados

- API de eventos: https://eonet.gsfc.nasa.gov/docs/v3
- Endpoint de categoría `wildfires`: https://eonet.gsfc.nasa.gov/api/v3/events
- Explorar focos térmicos satelitales (servicio independiente):
  https://firms.modaps.eosdis.nasa.gov/map/
- La API de NASA FIRMS para datos geolocalizados necesita una
  **MAP_KEY gratuita** obtenida por un operador; no está instalada ni
  simulada en PantheraLAB: https://firms.modaps.eosdis.nasa.gov/api/

La API interna `GET /api/fire/nasa-events?region=world&days=30`
emplea filtros fijos, un límite de 100 eventos y caché de 15 minutos
**en memoria de Render**. No permite URL arbitraria ni envía posiciones
de cámaras: las áreas son límites geográficos amplios predefinidos.
No almacena coordenadas sensibles del proyecto. Si el catálogo está
vacío o deja de responder, la interfaz lo indica como **falta de
información**, no como prueba de ausencia de incendios.

Las fechas de geometría EONET son fechas de referencia del catálogo,
a veces redondeadas a 00:00Z; no deben interpretarse automáticamente
como instantes exactos de ignición o de detección en vivo.

## Lo que aún falta para detección específica en cámaras

- Modelo real de humo/llamas **entrenado y evaluado** con cámaras en
  bosque seco/tropical, escenas nocturnas/IR, niebla y cambios de luz.
- Backend/inferencia en hardware EDGE o en servidor dimensionado;
  Render Free sigue apto para API ligera y consultas EONET, no para
  múltiples streams de IA pesada 24/7.
- Evidencia video de eventos para revisión, detector con reducción de
  falsas alarmas, registro reproducible, estadísticas y auditoría.
- Ingesta autenticada y persistente con almacenamiento privado,
  alertas configurables a investigadores, historial y permisos.
- No realizar despachos ni declarar emergencias automáticas sin
  validación y una integración formal con protocolos competentes.

## Cómo probar sin encender fuego

1. Abrir **PantheraFIRE**.
2. Consultar NASA EONET en **Mundo / últimos 30 días** y abrir alguna
   ficha oficial. Probar Costa Rica para observar resultados o mensajes
   de ausencia sin confundirlos con «sin incendios».
3. Expandir **Laboratorio visual** y cargar un video autorizado o
   material de archivo. Los resultados son indicios de reglas y se
   revisan manualmente. No se requiere ninguna prueba con fuego real.
4. Comprobar que la cámara PyroEngine aparece como no configurada,
   y que Wokwi sigue claramente identificado como simulación.
5. Verificar que PantheraFIRE permanezca al final de la navegación.

Este módulo es **investigación experimental, no un servicio de alerta
temprana de seguridad pública**. Ante incendio observado realmente,
seguir canales oficiales de emergencia.
