# PantheraLAB · PantheraEDGE (Hackatrón 5G)

Este repositorio contiene la aplicación científica **Streamlit** (`app.py`) para el análisis de evidencia de cámaras trampa. Su nombre funcional es **PantheraEDGE**, dentro de la plataforma PantheraLAB.

## Módulos y límites

- **PantheraCAM**: captura y sensores del nodo de campo (hardware o emulador, integración separada).
- **PantheraEDGE**: análisis de video e imagen, muestreo de fotogramas, detección de animales/personas/vehículos con MegaDetector 6, anotación científica, metadatos de campo y exportaciones.
- **PantheraID**: identificación individual de jaguares. **No está implementada por MegaDetector**; la identidad en esta aplicación es una anotación de investigador.
- **PantheraMONITORING**: dashboard de monitoreo aguas abajo; no se debe confundir su integración prevista con un panel ya conectado a datos de producción.

## Uso local

```bash
pip install -r requirements.txt
streamlit run app.py
```

La primera ejecución de MegaDetector puede requerir descargar pesos del modelo. Para intercambio Supabase, configurar `SUPABASE_PUBLISHABLE_KEY` en secretos de Streamlit y verificar permisos RLS con la persona administradora. Nunca escribir claves privadas directamente en el repositorio.

## Ficha científica

La observación admite datos del investigador, institución, estudio, protocolo, cámara, instalación/retiro, esfuerzo de muestreo, especie e individuo anotados, calidad de evidencia, método de identificación, variables ambientales, fuente de medición, hábitat, comportamiento y limitaciones. Ninguno de estos campos está obligado a derivarse de IA.

Las variables ambientales ausentes permanecen **sin dato**; no se inventan 100 m, 25 °C o 80 % de humedad. Los datos de Sentinel se presentan como metadatos de catálogo, no como mediciones ambientales calculadas.

## Exportación y persistencia

- Exportación de observación: JSON, GeoJSON e informe PDF.
- Registro de observaciones: tabla y respaldo CSV/JSON.
- **Importante:** el registro en Streamlit es de sesión, no almacenamiento persistente; descargar el respaldo antes de cerrar la sesión. Las escrituras Supabase disponibles se limitan al contrato ya existente y a sus permisos efectivos.

## Validación

```bash
python -m py_compile app.py
```

Esto solo comprueba sintaxis. El funcionamiento de MegaDetector, la ingesta del nodo VIGÍA, la comunicación con Supabase y la interfaz móvil deben probarse con datos reales o de prueba antes de un despliegue.
