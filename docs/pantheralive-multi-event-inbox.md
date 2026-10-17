# PantheraLIVE · videos consecutivos y avisos pendientes

## Propósito

PantheraLIVE prioriza grabar **eventos de posibles animales** para revisión. Cada
evento genera un clip local con un ID propio. En la misma sesión se pueden guardar
varios clips: cuando termina un evento, la vigilancia sigue activa y prepara
el siguiente. Una visita continua que supera los 19 segundos se divide en
segmentos sucesivos tras una pausa breve de unos 1,4 segundos. El modelo
COCO-SSD Lite sigue siendo experimental, puede omitir animales y producir
falsos positivos; no confirma especies ni identidad.

## Bandeja y contador

- **PantheraLIVE** muestra un contador rojo de videos **pendientes de revisión**
  en la navegación, que se actualiza al guardar, conservar o descartar.
- El navegador marca el título y la pestaña con un punto rojo (favicon).
- En plataformas que implementan el Badging API, la app instalada solicita
  actualizar el contador sobre su ícono. **Chrome Android no aplica este API
  al ícono instalado**: allí el punto de la pantalla de inicio está ligado
  a las **notificaciones del sistema pendientes**, al permiso de avisos y a
  la configuración del teléfono/launcher.
- Si el científico aceptó una vez el permiso de notificaciones al conectar
  la cámara, cada video que termine puede actualizar el aviso Android de
  `PantheraLIVE` con el **número total de clips pendientes**. No se envían
  nuevas notificaciones cuando solo se abre el historial.
- Al tocar la notificación, se intenta abrir PantheraLIVE (y su bandeja
  si la app ya estaba abierta). Tras conservar o descartar todos los clips
  pendientes, se solicita cerrar la notificación vigente.
- **Conservar** solo cambia el estado en IndexedDB del dispositivo actual;
  no lo sube a la nube. **Descargar** guarda una copia exportada.
  Ningún video se elimina automáticamente para liberar espacio.

## Capacidad y límites

La prueba de Chrome Android conserva el límite de **20 clips totales por
navegador** y **25 MB por clip** para proteger el espacio del teléfono. Si la
bandeja se llena, PantheraLIVE lo advierte y suspende nuevos clips hasta que
se revisen, exporten y descarten los antiguos. No se prometen grabaciones
ilimitadas ni una cola científica central.

**Muy importante:** la cámara del celular debe permanecer activa con la
página abierta. No es posible seguir grabando con Chrome cerrado mediante
este prototipo, ni notificar eventos nuevos procedentes de otra cámara
remota cuando PantheraLAB está cerrada. Eso requiere el agente EDGE o
un gateway autónomo, backend de ingesta autenticada, almacenamiento
privado y notificaciones push con credenciales de institución.

## Comprobación con Josefina

1. Instalar PantheraLAB desde Chrome Android si el navegador lo permite,
   habilitar avisos una sola vez y conectar **PantheraLIVE → EDGE**.
2. Mostrar a Josefina: esperar un primer evento y que se cierre al salir
   de cámara. Debe aparecer un video pendiente y contador **1**.
3. Hacerla pasar nuevamente después de un breve intervalo: debe grabar
   otro clip **sin reactivar el detector**; contador **2**.
4. Mantener al animal varios segundos en cuadro, incluso más de 19 s:
   deben aparecer segmentos sucesivos mientras la detección persista.
5. Reproducir un clip y marcarlo **Conservar**: pendiente 2 → 1.
   Descartar el otro: pendiente 1 → 0.
6. Si el permiso de Chrome está concedido y Android admite badges por
   notificaciones, comprobar el punto sobre el ícono instalado. Puede
   desaparecer si el científico desliza/descarta manualmente el aviso.
7. Mantener la cámara apuntando a plantas o automóviles sin animales:
   una etiqueta `car` no debe activar grabación (otros errores del
   detector todavía son posibles).

Son pruebas en hardware real, **no** verificadas por la compilación
automática. No se generan capturas ni videos ficticios en estos pasos.
