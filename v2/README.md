# PantheraID 2.0 — migración multiplataforma

Desarrollo experimental en la rama `pantheraid-v2`. **No se modifica** la versión original `app.py` de Streamlit.

## Funciones disponibles
- React + TypeScript + Vite: interfaz responsive, navegación y visor de fotografías.
- FastAPI: `/api/health`, `/api/capabilities`, `/api/images/inspect`.
- **MegaDetector V6 opcional** (YOLOv10-c compacto por defecto): `/api/images/detect?threshold=0.25`; recuadros, confianza, conteos animal/persona/vehículo, imagen anotada descargable y tiempo medido de inferencia.
- **Análisis de video (fase beta)**: MP4, MOV, AVI y MKV mediante `/api/videos/jobs`, con muestreo configurable, progreso consultable, galería de fotogramas anotados, recortes candidatos, tabla CSV, ZIP de evidencia, PDF de reporte y gráficos en la interfaz. Requiere dependencias de video y códec compatible.
- Se procesan fotografías de hasta 12 MB y 40 megapíxeles. La API utiliza archivos temporales durante la inferencia y los elimina; no persiste imágenes en Supabase.
- Detección real requiere instalar PyTorchWildlife y cargar sus pesos; **no está operativa automáticamente** por el mero hecho de descargar esta rama.
- No hay todavía identificación validada de especies o individuos, registros Supabase ni ingesta de VIGÍA en v2. La migración de análisis de video está implementada como primera etapa y aún requiere pruebas con videos reales en Codespaces.

## App instalable PWA (Android / iPhone)

Se preparó la interfaz de **PantheraID 2.0 como PWA**: `manifest.webmanifest`, ícono de jaguar, versiones PNG 180/192/512 y maskable 512, pantalla de inicio independiente (`display: standalone`), botón «Instalar app», vista móvil y service worker.

**No se necesita otra herramienta de desarrollo.** En el frontend, `npm run dev` y `npm run build` ejecutan automáticamente el script de Node `scripts/generate-pwa-icons.mjs` antes de arrancar o compilar. No requiere dependencias npm extra. Los PNG generados se ignoran en Git, pero se incluyen en `dist/` al compilar. Si Vite ya estaba iniciado antes de actualizar el repositorio, **parar Vite y arrancarlo nuevamente** para generar los íconos y servir los archivos nuevos.

Para comprobar la instalación desde el celular:
- Android: abrir la PWA por **HTTPS** en Chrome; utilizar «Instalar app» o el menú ⋮ → «Instalar aplicación» / «Agregar a pantalla de inicio».
- iPhone: abrirla por **HTTPS en Safari**; tocar **Compartir → Agregar a pantalla de inicio**. iOS normalmente no presenta el diálogo nativo `beforeinstallprompt`; el botón de la app muestra instrucciones.
- El navegador decide si ofrece instalación según sus requisitos; la configuración del repositorio por sí sola no garantiza que aparezca el botón nativo en todos los dispositivos.

**Precauciones:** Codespaces ofrece una URL HTTPS de desarrollo cuya disponibilidad, permisos y nombre pueden variar. No es un despliegue estable para usuarios científicos; aún falta desplegar un frontend HTTPS estable junto con una API Python segura (mismo origen o proxy configurado), autenticación y pruebas en teléfonos reales.

**Sin conexión:** el service worker solo conserva recursos públicos del frontend y una página explicativa para cuando no haya red. **Nunca almacena** peticiones o respuestas de `/api/`, datos de análisis, fotografías de investigación o videos. **MegaDetector, análisis y descargas requieren conexión con FastAPI**. En el servidor de desarrollo de Vite, los módulos dinámicos del frontend no se guardan para modo sin conexión. Una PWA **no ejecuta PyTorch directamente en el teléfono**.

### Comprobaciones recomendadas
```bash
cd /workspaces/HackatronJaguar/v2/frontend
npm run build
```
Confirmar que `dist/manifest.webmanifest`, `dist/sw.js` y `dist/icons/icon-192.png` existen. El backend sigue funcionando en el puerto 8000 durante las pruebas de fotografías y videos; el frontend de desarrollo continúa en 5173.

## Ejecutar en Codespaces (tres terminales)

Terminal A — interfaz:
```bash
cd /workspaces/HackatronJaguar/v2/frontend
npm install
npm run dev -- --port 5173 --strictPort
```

Terminal B — servidor Python:
```bash
cd /workspaces/HackatronJaguar/v2/backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Terminal C — dependencias de IA y video (se instalan una vez antes de reiniciar FastAPI):
```bash
cd /workspaces/HackatronJaguar/v2/backend
python -m pip install -r requirements-ai.txt
python -m pip install -r requirements-video.txt
```
En el Codespace actual, OpenCV (`cv2`) ya llegó con la instalación de la IA; `requirements-video.txt` instala ReportLab para PDF sin instalar una segunda variante de OpenCV que pudiera entrar en conflicto. Si una instalación nueva no tiene `cv2`, instalar `opencv-python-headless` por separado.
Después de instalar, reiniciar la terminal B con Ctrl+C y el comando de inicio de Python anterior. La primera inferencia descarga pesos de MegaDetector y puede tardar o necesitar bastante memoria/espacio. En Codespaces se utiliza normalmente CPU, por lo que el rendimiento puede ser limitado. Si las dependencias IA fallan, el visor y la recepción de fotografías pueden seguir funcionando.

### Diagnóstico de error «Unexpected end of JSON input»

Ese error significaba que el frontend esperaba JSON, pero la respuesta de la API llegó vacía, incompleta o en otro formato. No permite concluir por sí solo que se agotó la memoria. A partir de esta revisión la interfaz presenta mensajes más claros y el servidor registra las excepciones en su terminal.

**Variante predeterminada nueva:** `MDV6-yolov10-c` (MegaDetector V6, YOLOv10 compacto, 2,3 millones de parámetros), publicada por Microsoft como opción ligera para CPU. **No es el mismo modelo** que la antigua configuración `MDV6-yolov9-c`; las detecciones y tiempos pueden variar y hay que indicar siempre qué versión se utilizó. La licencia de los pesos YOLOv10 compactos es AGPL-3.0; comprobar compatibilidad antes de un despliegue comercial.

La versión antigua solo puede seleccionarse expresamente mediante `PANTHERA_MD_VERSION=MDV6-yolov9-c` en el entorno de FastAPI. Por defecto queda la variante ligera para reducir presión de memoria.

Si el servicio deja de responder, ejecutar en la **tercera terminal** (sin cargar modelos):

```bash
cd /workspaces/HackatronJaguar/v2/backend && python diagnostico.py
```

Revisar RAM disponible y el contador `oom_kill`. Son pistas y no un diagnóstico definitivo: el contador es acumulativo y puede haber fallos de red, proxy, descargas o compatibilidad.

**Reinicio tras actualizar código:** parar el proceso de FastAPI con Ctrl+C y volver a iniciar `python -m uvicorn main:app --host 0.0.0.0 --port 8000`. Vite suele actualizarse automáticamente al cambiar archivos React. Mantener ambas terminales abiertas.

La web de Codespaces se abre por puerto 5173. FastAPI documenta sus endpoints en el puerto 8000, ruta `/docs`. Vite redirige `/api` a 8000 mediante `vite.config.ts`.

## Análisis de video y privacidad
- Entrá a **PantheraID** en el puerto 5173, seleccioná un video y elegí umbral, intervalo (0,5 a 5 s) y máximo de fotogramas (1 a 24).
- El prototipo acepta archivos de hasta **250 MB** y videos con duración informada de hasta **10 minutos**, resolución máxima 3840 × 2160. El análisis se realiza sobre copias redimensionadas, lado mayor 960 px, y las coordenadas de los recuadros corresponden a esa resolución de análisis.
- El video se envía desde el navegador en **solicitudes independientes de 5 MiB**, mediante `POST /api/videos/uploads`, `PUT /api/videos/uploads/{id}/chunks?offset=...` y `POST /api/videos/uploads/{id}/complete`. Esto reduce el riesgo de rechazo por límites de tamaño de petición del proxy. FastAPI almacena los bloques directamente en disco, sin cargar los 250 MB completos en RAM; se necesita espacio libre y archivos grandes pueden tardar más. Una carga incompleta puede cancelarse con `DELETE /api/videos/uploads/{id}`. No se envía a Supabase. El video original se borra al finalizar el trabajo; resultados y archivos ZIP/CSV/PDF vencen aproximadamente a la hora y se eliminan al atender nuevas solicitudes. Una caída inesperada puede dejar temporales y el almacenamiento temporal **no es un mecanismo de seguridad ni retención formal**.
- **Solo un video a la vez por proceso.** Los trabajos y las sesiones de carga se almacenan en memoria del proceso FastAPI; reiniciar FastAPI cancela o pierde seguimiento de esos trabajos. Las cargas incompletas se consideran abandonadas tras 30 minutos de inactividad; los reportes finalizados vencen después de una hora. No implementar como servicio público sin autenticación, control de uso, cifrado y cola de tareas persistente.
- **RETAIN**: al menos una detección animal en el fotograma muestreado; **DISCARD**: no se detectó un animal sobre el umbral. Esta clasificación no verifica especie ni ausencia ecológica.
- El indicador de reducción es una **estimación de bytes JPEG de fotogramas muestreados frente a los retenidos**, no representa tráfico 5G real ni ahorro de red medido. El recuento de animales suma detecciones por fotograma, **no individuos únicos**.
- Si el video contiene FPS variables, el timestamp inferido por número de fotograma es nominal; para aplicaciones científicas más exigentes habrá que extraer PTS reales y validar fotogramas.
- Descargas: ZIP con fotogramas retenidos, fotogramas anotados retenidos, recortes candidatos y CSV; también PDF preliminar y CSV independiente. El reporte incluye límites metodológicos.

## Error de proxy al subir videos grandes
Si aparece «respuesta no JSON» o un HTTP 413/502, puede ser que un servidor intermediario bloquee una petición. Desde esta versión, el navegador divide la carga en trozos de 5 MiB e informa cuántos MB han llegado a FastAPI. Si falla un bloque, la interfaz muestra el código HTTP en vez de afirmar que Python produjo JSON inválido. Los límites externos de Codespaces no están bajo control de este repositorio; comprobar en las terminales de Vite y FastAPI si continúan los errores.

Para activar los cambios después de `git pull`, reiniciar FastAPI con `python -m uvicorn main:app --host 0.0.0.0 --port 8000`; Vite debe permanecer ejecutándose en el puerto 5173. **No se ha comprobado todavía una subida real de 118 MB ni 250 MB en este entorno**.

## Pruebas de API
Se añadieron pruebas con un modelo simulado para no descargar pesos durante los tests:
```bash
cd v2/backend
python -m pip install pytest httpx
python -m pytest -q test_api.py test_video_api.py
```
Estas pruebas **no prueban inferencia real de MegaDetector** y necesitan OpenCV y ReportLab instalados. Además, deben ejecutarse en Codespaces antes de dar el video por operativo. Validar con fotografías de cámaras trampa y posteriormente con datos anotados de referencia.

## Notas científicas
MegaDetector detecta **animales, personas y vehículos**, no identifica la especie ni el individuo de un jaguar. La puntuación de confianza de detección no es una medida de exactitud externa ni prueba de calibración. La ausencia de detecciones por encima de un umbral no demuestra ausencia de fauna.

## Siguientes etapas
1. Validar análisis real de videos, fotogramas, gráficos y descargas en Codespaces (fase beta implementada).
2. Ampliar metadatos de observaciones, reportes avanzados, filtros, mapas y comparación científica del Streamlit original.
3. Separar identificación individual y su validación científica.
4. Integrar Supabase con autenticación y políticas RLS comprobadas.
5. Conectar PantheraEDGE/VIGÍA y telemetría testbed; diferenciar mediciones de estimaciones.
6. Preparar PWA; más adelante evaluar Capacitor/Tauri para tiendas y escritorio.

No publicar credenciales, datos confidenciales ni identificaciones científicas no validadas. Antes de desplegar fuera del entorno de desarrollo, implementar autenticación, control de uso y límites de concurrencia.
