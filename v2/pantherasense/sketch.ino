/*
  PANTHERASENSE 1.4 — INTEGRACION EXPERIMENTAL
  Diseño y desarrollo del proyecto: Andrea Navarro Jimenez (2026)

  ESP32 virtual + DHT22 (GPIO 21) + LED (GPIO 2)
  Envía valores SIMULADOS a un receptor FastAPI de pruebas.
  NO usar para fauna real sin validar equipo, seguridad y almacenamiento.

  NO PUBLICAR UNA CLAVE REAL en GitHub ni compartirla mediante Wokwi.
  El receptor exige una clave temporal exclusiva para estas pruebas.
*/
#include <DHTesp.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

const int LED_PIN = 2;
const int DHT_PIN = 21;

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";
const char* API_URL = "https://pantheraid-backend.onrender.com/api/sense/ingest";

// Pegar solo en una copia de pruebas NO compartida; no subir secretos a GitHub.
// Debe coincidir con PANTHERASENSE_INGEST_KEY en el servicio Render.
const char* API_KEY = "REEMPLAZAR_CON_CLAVE_TEMPORAL_PRIVADA";

const char* DEVICE_ID = "PANTHERASENSE-01";
const unsigned long ENVIO_MS = 30000;
const unsigned long WIFI_RETRY_MS = 12000;

DHTesp sensor;
unsigned long contador = 0;
unsigned long ultimoEnvio = 0;
unsigned long ultimoIntentoWifi = 0;
bool primeraLectura = true;

void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  ultimoIntentoWifi = millis();
  Serial.println("Conectando a Wokwi-GUEST...");
  WiFi.mode(WIFI_STA);
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
    Serial.println("Wi-Fi no disponible. Continuara midiendo y reintentara.");
  }
}

void enviarMedicion(float temperatura, float humedad) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Envio pendiente: sin Wi-Fi (demo sin almacenamiento de cola).");
    return;
  }
  if (String(API_KEY).startsWith("REEMPLAZAR_")) {
    Serial.println("Falta configurar la clave temporal del servidor.");
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

  Serial.println("ENVIO A FASTAPI: ");
  Serial.println(json);

  WiFiClientSecure client;
  // Solo Wokwi de demostracion: no verifica el certificado TLS.
  // Hardware real: configurar CA valida y autenticacion robusta.
  client.setInsecure();
  HTTPClient http;
  http.setTimeout(10000);

  if (!http.begin(client, API_URL)) {
    Serial.println("Error al iniciar HTTPS.");
    return;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-PantheraSense-Key", API_KEY);
  int code = http.POST(json);
  Serial.print("Resultado de envio: HTTP ");
  Serial.println(code);
  if (code == 202) {
    Serial.println("MEDICION ACEPTADA POR PANTHERASENSE");
  } else if (code == 401) {
    Serial.println("Clave incorrecta. Revisar Render/Wokwi.");
  } else if (code == 503) {
    Serial.println("Receptor sin configurar en Render.");
  } else if (code < 0) {
    Serial.println(http.errorToString(code));
  } else {
    Serial.println(http.getString());
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  sensor.setup(DHT_PIN, DHTesp::DHT22);
  delay(1000);
  Serial.println("=================================");
  Serial.println("  PANTHERASENSE · Andrea Navarro Jimenez");
  Serial.println("  SIMULACION WOKWI · VERSION 1.4");
  Serial.println("=================================");
  conectarWiFi();
}

void loop() {
  // Conservar el parpadeo original y consultar sensor cada 2 segundos.
  digitalWrite(LED_PIN, HIGH);
  delay(1000);
  digitalWrite(LED_PIN, LOW);
  delay(1000);

  if (WiFi.status() != WL_CONNECTED &&
      millis() - ultimoIntentoWifi >= WIFI_RETRY_MS) conectarWiFi();

  TempAndHumidity d = sensor.getTempAndHumidity();
  contador++;
  if (isnan(d.temperature) || isnan(d.humidity)) {
    Serial.println("DHT22: lectura invalida");
    return;
  }

  Serial.print("Temperatura: "); Serial.print(d.temperature, 1); Serial.println(" C");
  Serial.print("Humedad: "); Serial.print(d.humidity, 1); Serial.println(" %");

  if (primeraLectura || millis() - ultimoEnvio >= ENVIO_MS) {
    primeraLectura = false;
    ultimoEnvio = millis();
    enviarMedicion(d.temperature, d.humidity);
  }
}
