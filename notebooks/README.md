# PantheraLAB — Prueba REAL de IA sin tocar Render gratuito

[▶ Abrir la prueba en Google Colab](https://colab.research.google.com/github/AndreNavaJime/HackatronJaguar/blob/pantherasense-integration/notebooks/PantheraLAB_IA_Real_Colab.ipynb)

Cuaderno: `PantheraLAB_IA_Real_Colab.ipynb`

## Prueba del perro
1. Abrí el enlace de Colab con tu cuenta de Google.
2. Tocá **Entorno de ejecución → Ejecutar todas**. Si Colab pide permisos, revisalos.
3. Cuando aparezca el selector, elegí **una foto de tu perro** (solo foto autorizada, sin personas).
4. Esperá la descarga de los pesos y la inferencia. Verás recuadros de MegaDetector, sugerencias de SpeciesNet cuando proceda, y podrás descargar un JSON y un JPG anotado.

La foto se usa únicamente en la sesión temporal de Google Colab. No hay envío automático hacia nuestra aplicación ni un enlace compartido de cámara. No es streaming en tiempo real: es el ensayo de los dos modelos con una imagen real. Google Colab gratuito puede suspenderse, y GPU / memoria no están garantizadas.

## Integración de servidor posterior
Nuestro prototipo experimental FastAPI expone:
- `GET /api/live/capabilities` — capacidad del detector, clasificador y cámaras remotas.
- `POST /api/live/wildlife-frame` — análisis de un fotograma autorizado con MegaDetector y, si el entorno está configurado, SpeciesNet.

El servidor Render **free** (`pantherasense-backend-test`) tiene memoria insuficiente para garantizar la carga estable de PyTorch y SpeciesNet. Su build estándar instala **solo** `v2/backend/requirements.txt`. No instalar las dependencias grandes en este servicio.

Para un servidor privado **con recursos adecuados**, ejecutar de forma explícita:
```bash
python -m pip install -r v2/backend/requirements.txt
python -m pip install -r v2/backend/requirements-ai.txt
export PANTHERA_SPECIESNET_MODEL='kaggle:google/speciesnet/pyTorch/v4.0.3a/1'
```
Los pesos se descargan la primera vez, sujetos a la disponibilidad y licencias de los repositorios de los modelos. No publicar el endpoint de inferencia sin autenticación, límites de solicitudes y medidas de privacidad. La detección de personas NO indica caza furtiva.

**Pendiente:** pruebas reales de instalación e inferencia en Colab, capacidad de cómputo dedicada, autenticación, transferencia segura y almacenamiento de clips de interés. Nada de esto se considera desplegado ni validado automáticamente.

Fuentes: [MegaDetector](https://github.com/microsoft/MegaDetector) y [SpeciesNet](https://github.com/google/cameratrapai).

## Importar resultados reales en PantheraLAB / Vercel

La rama experimental `pantherasense-integration` incorpora el componente `v2/frontend/src/AIResultsPanel.tsx` en la parte superior de **PantheraMONITORING**.

1. Ejecutar [el cuaderno Colab](https://colab.research.google.com/github/AndreNavaJime/HackatronJaguar/blob/pantherasense-integration/notebooks/PantheraLAB_IA_Real_Colab.ipynb), con GPU para SAM 2.
2. Descargar `resultado_pantheralab.json` (y opcionalmente la imagen anotada, comparación visual y máscaras).
3. Abrir la versión **experimental actualizada** de PantheraLAB y entrar en **PantheraMONITORING → Laboratorio de IA → Importar resultado JSON**.
4. Se muestran la detección de MegaDetector, la región LR-ASPP, máscaras SAM 2 y las propuestas taxonómicas de SpeciesNet; los resultados pueden revisarse y exportarse a CSV/JSON. También se pueden abrir imágenes locales por separado.
5. **Importante:** el JSON y las imágenes son archivos distintos; el panel no comprueba automáticamente que correspondan al mismo análisis. Registrar la cámara real, nombre del revisor y especie confirmada solo cuando la evidencia lo respalde.

**Arquitectura:** GitHub contiene el cuaderno y frontend; Google Colab ejecuta inferencia temporalmente; Vercel aloja el frontend; Render sirve la API experimental separada. No existe conexión permanente desde Vercel a una sesión gratuita de Colab ni se ejecuta SAM 2 en Render free.

**Persistencia:** informes importados guardados exclusivamente como metadatos en `sessionStorage` del navegador (máx. 20 por sesión); no se guardan ni suben imágenes. Los campos revisados tampoco se incorporan automáticamente al registro oficial del estudio. Exportar como respaldo antes de cerrar la pestaña y volver a importar cuando sea necesario.

**Estado del despliegue (16-oct-2026):** el código experimental ya contiene el panel, pero Vercel devolvió `402 api-deployments-free-per-day` y bloqueó una nueva publicación. El enlace de vista previa existente puede servir una versión anterior hasta que haya un despliegue READY del commit actual. No confundir código guardado en GitHub con una aplicación ya publicada.

