# main.py
import threading

import webview

from api import Api
from webapp import flask_app, set_api_instance
from websocket_server import start_ws_server
from rfid_monitor import start_rfid_serial_monitor


def start_http_server():
    print("HTTP-Server auf http://0.0.0.0:8000")
    flask_app.run(host="0.0.0.0", port=8000)


def main():
    api = Api()
    set_api_instance(api)

    threading.Thread(target=start_ws_server, daemon=True).start()
    threading.Thread(target=start_http_server, daemon=True).start()

    threading.Thread(
        target=start_rfid_serial_monitor,
        args=(api, "/dev/ttyUSB0"),
        daemon=True,
    ).start()

    window = webview.create_window(
        "Mini-EAN-Scanner",
        url="http://127.0.0.1:8000/desktop",
        js_api=api,
        width=800,
        height=600,
        fullscreen=True,
    )
    webview.start(debug=True)


if __name__ == "__main__":
    main()
