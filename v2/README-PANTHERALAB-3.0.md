# PantheraLAB 3.0 — Blue Edition

**De la intuición a la evidencia**

Plataforma web instalable (PWA) de investigación de fauna y cámaras trampa. Esta edición utiliza un diseño azul eléctrico/cian y el arte del jaguar aportado para la identidad visual de PantheraLAB 3.0.

## Autoría y condiciones de uso

**Diseño y desarrollo de la aplicación: Andrea Navarro Jiménez (2026).**

- [AUTORÍA Y CRÉDITOS](AUTHORS.md)
- [CONDICIONES DE USO RESTRINGIDO](LICENSE-PANTHERALAB-3.0.md)

**El paquete puede entregarse para evaluación privada, pero esa entrega no concede licencia para reutilizar, redistribuir, comercializar ni presentarse como autor/a del trabajo original de Andrea.** Los derechos y licencias de otras personas o componentes siguen siendo independientes. En usos profesionales o comerciales, confirmar titularidad y acuerdos aplicables.

## Independencia de versiones

- **PantheraLAB 3.0:** rama `pantheralab-3.0`. Diseño, manifiesto PWA e iconos independientes.
- **PantheraLAB 2.0:** rama `pantheraid-v2`, mantenida sin cambios.
- **API de análisis:** la edición 3.0 se configura inicialmente para utilizar el mismo backend FastAPI de Render. El ZIP no incluye acceso administrativo ni credenciales.

## Funcionalidades

- **PantheraID:** inspección de fotografías y análisis exploratorio de videos, fotogramas, revisión y evidencias.
- **PantheraMONITORING:** estudios, estaciones, capturas, individuos, observaciones e informes científicos.
- **PantheraEDGE:** interfaz de recepción/consulta de eventos según capacidades disponibles.
- **Investigación:** exploración de resultados e informes.
- **PWA:** instalación desde Chrome/Android o Safari/iOS cuando se publique en un origen HTTPS válido.

No se garantiza identificación automática individual validada ni disponibilidad de módulos de IA no instalados. Los archivos temporales de Render pueden caducar. Los datos de investigación almacenados localmente **no se sincronizan automáticamente entre dispositivos**.

## Desarrollo y compilación

```bash
cd v2/frontend
npm install
npm run build
```

El directorio de publicación es `v2/frontend/dist`; los recursos específicos de marca se encuentran en `v2/frontend/public/branding` e `icons`, y los estilos en `v2/frontend/src/panthera3.css`. La aplicación utiliza las rutas `/api/*` hacia FastAPI de Render según `v2/frontend/vercel.json`.

## Antes de compartir un ZIP

1. Incluir este README, `AUTHORS.md` y `LICENSE-PANTHERALAB-3.0.md`.
2. No incluir secretos, tokens, archivos `.env`, datos personales, localizaciones sensibles de fauna ni sesiones privadas.
3. Respetar derechos de autor, atribuciones y licencias de dependencias, modelos y recursos gráficos de terceros.
4. Entregar solamente a personas autorizadas y documentar el propósito de evaluación.

**Estado del despliegue:** la edición 3.0 se preparó en GitHub; la publicación independiente en Vercel requiere completarse y verificarse aparte.
