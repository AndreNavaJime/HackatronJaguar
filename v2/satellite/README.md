# PantheraLAB · análisis satelital real (prototipo)

Desarrollo de la aplicación y propuesta de módulo: **Andrea Navarro Jiménez**.

Esta mejora aparece en **Investigación → Vegetación y hábitat**, solo en la rama experimental `pantherasense-integration` hasta que se autorice migración a la rama original. El desarrollo no requiere pagar una API ni crear credenciales de Copernicus.

## Fuentes abiertas

- **Element 84 Earth Search** `sentinel-2-c1-l2a`: escenas Sentinel-2 Collection 1 L2A, bandas COG `red` (B04), `nir` (B08), `swir16` (B11) y máscara SCL. Earth Search es gratuito *best effort*, sin SLA.
- **ESA WorldCover v200, 2021**: clase **10 = cobertura arbórea clasificada**, incluye plantaciones. Año de referencia **2021**. Uso bajo CC BY 4.0; debe citarse el proyecto ESA WorldCover y el procesamiento Copernicus.

Attribution: © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium. Sentinel-2 data: Contains modified Copernicus Sentinel data, surfaced via Element 84 Earth Search.

## Estadísticos

- NDVI medio = `(B08 − B04) / (B08 + B04)`.
- NDMI medio = `(B08 − B11) / (B08 + B11)`.
- Se aplica la `scale` y `offset` de cada `raster:bands` STAC antes de los índices para preservar la corrección del procesamiento Sentinel-2.
- Píxeles considerados: SCL 4 (vegetación), 5 (suelo desnudo), 7 (sin clasificar), excluyendo nubes y sombras, nieve y agua.
- Se realiza un **muestreo de 96 × 96** píxeles reproyectados en un cuadrado alrededor del punto de la cámara, radio configurable entre 0,2 y 2 km. Se informa fracción válida y nubosidad de la escena.
- Porcentaje NDVI > 0,4: proxy de verdor **NO forestal** (denominador: solo píxeles válidos).
- Proporción WorldCover 2021 clase 10: área **clasificada como cobertura arbórea en 2021**, no % de dosel, no bosque natural exclusivamente y no detección de deforestación reciente.
- Comparación de NDVI: solo si existen **dos fechas de adquisición separadas por al menos siete días**. Las variaciones pueden deberse a nubosidad residual, fenología y condiciones ópticas, NO implican deforestación.
- Cuando WorldCover falla, NDVI/NDMI puede presentarse igual con advertencia y sin inventar porcentajes.

## Implementación y seguridad

- Endpoint: `POST /api/science/vegetation/analyze`.
- Cuerpo: `{ "latitude": 9.93, "longitude": -84.08, "radius_km": 0.2, "days_back": 90, "max_cloud_cover": 40 }`.
- Usa exclusivamente URLs devueltas por Earth Search con hosts satelitales autorizados y WorldCover 2021 fijo, no es un proxy arbitrario.
- Límite global de **una consulta a la vez y 45 s entre inicios** para proteger recursos de Render Free.
- Se buscan hasta 12 metadatos de escenas y se procesan como máximo tres candidatas diferentes; cada banda se remuestrea en una ventana pequeña.
- Sin base de datos, fotos ni coordenadas de jaguares almacenadas. Los proveedores externos reciben el punto de búsqueda y la URL de la imagen solicitada.
- Respuestas `404` si no hay escenas, `422` si no hay píxeles válidos, `502` si el catálogo no responde y `429` al alcanzar el límite del servidor de pruebas.
- No se afirma que las métricas tengan calidad operacional de investigación: faltan validación de campo, mejores mosaicos en clima tropical, análisis multitemporal, incertidumbre e integración GIS rigurosa.

## Requisitos

El backend de `v2/backend/requirements.txt` ya incluye `rasterio`, junto a NumPy (desde OpenCV). Solo se necesitan los servicios ya conectados en modo gratuito. No hay claves en código.

GitHub Actions valida el build y pruebas sin red; una prueba temporal adicional verificó lectura REAL de una escena Sentinel-2 y WorldCover desde el Render de pruebas, tras lo cual se retiró el workflow de prueba en vivo para ahorrar recursos.

**No cambiar a producción hasta que la usuaria apruebe expresamente la integración.**
