# PantheraID 2.0 — migración multiplataforma

Desarrollo experimental en la rama `pantheraid-v2`. **No se modifica** la versión original `app.py` de Streamlit.

## Funciones disponibles
- React + TypeScript + Vite: interfaz responsive, navegación y visor de fotografías.
- FastAPI: `/api/health`, `/api/capabilities`, `/api/images/inspect`.
- **MegaDetector V6 opcional** (YOLOv10-c compacto por defecto): `/api/images/detect?threshold=0.25`; recuadros, confianza, conteos animal/persona/vehículo, imagen anotada descargable y tiempo medido de inferencia.
- Se procesan fotografías de hasta 12 MB y 40 megapíxeles. La API utiliza archivos temporales durante la inferencia y los elimina; no persiste imágenes en Supabase.
- Detección real requiere instalar PyTorchWildlife y cargar sus pesos; **no está operativa automáticamente** por el mero hecho de descargar esta rama.
- No hay todavía identificación validada de especies o individuos, videos, registros Supabase ni ingesta de VIGÍA en v2.

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

Terminal C — dependencias de IA opcionales **antes de iniciar la detección**:
```bash
cd /workspaces/HackatronJaguar/v2/backend
python -m pip install -r requirements-ai.txt
```
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

## Pruebas de API
Se añadieron pruebas con un modelo simulado para no descargar pesos durante los tests:
```bash
cd v2/backend
python -m pip install pytest httpx
python -m pytest -q test_api.py
```
Estas pruebas **no prueban inferencia real de MegaDetector**. Validar con fotografías de cámaras trampa y posteriormente con datos anotados de referencia.

## Notas científicas
MegaDetector detecta **animales, personas y vehículos**, no identifica la especie ni el individuo de un jaguar. La puntuación de confianza de detección no es una medida de exactitud externa ni prueba de calibración. La ausencia de detecciones por encima de un umbral no demuestra ausencia de fauna.

## Siguientes etapas
1. Completar y validar inferencia de fotografías en Codespaces.
2. Migrar análisis de videos, selección de fotogramas, gráficos y exportaciones PDF/ZIP.
3. Separar identificación individual y su validación científica.
4. Integrar Supabase con autenticación y políticas RLS comprobadas.
5. Conectar PantheraEDGE/VIGÍA y telemetría testbed; diferenciar mediciones de estimaciones.
6. Preparar PWA; más adelante evaluar Capacitor/Tauri para tiendas y escritorio.

No publicar credenciales, datos confidenciales ni identificaciones científicas no validadas. Antes de desplegar fuera del entorno de desarrollo, implementar autenticación, control de uso y límites de concurrencia.
