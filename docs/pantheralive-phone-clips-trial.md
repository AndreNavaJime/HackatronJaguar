# PantheraLIVE · prueba de detección y clips con un celular

## Objetivo

Validar el flujo **cámara activa → detección preliminar de animal → grabación
automática solo del evento → bandeja local → conservar o descartar**. Este
prototipo está preparado para probarlo con un perro o gato doméstico
(Josefina), sin simular detecciones ni generar clips periódicos de hojas, lluvia
o movimiento del fondo.

## Pasos (Chrome Android)

1. Entrar a https://pantherascan-ciencia.onrender.com mediante HTTPS.
   Opcional: menú Chrome → **Instalar aplicación** / **Agregar a inicio**.
2. Abrir **PantheraLIVE**. La opción inicial es **Cámara local**.
3. Seleccionar **Activar cámara local** y aceptar el permiso.
4. Pulsar **Activar detección y grabación selectiva**. Esperar la descarga
   inicial del modelo público COCO-SSD Lite; requiere internet.
5. Mantener visible la app, enfocar a Josefina y dejar que el modelo la
   identifique de forma preliminar como **perro**. Se graba un clip únicamente
   tras una detección con puntuación >= 0.56. La grabación empieza en ese
   instante (sin imágenes anteriores), termina tras unos 4,5 s sin detectar
   animal o al alcanzar 19 s, y reanuda búsquedas sin crear clips duplicados
   mientras el animal permanezca constantemente en cuadro.
6. Revisar el aviso en pantalla. Reproducir el video en **Bandeja de videos
   locales**, elegir **Conservar**, **Descargar** o **Descartar**.
7. Desconectar y reconectar la cámara: los clips terminados siguen en
   IndexedDB del mismo navegador mientras ese almacenamiento persista.
8. Probar sin animales, enfocando plantas u objetos: normalmente no debería
   generar clips. Este resultado depende del detector; falsos positivos
   y animales no detectados siguen siendo posibles.

## Qué hace realmente

- Utiliza un modelo de detección de objetos **COCO-SSD Lite**, no MegaDetector,
  SpeciesNet ni un modelo entrenado/validado para especies neotropicales.
  Sus categorías incluyen perro, gato, ave, caballo, vaca, oveja, elefante,
  oso, cebra y jirafa, **no jaguar, ocelote ni patrones de rosetas**.
- El modelo corre con TensorFlow.js **en el dispositivo**, no se envían
  fotogramas a Render. Los pesos del modelo se descargan inicialmente
  desde un servidor público de modelos.
- Graba mediante MediaRecorder sin micrófono. Requiere navegador compatible.
  Aborta un clip cuando el detector observa personas, pero este control
  **no garantiza privacidad** (puede equivocarse); no grabar personas.
- Solo guarda después de una detección, sin pre-roll aún. Por eso los
  primeros segundos del paso de un animal podrían perderse.
- La bandeja admite 20 videos como máximo, de hasta 25 MB cada uno.
  Los guarda en IndexedDB del teléfono. Marcarlos **Conservar** no es
  una copia de seguridad, solo cambia su estado local. Descargar
  es la forma más fiable de guardarlos hasta conectar un bucket privado.
- La notificación está **dentro de la app**; no hay alertas push con
  la aplicación cerrada, ni grabación con la pantalla apagada.
- Los clips no se envían a Supabase ni a MONITORING automáticamente.
  Los investigadores pueden exportar los videos y añadirlos al estudio
  después de verificar qué muestran.

## Infraestructura Render

- **Render Static Site:** sirve el frontend, TensorFlow.js y la interfaz
  PantheraLIVE por HTTPS. Apto para esta prueba.
- **Render web service gratis:** sirve la API existente, pero no necesita
  inferir cada fotograma cuando la opción de detección local está activa.
  Su entorno tiene CPU/memoria limitadas, puede suspenderse por inactividad,
  y carece de disco persistente en el plan gratuito.
- Almacenamiento futuro multiusuario: bucket privado con autenticación,
  aislamiento por institución y estudio, restricciones sobre coordenadas
  y reglas de retención. Supabase pendiente de conexión/autorización.
- Detector profesional de animales silvestres: analizar MegaDetector /
  PyTorchWildlife en servicio de inferencia dimensionado, o un modelo
  adecuado al dispositivo, con evaluación para falsos positivos y
  falsos negativos. Ninguno se activa automáticamente en Render gratis.

## Validaciones pendientes del piloto

El pipeline de GitHub verifica TypeScript/Vite y pruebas del backend, **no
sustituye** una prueba física en Android. Verificar permiso de cámara,
carga del modelo, velocidad de inferencia, codecs webm/mp4, reproducción,
almacenamiento IndexedDB y batería en el teléfono real.
