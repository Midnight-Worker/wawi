# rfid_monitor.py
import time
import serial

def start_rfid_serial_monitor(api, port: str = "/dev/ttyUSB0", baudrate: int = 9600):
    print(f"[rfid-serial] Starte Monitor auf {port} @ {baudrate}")

    while True:
        try:
            with serial.Serial(port, baudrate, timeout=1) as ser:
                print("[rfid-serial] Serial geöffnet, warte auf UIDs…")
                while True:
                    line = ser.readline().decode(errors="ignore").strip()
                    if not line:
                        continue

                    print(f"[rfid-serial] Zeile empfangen: {line}")

                    if not line.startswith("RFID:"):
                        continue

                    uid = line[5:].strip()
                    if not uid:
                        continue

                    result = api.rfid_login(uid)
                    if not result.get("ok"):
                        print(f"[rfid-serial] UID {uid} nicht in users, ignoriere.")
                        continue

                    print(
                        f"[rfid-serial] Login: {result['user_name']} "
                        f"(id={result['user_id']}), Timeout={api.session_timeout_minutes} min"
                    )

        except serial.SerialException as e:
            print(f"[rfid-serial] Fehler auf {port}: {e}. Neuer Versuch in 3s…")
            time.sleep(3)
        except Exception as e:
            print(f"[rfid-serial] Unerwarteter Fehler im Serial-Monitor: {e}. Neuer Versuch in 3s…")
            time.sleep(3)
