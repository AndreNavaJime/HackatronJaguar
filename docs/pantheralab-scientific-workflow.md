# PantheraLAB · flujo científico y límites del informe

## Orden para equipos de investigación

1. **PantheraMONITORING**: crear/seleccionar estudio local, preparar **Biblioteca de individuos** y registrar estaciones. En la biblioteca, la sección Supabase es independiente, privada y solo se habilita al configurar credenciales públicas, Auth y RLS; las fichas locales antiguas se conservan en IndexedDB/localStorage sin sincronizarse.
2. **PantheraLIVE**: conectar fuente y revisar eventos preliminares. La cámara local ofrece vista previa; en el backend gratuito no está habilitada la detección neuronal de fauna y no se guardan clips.
3. **PantheraSCAN**: subir fotografías o videos, comparar hasta seis imágenes de referencia usando SIFT/RANSAC y revisión humana; la biblioteca en nube solo puede ofrecer fotos cuando hay una sesión Supabase autorizada. Sin catálogo previo también se pueden dejar animales sin identificar.
4. **PantheraMONITORING**: registrar el evento y validar individuos con evidencia; todos los cambios de campo se guardan en la carpeta del estudio **local activo**. Este retorno desde SCAN no exige crear otro estudio.
5. **PantheraSENSE**: consultar sensor virtual identificado como **simulación**, no equivaler a una medición ligada automáticamente a estación o captura.
6. **PantheraSAT**: consultar catálogo Sentinel o vegetación, siempre con fuente y límites. La estación sugerida se obtiene solo del estudio activo; la consulta no se inserta automáticamente en capturas ni en PDF.
7. **Informes científicos**: estudio local seleccionado, estadísticas y PDF/ZIP, fichas de individuos y capturas bajo opciones secundarias. Las estadísticas provienen solo de estaciones, eventos y observaciones efectivamente vinculados al estudio. El ZIP incluye `statistics.json` para auditar los conteos.
8. **PantheraFIRE**: siempre el último módulo del menú, con acceso directo y alertas independientes.

La navegación no exige completar cada pestaña: proyectos sin catálogo pueden registrar individuos desconocidos; investigadores con videos históricos pueden abrir directamente SCAN.

## Interpretación y privacidad de estadísticas

Los gráficos incorporados tanto al navegador como al PDF describen:
- eventos de captura por cámara y mes UTC,
- observaciones anotadas por especie y estado de revisión,
- individuos con verificación de un revisor,
- esfuerzo declarado por estación, y un índice **eventos / 100 días-cámara** solo cuando se completó el esfuerzo de todas las estaciones y es positivo,
- temperatura/humedad registradas en eventos con valores numéricos finitos.

**Nunca** interpretar estos recuentos como tamaño poblacional, densidad, captura independiente, probabilidad de identificación, modelo de ocupación o diversidad estimada estadísticamente sin otro protocolo. Las imágenes de referencia y coordenadas sensibles requieren protección. El informe oculta coordenadas por defecto y las incluye solo mediante confirmación expresa.

## Integraciones pendientes

La Biblioteca Supabase **no** equivale a una sincronización de todos los estudios locales con la nube. Los eventos PantheraLIVE en memoria, los datos virtuales SENSE, los resultados de modelos externos y las consultas SAT transitorias no se unen automáticamente al PDF. Esto exige un modelo unificado de procedencia, permisos, vínculos entre estaciones e informes y evaluación científica posterior. No presentar enlaces, indicadores o botones futuros como si estuvieran conectados.
