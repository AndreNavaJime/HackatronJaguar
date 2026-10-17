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



## PantheraSCAN · comparación opcional de rosetas (investigación NO COMERCIAL)

Nuevo cuaderno independiente:
[PantheraSCAN_Rosetas_Colab.ipynb](https://colab.research.google.com/github/AndreNavaJime/HackatronJaguar/blob/pantherasense-integration/notebooks/PantheraSCAN_Rosetas_Colab.ipynb).

**Objetivo:** comparar la similitud visual de una fotografía de consulta contra imágenes de referencia aportadas y etiquetadas por el investigador; no requiere bases de datos de ONG y **no certifica identidades**.

**Cómo probarlo:** abrir el cuaderno en Google Colab; ejecutar las celdas; subir 1 fotografía de consulta y 1–30 fotografías de referencia; ingresar el nombre/código conocido de cada referencia; aceptar explícitamente las condiciones **de investigación no comercial** antes de descargar el modelo; obtener ranking de similitud coseno y descargar `resultado_pantherascan_rosetas.json`. Finalmente, en la rama experimental publicada de la app, abrir **PantheraSCAN → Opcional · Comparar rosetas**, importar JSON, anotar candidato/revisor/dudas, exportar `PantheraSCAN_revision_rosetas.json`. Si la app aún no se publica, el JSON del cuaderno puede conservarse para importación posterior.

**Implementación:** código MIT de [WildlifeTools](https://github.com/WildlifeDatasets/wildlife-tools) (dataset, `DeepFeatures`, `CosineSimilarity`) y pesos [BVRA/MegaDescriptor-T-224](https://huggingface.co/BVRA/MegaDescriptor-T-224) de licencia **CC BY-NC 4.0**. No se incluyen pesos en el repositorio, ni se cargan en Vercel ni en Render. **No habilitar para venta, uso comercial ni servicio productivo** sin una licencia de pesos diferente o permiso correspondiente.

**Limitaciones:** el ranking depende de la calidad de fotos, de rosetas visibles, puntos de vista similares y de la galería del investigador; si no existe una foto de un individuo conocido comparable no es posible identificarlo. Puntuaciones coseno no son probabilidades (0,91 NO significa 91 % de confianza) ni se han calibrado sobre nuestros datos. El cuaderno asume manualmente que las fotos son de jaguar, pero no ejecuta SpeciesNet. La confirmación de identidad queda fuera de este prototipo y requiere revisión visual y validación de un protocolo científico.

**Privacidad:** las fotografías se procesan dentro de la sesión temporal de Colab del usuario. El JSON exportado contiene nombres/códigos y puntuaciones, sin imágenes ni embeddings biométricos. PantheraSCAN solo guarda metadatos de la comparación en `sessionStorage`, no los publica en nube ni los incorpora automáticamente a fichas de PantheraMONITORING. Exportar los JSON antes de cerrar la pestaña.

**Estado:** código experimental agregado en GitHub; requiere ejecución manual en Colab, comprobación de dependencias de tiempo de ejecución y compilación/publicación posterior del frontend; no se declara producción operativa.

### Primer ensayo real documentado (16 de octubre de 2026, Costa Rica)

La persona investigadora ejecutó el cuaderno en **GPU T4 (CUDA)** y obtuvo el mensaje
`Características calculadas con WildlifeTools. Similitud coseno, NO probabilidad.`.
El programa descargó `BVRA/MegaDescriptor-T-224`, comparó **una fotografía de Josefina
(perra doméstica; consulta, 1198 × 1600 px)** con **una fotografía de jaguar
(referencia)** y generó `resultado_pantherascan_rosetas.json`.

**Resultado observado:** similitud coseno **-0.034706** y **1 referencia**.
Es una inferencia real del pipeline, **no una validación de identidad individual**:
se compararon animales de **especies diferentes** y no hay referencias suficientes
para decidir identidades. El resultado **no equivale a -3,47 % ni a una probabilidad**.
No se ejecutó identificación taxonómica. El JSON original incluía
`species_assumed_by_user: Panthera onca` aun cuando la foto de consulta era de
una perra; ese dato es una suposición del formato y **no evidencia biológica**.

Se conserva una versión **anonimizada, solo metadatos**, de este resultado en
`v2/frontend/public/examples/pantherascan-rosetas-colab-prueba-01.json`.
No se publica el JSON original, los nombres originales de fotografías ni
las fotografías. PantheraSCAN ofrece un botón **«Ver primera prueba real»**
que muestra el valor sin incorporarlo al registro científico y sin poder
asignarle una identidad. La prueba completa puede repetirse con fotografías
autorizadas de jaguares de identidad conocida, en un diseño con positivos
y negativos y revisión científica.

**Estado:** cuaderno ejecutado exitosamente al menos una vez;
el frontend con la visualización de este ejemplo requiere todavía
compilación y despliegue. La biblioteca y el modelo de este ejemplo
se mantienen exclusivamente para investigación no comercial.
