import os
import threading
import asyncio
import json
import sqlite3
import base64
import time

import webview
from flask import Flask, send_from_directory, send_file
import qrcode
from io import BytesIO
import websockets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "products.db")
IMAGE_DIR = os.path.join(BASE_DIR, "images")
VIEWS_DIR = os.path.join(BASE_DIR, "views")
MOBILE_VIEWS_DIR = os.path.join(BASE_DIR, "mobile_views")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
MOBILE_URL = "http://192.168.0.30:8000/mobile"


os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIEWS_DIR, exist_ok=True)
os.makedirs(MOBILE_VIEWS_DIR, exist_ok=True)

# >>> LEGER HIN: images/dummy.png (z.B. graues 200x200 PNG)
DUMMY_IMAGE_PATH = os.path.join(IMAGE_DIR, "dummy.png")


# ----------------- SQLite-DB (ean + name + image_path) -----------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            ean TEXT PRIMARY KEY,
            name TEXT
        )
    """)
    # image_path nachrüsten, falls alte DB ohne Spalte
    try:
        cur.execute("ALTER TABLE products ADD COLUMN image_path TEXT")
    except sqlite3.OperationalError:
        # Spalte existiert schon -> egal
        pass
    conn.commit()
    conn.close()


class Api:
    def __init__(self):
        init_db()

    def _db_get_product(self, ean: str):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT ean, name, image_path FROM products WHERE ean = ?", (ean,))
        row = cur.fetchone()
        conn.close()
        if row:
            return {"ean": row[0], "name": row[1], "image_path": row[2] or ""}
        return None

    def _db_save_product(self, ean: str, name: str, image_path: str | None = None):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # vorhandenen image_path erhalten, wenn keiner übergeben wird
        cur.execute("SELECT image_path FROM products WHERE ean = ?", (ean,))
        row = cur.fetchone()
        if row and image_path is None:
            image_path = row[0]

        cur.execute("""
            INSERT OR REPLACE INTO products (ean, name, image_path)
            VALUES (?, ?, ?)
        """, (ean, name, image_path))
        conn.commit()
        conn.close()

    # wird von index.html per pywebview aufgerufen
    def lookup_ean(self, ean: str):
        ean = (ean or "").strip()
        if not ean:
            return {"ean": "", "name": "", "image_path": ""}

        row = self._db_get_product(ean)
        if row:
            return row
        else:
            # wenn nichts in der DB: "leerer" Datensatz zurückgeben
            return {"ean": ean, "name": "", "image_path": ""}

    def save_product(self, ean: str, name: str):
        ean = (ean or "").strip()
        name = (name or "").strip()
        if not ean:
            return {"ok": False, "message": "EAN fehlt"}
        self._db_save_product(ean, name)
        return {"ok": True, "message": "Gespeichert"}


# ----------------- Bildspeicherung für Mobile-Upload -----------------

def save_image_for_ean(ean: str, image_b64: str) -> str:
    """
    Speichert ein JPEG-Bild für diese EAN unter images/<ean>.jpg
    und aktualisiert products.image_path. Gibt den Dateipfad zurück.
    """
    img_bytes = base64.b64decode(image_b64)
    filename = f"{ean}.jpg"
    filepath = os.path.join(IMAGE_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(img_bytes)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT ean FROM products WHERE ean = ?", (ean,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE products SET image_path = ? WHERE ean = ?", (filepath, ean))
    else:
        # Falls Produkt noch nicht in DB: Dummy-Name, nur Bild
        cur.execute("""
            INSERT INTO products (ean, name, image_path)
            VALUES (?, ?, ?)
        """, (ean, "", filepath))
    conn.commit()
    conn.close()
    return filepath


# ----------------- Flask: mobile.html + Bild-Endpoint -----------------

flask_app = Flask(
    __name__,
    static_folder=PUBLIC_DIR,
    static_url_path="/public"
)


@flask_app.route("/")
def root():
    return "<h1>Server läuft</h1><p>Mobile: /mobile aufrufen.</p>"


@flask_app.route("/mobile")
def mobile_page():
    return send_from_directory(MOBILE_VIEWS_DIR, "mobile.html")


@flask_app.route("/image/<ean>")
def product_image(ean):
    # Versuchen, ein spezielles Bild für diese EAN zu finden
    candidate = os.path.join(IMAGE_DIR, f"{ean}.jpg")
    if os.path.exists(candidate):
        return send_file(candidate, mimetype="image/jpeg")
    # sonst Dummy
    return send_file(DUMMY_IMAGE_PATH, mimetype="image/png")

@flask_app.route("/desktop")
def desktop_page():
    return send_from_directory(VIEWS_DIR, "index.html")

@flask_app.route("/qr")
def mobile_qr():
    """
    Liefert einen PNG-QR-Code, der auf MOBILE_URL zeigt.
    """
    img = qrcode.make(MOBILE_URL)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

# ----------------- WebSocket: Desktop <-> Mobile -----------------

connected_clients = set()
last_article = None  # {"ean": "...", "name": "..."}


async def broadcast(message_dict):
    if not connected_clients:
        return
    data = json.dumps(message_dict)
    dead = []
    for ws in connected_clients:
        try:
            await ws.send(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.discard(ws)


async def ws_handler(websocket):
    global last_article
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "set_article":
                # kommt vom Desktop
                ean = data.get("ean", "")
                name = data.get("name", "")
                last_article = {"ean": ean, "name": name}
                await broadcast({"type": "current_article", **last_article})

            elif msg_type == "request_current_article":
                # kommt vom Handy beim Verbinden
                if last_article:
                    await websocket.send(json.dumps({
                        "type": "current_article",
                        **last_article
                    }))

            elif msg_type == "upload_image":
                # kommt vom Handy: neues Foto
                ean = data.get("ean", "").strip()
                image_b64 = data.get("image_base64", "")
                if not ean or not image_b64:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "ean und image_base64 erforderlich"
                    }))
                    continue

                filepath = save_image_for_ean(ean, image_b64)
                # allen sagen, dass das Bild aktualisiert wurde
                await broadcast({
                    "type": "image_updated",
                    "ean": ean,
                    "image_path": filepath,
                    "timestamp": int(time.time())
                })

    finally:
        connected_clients.discard(websocket)


def start_ws_server():
    async def main_ws():
        print("WS-Server auf ws://0.0.0.0:8765")
        async with websockets.serve(ws_handler, "0.0.0.0", 8765):
            await asyncio.Future()  # läuft dauerhaft

    asyncio.run(main_ws())


def start_http_server():
    print("HTTP-Server auf http://0.0.0.0:8000")
    flask_app.run(host="0.0.0.0", port=8000)


# ----------------- pywebview starten -----------------

def main():
    api = Api()

    threading.Thread(target=start_ws_server, daemon=True).start()
    threading.Thread(target=start_http_server, daemon=True).start()

    index_html_path = os.path.join(VIEWS_DIR, "index.html")

    window = webview.create_window(
        "Mini-EAN-Scanner",
        url="http://127.0.0.1:8000/desktop",
        js_api=api,
        width=800,
        height=600,
    )
    webview.start(debug=True)


if __name__ == "__main__":
    main()
