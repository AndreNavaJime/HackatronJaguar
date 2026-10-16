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
