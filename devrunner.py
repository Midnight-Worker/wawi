#!/usr/bin/env python3
import subprocess
import threading
import sys
import os
import signal
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CMD = [sys.executable, os.path.join(BASE_DIR, "app.py")]

restart_requested = False
stop_requested = False


def stdin_loop():
    """
    Liest Eingaben vom Terminal:

    rs + Enter -> app.py neu starten
    q  + Enter -> alles beenden (app.py + X, wenn über startx gestartet)
    """
    global restart_requested, stop_requested

    print("Dev-Control: 'rs' = restart app, 'q' = quit")
    for line in sys.stdin:
        cmd = line.strip()
        if cmd == "rs":
            print("Restart angefordert...")
            restart_requested = True
        elif cmd == "q":
            print("Beenden angefordert...")
            stop_requested = True
            break


def main():
    global restart_requested, stop_requested

    t = threading.Thread(target=stdin_loop, daemon=True)
    t.start()

    while not stop_requested:
        print("Starte app.py ...")
        proc = subprocess.Popen(CMD)

        # Solange app läuft und kein Restart/Stop angefordert ist
        while proc.poll() is None and not restart_requested and not stop_requested:
            time.sleep(0.2)

        # Wenn noch läuft -> freundlich beenden
        if proc.poll() is None:
            print("Beende laufende app.py ...")
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("app.py reagiert nicht, kill -9 ...")
                proc.kill()

        if stop_requested:
            print("Stop requested, Supervisor endet.")
            break

        if restart_requested:
            # Flag zurücksetzen und Schleife neu -> app.py wird neu gestartet
            restart_requested = False
            print("Starte app.py neu ...")
            continue

        # Falls app.py einfach so ausgestiegen ist (Crash o.ä.),
        # direkt wieder hochfahren nach kurzer Pause:
        print("app.py beendet. Starte in 2 Sekunden neu (oder 'q' zum Beenden).")
        time.sleep(2)


if __name__ == "__main__":
    main()

