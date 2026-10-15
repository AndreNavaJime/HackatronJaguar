# PantheraSENSE 2.0 · Telemetría y alertas ambientales simuladas

**Prototipo experimental de Andrea Navarro Jiménez.** Integrado con PantheraEDGE en la rama `pantherasense-integration`, independiente de la versión principal `pantheraid-v2`. No es un sistema de emergencia operativo.

## Funcionalidad

- **Sin Wokwi abierto:** `GET /api/sense/latest` calcula temperatura y humedad sintéticas bajo demanda mediante la API experimental de Render. No simula incendios espontáneamente ni envía alertas reales. No hay tareas permanentes, almacenamiento científico ni monitoreo real 24/7.
- **Con Wokwi:** `POST /api/sense/ingest`, autenticado con `X-PantheraSense-Key`, acepta mediciones DHT22 virtuales con `simulation:true`. El nuevo campo **opcional** `gas_alert` (booleano) transmite la salida digital simulada del MQ-2. Los sketches anteriores sin ese campo siguen funcionando.
- **Panel de incidentes:** una señal `gas_alert:true` procedente de Wokwi muestra una alerta de simulación en el panel. La siguiente lectura normal la desactiva. El botón **Simular alerta de gases** reproduce localmente el aviso sin modificar datos compartidos en Render, y **Finalizar simulacro** lo quita.
- **Preferencia de origen:** cuando llegan lecturas Wokwi recientes, la API las prioriza; después de 150 segundos sin nuevas lecturas, vuelve a mostrar valores sintéticos de la nube.
- **Tabla de mediciones:** conserva temperatura, humedad y estado MQ-2. Los mensajes se actualizan mediante consultas del navegador cada 15 segundos.

## Circuito Wokwi

Esta carpeta tiene dos archivos de referencia para el **mismo ESP32**, no un proyecto independiente:

- [`sketch.ino`](sketch.ino): DHT22 en GPIO21, LED en GPIO2 y **MQ-2 digital DO en GPIO27**. Usa HTTPS con 20 segundos para conectar y 60 segundos para recibir respuesta.
- [`diagram.json`](diagram.json): ejemplo de circuito compatible con el sketch, con alimentación, LED y resistencia.

En el proyecto Wokwi que ya está abierto, reemplazar el sketch y añadir los cables/componentes equivalentes en `diagram.json`. GitHub no modifica automáticamente ningún proyecto alojado en Wokwi. Ajustar la concentración simulada y el umbral digital del MQ-2 hasta que DO pase a LOW; se enviará `gas_alert:true` en la siguiente lectura programada (~30 segundos). **Un MQ-2 registra gases combustibles: su alerta no confirma humo, llama, incendio ni ubicación cercana a una cámara.**

**Advertencia eléctrica:** estos cables son un ejemplo **exclusivo del simulador**. El módulo MQ-2 puede trabajar con 5 V; en un equipo físico, sus señales eléctricas deben adaptarse a los niveles seguros del ESP32. No conectar directamente el DO de 5 V a un GPIO de 3,3 V sin comprobar compatibilidad/protección. En hardware real se necesita calibración, verificación de certificados TLS, protección de secretos, energía fiable y pruebas de falsas alarmas.

## Seguridad y procedencia

La clave `PANTHERASENSE_INGEST_KEY` se configura **solo** como secreto en Render y se introduce interactivamente en el monitor serial de Wokwi; nunca se guarda en el repositorio. El endpoint de ingestión falla cerrado sin clave o ante una clave incorrecta, exige `simulation:true` y rechaza campos como coordenadas. Máximo 30 mensajes autenticados en RAM (se pierden al reiniciar Render); el historial público muestra hasta 12.

La **demostración de alarma local** no llama a la API, no persiste y no se notifica a otros dispositivos. No se vincula automáticamente a `CAM-01`, ni a ubicaciones registradas, ni a cuerpos de emergencia. La asociación con estaciones reales y un sistema de avisos verificado requieren un desarrollo posterior separado.

## Pruebas

```bash
cd v2/backend && python -m pytest -q test_sense_api.py
cd ../frontend && npm install --no-audit --no-fund && npm run build
```

Todos los valores y alertas de este módulo son simulados. No representan resultados de campo, detección automática de incendios ni comunicaciones 5G reales.
