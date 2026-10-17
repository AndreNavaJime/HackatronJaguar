# PantheraLIVE: detección adaptativa con baja luz (prototipo)

## Qué funciona en la app

En **PantheraLIVE → EDGE · Cámara de este dispositivo** (o transmisión
WHEP compatible), el detector del navegador obtiene el brillo aproximado
de un muestreo de píxeles del fotograma, en escala 0–255. Este número **no
es una medición de lux**, no está calibrado como sensor científico.

- Con iluminación suficiente, el detector COCO-SSD Lite ve el fotograma
  original.
- Cuando el fotograma está moderadamente oscuro, aplica corrección gamma
  limitada **solo al canvas en RAM utilizado para inferencia**. No altera
  el archivo de video guardado en IndexedDB, no simula detalles y no
  pretende identificar jaguares.
- Si la imagen está prácticamente negra, aparece una advertencia
  **Luz insuficiente** y no se intenta fabricar detecciones a partir del
  ruido del sensor. Una cámara ordinaria no ve en oscuridad total.
- Con teléfonos que anuncian capacidad `torch` en
  `MediaStreamTrack.getCapabilities()`, aparece opcionalmente
  **Encender luz auxiliar (prueba doméstica)**. La luz no se activa
  sin consentimiento, no se muestra cuando Chrome no la admite y **no
  debe emplearse para iluminar fauna silvestre**.

Este ajuste es experimental. Aclarar digitalmente una foto puede aumentar
el ruido y producir falsos positivos o falsos negativos. No garantiza
detectar a Josefina en cualquier iluminación ni identifica especies.

## Prueba controlada

1. Actualizar PantheraLAB y abrir PantheraLIVE en Chrome Android.
2. Conectar cámara local, dejar que «Fotogramas analizados» aumente.
3. Enfocar a Josefina con luz normal: anotar categoría y puntuación
   aproximada, registrar si produjo clip.
4. Disminuir moderadamente la iluminación: comprobar que la pantalla
   indique **Mejora automática para detección**, sin transformar el
   video grabado, y repetir la observación.
5. Apagar la luz completamente: debe indicar **Luz insuficiente**, no
   declarar fauna inexistente.
6. Solo si aparece y es conveniente, activar la luz auxiliar para la
   prueba doméstica; cerrar la cámara al terminar.

Para evaluar efectividad real, comparar detecciones por nivel de luz,
considerando los casos en que no detecta al animal, no solo los clips
que llegan a la bandeja.

## Cámara trampa nocturna para investigación

El diseño definitivo debe utilizar una cámara **sensor compatible con IR +
iluminación infrarroja**, normalmente blanco y negro en baja luz, con
iluminadores apropiados a la distancia de muestreo. LED IR **940 nm
no-glow** puede ser preferible al flash visible; depende del sensor,
energía disponible y sensibilidad del dispositivo. No asumir que el
sensor RGB de un teléfono ve IR sin hardware compatible.

Para fauna real, ejecutar **MegaDetector V6 u otro detector de animales
entrenado con material de cámaras trampa**, además de evaluar imágenes
nocturnas IR, resolución, falsas alarmas por lluvia, condiciones de campo
y animales pequeños/ocultos. MegaDetector distingue fauna/personas/
vehículos, **no identifica especies ni jaguares individuales**.

Tanto EDGE como LIVE pueden recibir un stream ya iluminado por IR:
el navegador no controla la iluminación de la cámara remota mediante
WHEP y el modo de baja luz no sustituye el hardware.

Render gratuito sirve el frontend/API, no es un nodo de inferencia
neuronal fiable para múltiples cámaras en continuo ni almacenamiento
persistente de videos.
