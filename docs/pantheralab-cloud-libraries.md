# PantheraLAB · bibliotecas científicas privadas (piloto)

La nueva pestaña **PantheraMONITORING → Individuos → Biblioteca en la nube**
requiere una cuenta y un proyecto de Supabase autorizados. La interfaz no carga
ni publica fotografías mientras falta esa conexión; los estudios antiguos
continúan en IndexedDB/localStorage **sin sincronización automática**.

## Habilitación
1. Seleccionar un proyecto Supabase autorizado por el responsable científico.
2. Revisar con el administrador `supabase/migrations/20261017_pantheralab_private_libraries.sql` y
   ejecutar la migración **una sola vez** en el editor SQL (no pegues claves en GitHub).
3. Activar inicio de sesión con correo en Supabase Auth, añadir la URL HTTPS de
   PantheraLAB a las URL de redirección permitidas y verificar entregabilidad.
4. Configurar **en el sitio estático** de Render / Vercel y reconstruir:
   - `VITE_SUPABASE_URL=https://<project-ref>.supabase.co`
   - `VITE_SUPABASE_ANON_KEY=<publishable key/anon key>`
5. **Nunca** usar `service_role`, `sb_secret`, claves del panel privado ni token
   de administrador en variables VITE o código del navegador.
6. Crear una institución y un estudio. El creador recibe membresía `owner`
   mediante trigger seguro. No se ofrecen invitaciones a otros investigadores
   hasta que exista una interfaz de aprobación auditada.
7. Preparar CSV y fotografías con nombres idénticos:
   `filename,code,alias,species,sex,age_class,flank,notes`.
   Valores para `sex`: unknown, female, male.
   Para `flank`: unknown, left, right.
   Para `age_class`: unknown, juvenile, subadult, adult.
   Límite de 20 fotos por lote; 8 MB por foto.
8. Desde PantheraSCAN, al iniciar sesión, elegir hasta seis fotos del **mismo
   estudio**. Se descargan con URL firmada de duración breve y se envían a
   Render para comparación SIFT, sin guardarlas allí permanentemente.

## Seguridad y límites del piloto
- Cada institución tiene sus datos aislados con RLS basada en membresía.
- El bucket de fotos es privado. No publicar coordenadas de cámaras ni claves.
- No existe actualmente interfaz para compartir entre instituciones: requerirá
  permisos explícitos y revisión de sensibilidad ecológica.
- Sincronización solo para **biblioteca de individuos y fotos**. Las fichas
  locales previas y eventos de captura NO se migran automáticamente.
- No hay búsqueda automática sobre todos los jaguares ni reconocimiento IA
  validado. El investigador elige las referencias y revisa el resultado SIFT.
- Cada código es único dentro de su estudio. No crear identidades verificadas
  automáticamente; los registros CSV nuevos se crean provisionales.
- Importaciones por lote pueden terminar parcialmente. Si alguna foto falla,
  los registros ya guardados permanecen; comprobar el catálogo antes de reintentar.
- El almacenamiento gratuito tiene límites. Evaluar costes y retención de datos
  antes de usar bibliotecas masivas o sensibles.
