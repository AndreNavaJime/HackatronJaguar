/*
  PantheraSENSE 1.5 — ESP32 + DHT22 + LED + FastAPI (PRUEBAS)
  Proyecto y diseño: Andrea Navarro Jimenez (2026)

  Wokwi (simulado, NO sensor de campo).
  ESP32: LED GPIO 2 / DHT22 SDA GPIO 21.
  IMPORTANTE: NO guardar una contraseña dentro de este archivo.
  Ingresar la clave TEMPORAL en el monitor serial durante la simulacion.
*/
#include <DHTesp.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

const int LED_PIN = 2;
const int DHT_PIN = 21;
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";
const char* API_URL = "https://pantherasense-backend-test.onrender.com/api/sense/ingest";
const char* DEVICE_ID = "PANTHERASENSE-01";
const unsigned long ENVIO_MS = 30000;
const unsigned long WIFI_RETRY_MS = 15000;

// Solo memoria RAM: la clave NO se guarda en el codigo ni en la microSD.
String temporaryKey = "";
DHTesp sensor;
unsigned long contador = 0;
unsigned long ultimoEnvio = 0;
unsigned long ultimoIntentoWiFi = 0;
bool envioInicialPendiente = true;

void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  ultimoIntentoWiFi = millis();
  Serial.println("Conectando a Wokwi-GUEST...");
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);

  unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - inicio < 12000) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi conectado. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi no disponible. Reintentaremos sin perder el sensor.");
  }
}

void leerClavePorSerial() {
  if (!Serial.available()) return;
  String entrada = Serial.readStringUntil('\n');
  entrada.trim();
  if (entrada.length() < 16 || entrada.length() > 200) {
    Serial.println("Clave no aceptada: se requieren 16 a 200 caracteres.");
    return;
  }
  temporaryKey = entrada;
  envioInicialPendiente = true;
  Serial.println("CLAVE TEMPORAL CARGADA SOLO EN MEMORIA.");
  Serial.println("No compartas una captura mostrando la clave.");
}

void enviarMedicion(float temperatura, float humedad) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("SIN ENVIO: Wi-Fi desconectado.");
    return;
  }
  if (temporaryKey.length() < 16) {
    Serial.println("SIN ENVIO: falta introducir la clave en el monitor serial.");
    return;
  }

  String json = "{";
  json += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  json += "\"project\":\"PantheraSENSE\",";
  json += "\"simulation\":true,";
  json += "\"temperature_c\":" + String(temperatura, 1) + ",";
  json += "\"humidity_pct\":" + String(humedad, 1) + ",";
  json += "\"uptime_s\":" + String(millis() / 1000) + ",";
  json += "\"reading_number\":" + String(contador);
  json += "}";

  Serial.println("ENVIO SIMULADO A FASTAPI:");
  Serial.println(json);

  WiFiClientSecure client;
  // Solo para demostracion en Wokwi; verificar CA real en produccion.
  client.setInsecure();
  HTTPClient http;
  http.setTimeout(12000);
  if (!http.begin(client, API_URL)) {
    Serial.println("Error al iniciar conexion HTTPS.");
    return;
  }

  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-PantheraSense-Key", temporaryKey);
  int codigo = http.POST(json);
  http.end();

  Serial.print("Respuesta HTTP: ");
  Serial.println(codigo);
  if (codigo == 202) {
    Serial.println("MEDICION RECIBIDA POR PANTHERASENSE EN RENDER");
  } else if (codigo == 401) {
    Serial.println("Clave incorrecta: revisar valor en Render.");
  } else if (codigo == 503) {
    Serial.println("Servidor sin clave de recepcion configurada.");
  } else if (codigo < 0) {
    Serial.println("Fallo de conexion HTTPS. Verificar Wi-Fi / Gateway Wokwi.");
  } else {
    Serial.println("Servidor devolvio error. Revisar respuesta HTTP.");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(250);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  sensor.setup(DHT_PIN, DHTesp::DHT22);
  delay(1000);
  Serial.println("=======================================");
  Serial.println(" PantheraSENSE · Andrea Navarro Jimenez");
  Serial.println(" WOKWI · PRUEBAS · VERSION 1.5");
  Serial.println("=======================================");
  conectarWiFi();
  Serial.println("Pega tu clave TEMPORAL de Render en el monitor serial");
  Serial.println("y presiona ENTER. No se guarda en sketch.ino.");
}

void loop() {
  leerClavePorSerial();
  if (WiFi.status() != WL_CONNECTED &&
      millis() - ultimoIntentoWiFi >= WIFI_RETRY_MS) {
    conectarWiFi();
  }

  digitalWrite(LED_PIN, HIGH);
  delay(1000);
  digitalWrite(LED_PIN, LOW);
  delay(1000);

  TempAndHumidity datos = sensor.getTempAndHumidity();
  contador++;
  if (isnan(datos.temperature) || isnan(datos.humidity)) {
    Serial.println("ERROR: DHT22 sin datos.");
    return;
  }

  Serial.print("Temperatura: ");
  Serial.print(datos.temperature, 1);
  Serial.print(" C, humedad: ");
  Serial.print(datos.humidity, 1);
  Serial.println(" %");

  if (envioInicialPendiente || millis() - ultimoEnvio >= ENVIO_MS) {
    if (temporaryKey.length() >= 16 && WiFi.status() == WL_CONNECTED) {
      ultimoEnvio = millis();
      envioInicialPendiente = false;
      enviarMedicion(datos.temperature, datos.humidity);
    } else {
      Serial.println("Esperando Wi-Fi y clave temporal para el primer envio...");
    }
  }
}
