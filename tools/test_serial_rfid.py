#!/usr/bin/env python3
import serial

PORT = "/dev/ttyUSB0"
BAUD = 9600

print(f"Öffne {PORT} @ {BAUD} ...")

with serial.Serial(PORT, BAUD, timeout=1) as ser:
    print("Warte auf Zeilen vom Arduino (Strg+C zum Abbruch)...")
    while True:
        line = ser.readline().decode(errors="ignore").strip()
        if not line:
            continue
        print(">>", repr(line))
