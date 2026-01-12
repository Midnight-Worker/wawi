#!/usr/bin/env python3
import time

import nfc  # nfcpy


def on_connect(tag):
    print("======================================")
    print("Tag erkannt:", tag)

    uid_hex = None
    if hasattr(tag, "identifier"):
        try:
            uid_hex = tag.identifier.hex()
        except Exception:
            pass

    if uid_hex:
        print("UID (hex):", uid_hex)
    else:
        print("Konnte UID nicht ermitteln.")

    print("Bitte Karte wieder entfernen…")
    print("======================================")
    return True  # danach auf on_release warten


def on_release(tag):
    print("Tag entfernt.")
    return


def main():
    while True:
        try:
            # WICHTIG: explizit deine VID:PID nutzen
            # Alternative 1: 'usb'
            # Alternative 2: 'usb:072f:2200'
            print("Öffne ACR122 über nfc.ContactlessFrontend…")
            with nfc.ContactlessFrontend('usb:072f:2200') as clf:
                print("Warte auf Karte… (Strg+C zum Abbruch)")
                clf.connect(rdwr={
                    "on-connect": on_connect,
                    "on-release": on_release,
                })
        except KeyboardInterrupt:
            print("Abbruch durch Benutzer.")
            break
        except Exception as e:
            print("Fehler:", e)
            print("Retry in 2 Sekunden…")
            time.sleep(2)


if __name__ == "__main__":
    main()

