# PantheraID 2.0 — primera base multiplataforma

Esta carpeta es una **nueva interfaz experimental** y una API mínima. No reemplaza ni modifica `app.py` (Streamlit).

## Estado
- React + TypeScript + Vite: interfaz responsive preliminar con navegación.
- FastAPI: endpoints de salud y capacidades, sin modelos de IA conectados.
- **No hay aún** identificación de individuos, análisis de video, sincronización con Supabase ni ingesta real de VIGÍA en v2.
- Las aplicaciones Android/iOS (Capacitor), escritorio (Tauri) y PWA se evaluarán después de validar el flujo web.

## Ejecutar frontend
```bash
cd v2/frontend
npm install
npm run dev
```
Abrir http://localhost:5173

## Ejecutar backend (otra terminal)
```bash
cd v2/backend
python -m pip install -r requirements.txt
uvicorn main:app --reload
```
Ver http://localhost:8000/docs

## Inventario inicial de app.py (5072 líneas, inspección estructural)
- Supabase: carga, inserción, eliminación y esquema de registros.
- MegaDetector/PytorchWildlife: detección de animal/persona/vehículo; **no** identidad individual.
- Análisis de imagen y video; exportación PDF/ZIP y métricas de confianza.
- Eventos PantheraEDGE, validación HMAC opcional, GeoJSON, consulta Copernicus y estimaciones de red.
- Interfaz Streamlit con sidebar, controles y gráficos.

## Secuencia de migración
1. Extraer lógica Python independiente de Streamlit y añadir pruebas.
2. API para cargas, trabajos asíncronos y resultados con límites de tamaño y autenticación.
3. Migrar visor de imágenes/video y gráficos científicos, manteniendo descarga de resultados.
4. Integrar Supabase con permisos y políticas RLS verificadas.
5. Integrar nodo VIGÍA y testbed con métricas medidas diferenciadas de estimaciones.
6. PWA y posteriormente empaquetado Capacitor/Tauri.

No publicar credenciales ni datos sensibles. El frontend nunca debe recibir claves de servicio de Supabase.
