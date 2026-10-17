# PantheraLIVE: detectar animal antes de intentar especie

## Decisión científica y UX

La función principal de PantheraLIVE es **proponer un evento cuando hay indicios
de un animal y guardar el clip para revisión**. No debe convertir una etiqueta
de COCO-SSD (cat/dog/car) en una identificación de especie. PantheraSCAN y
los investigadores pueden realizar posteriormente análisis más especializados.

El detector experimental instalado **sigue siendo COCO-SSD Lite**, no
MegaDetector. COCO-SSD devuelve sus propias clases de objeto en cada
fotograma y la etiqueta puede fluctuar incluso con el mismo perro:

- `cat` seguido de `dog`: son dos **señales de animal**, aunque no
  son evidencia de la identidad o de la especie.
- `car`, `truck`, `person` u objetos no animales: **no cuentan**
  como señales de fauna. Si el modelo falla y etiqueta un animal solamente
  como automóvil, ese animal podría quedar sin registrar.
- `person` con confianza suficiente bloquea y descarta la grabación
  por precaución, aunque sigue existiendo riesgo de detecciones erróneas.

## Condiciones del prototipo

1. Evaluar solo las clases COCO de animales que admite el modelo.
2. Acumular evidencias en fotogramas durante 6 s, **independientemente del
   nombre específico de la clase**, sin sumar coches u objetos no animales.
3. Disparar un candidato cuando aparece una señal fuerte (>= 0.78),
   dos señales medias (>= 0.38) o tres señales débiles (>= 0.28)
   en esa ventana temporal.
4. Mientras se graba un evento, señales animales más débiles pueden mantener
   la grabación abierta sin volver a exigir confirmación de especie.
5. Almacenar el evento como `animal` **provisional**, no `dog` o `cat`.
   En interfaz se ve «Posible animal», la bandeja permite conservar o
   descartar, y el JSON contiene `species_verified:false`.
6. Guardar el video original, no los fotogramas modificados de inferencia.
   El clip y la revisión siguen siendo locales, sin envío a Render.

**Limitaciones**: esto mejora la continuidad temporal y la interfaz pero
no convierte COCO-SSD en detector fiable de fauna silvestre. El sistema
todavía puede perder animales y generar falsas alarmas. Una detección no
equivale a un individuo identificado ni una grabación a una captura validada.
Para ciencia de campo se necesitarán modelos evaluados con fauna de cámaras
trampa y pruebas cuantificadas con videos etiquetados, también nocturnos IR.

## Prueba con Josefina

- Abrir PantheraLIVE en Chrome Android, conectar cámara y mantener el
  teléfono encendido.
- La app debe mostrar «Fotogramas analizados» aumentando.
- Mostrar a Josefina de cuerpo entero; cambiar el ángulo y la luz.
- Si una predicción cambia entre gato y perro, la app NO debería
  cambiar la etiqueta de especie: mostrará «Posible animal»,
  seguida de la grabación y un clip pendiente de revisión.
- Apuntar a un automóvil o una imagen de automóvil **sin animales**:
  las etiquetas `car` por sí solas no deben disparar clips.
- Revisar con atención falsos positivos, eventos que no se graban
  y videos que requieren revisión humana.

No se habilita push remoto con la app cerrada ni se activa una base de datos
compartida sin conexión autorizada.
