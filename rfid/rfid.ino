#include <SPI.h>
#include <MFRC522.h>

// Pin-Definitionen (an Nano anpassen)
constexpr uint8_t SS_PIN  = 10;  // SDA
constexpr uint8_t RST_PIN = 9;   // RST

MFRC522 mfrc522(SS_PIN, RST_PIN);

// Zum Erkennen, ob wir dieselbe Karte direkt hintereinander sehen
bool hasLastUid = false;
byte lastUid[10];
byte lastUidSize = 0;

void setup() {
  Serial.begin(9600);
  while (!Serial) {
    ; // warten bis USB bereit (bei Nano meist sofort ok)
  }

  SPI.begin();
  mfrc522.PCD_Init();

  Serial.println(F("RFID-Serial-Bridge gestartet."));
  Serial.println(F("Karte kurz auflegen zum An-/Abmelden."));
}

bool sameUid(const byte *a, byte aSize, const byte *b, byte bSize) {
  if (aSize != bSize) return false;
  for (byte i = 0; i < aSize; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}

void loop() {
  // Nur reagieren, wenn neue Karte gemeldet
  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
    delay(50);
    return;
  }

  byte *uid = mfrc522.uid.uidByte;
  byte uidSize = mfrc522.uid.size;

  // UID in Hex-String bauen
  char uidStr[32] = {0};
  char *p = uidStr;
  for (byte i = 0; i < uidSize; i++) {
    sprintf(p, "%02x", uid[i]);  // klein geschrieben
    p += 2;
  }

  // Nur senden, wenn es NICHT exakt dieselbe UID ist wie beim letzten Event
  // (damit nicht 5x hintereinander das Gleiche rausfällt, wenn man zuckt)
  if (!hasLastUid || !sameUid(lastUid, lastUidSize, uid, uidSize)) {
    Serial.print(F("RFID:"));
    Serial.println(uidStr);  // z. B. "RFID:35243d7b"

    memcpy(lastUid, uid, uidSize);
    lastUidSize = uidSize;
    hasLastUid = true;
  }

  mfrc522.PICC_HaltA();
  delay(200);
}

