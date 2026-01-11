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
from PIL import Image
from io import BytesIO
import websockets
from websockets import exceptions as ws_exceptions
import requests
import imghdr
import mysql.connector
from mysql.connector import Error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "products.db")
IMAGE_DIR = os.path.join(BASE_DIR, "images")
VIEWS_DIR = os.path.join(BASE_DIR, "views")
MOBILE_VIEWS_DIR = os.path.join(BASE_DIR, "mobile_views")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
MOBILE_URL = "http://192.168.0.30:8000/mobile"

DB_CONFIG = {
    "host": "localhost",
    "user": "wawi_user",        # anpassen
    "password": "poke",# anpassen
    "database": "wawi_b7",
}


os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIEWS_DIR, exist_ok=True)
os.makedirs(MOBILE_VIEWS_DIR, exist_ok=True)

# >>> LEGER HIN: images/dummy.png (z.B. graues 200x200 PNG)
DUMMY_IMAGE_PATH = os.path.join(IMAGE_DIR, "dummy.png")


# ----------------- SQLite-DB (ean + name + image_path) -----------------

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

class Api:
    def __init__(self):
        pass

    def _db_get_product(self, ean: str):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT ean, name, image_path
            FROM items
            WHERE ean = %s
        """, (ean,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            return {
                "ean": row[0],
                "name": row[1],
                "image_path": row[2] or ""
            }
        return None

    def _db_save_product(self, ean: str, name: str, image_path: str | None = None):
        conn = get_db_connection()
        cur = conn.cursor()

        # vorhandenen image_path beibehalten, wenn keiner mitkommt
        cur.execute("SELECT image_path FROM items WHERE ean = %s", (ean,))
        row = cur.fetchone()
        if row and image_path is None:
            image_path = row[0]

        cur.execute("""
            INSERT INTO items (ean, name, image_path)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                image_path = VALUES(image_path)
        """, (ean, name, image_path))

        conn.commit()
        cur.close()
        conn.close()

    def update_product_name(ean: str, name: str) -> None:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM items WHERE ean = %s", (ean,))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE items SET name = %s WHERE ean = %s", (name, ean))
        else:
            cur.execute("""
                INSERT INTO items (ean, name, image_path)
                VALUES (%s, %s, %s)
            """, (ean, name, None))
        conn.commit()
        cur.close()
        conn.close()
        print(f"[update_product_name] EAN={ean}, name={name}")




    def lookup_ean(self, ean: str, use_online: bool = False):
        ean = (ean or "").strip()
        if not ean:
            return {"ean": "", "name": "", "image_path": ""}

        # 1) zuerst MySQL items
        row = self._db_get_product(ean)
        if row:
            return row

        # 2) optional externe Datenbanken
        if use_online:
            online = self._lookup_ean_online(ean)  # falls du das schon implementiert hast
            if online:
                name = online.get("name", "").strip()
                if name:
                    self._db_save_product(ean, name)
                    return {"ean": ean, "name": name, "image_path": ""}

        # 3) nichts gefunden
        return {"ean": ean, "name": "", "image_path": ""}



    def _lookup_ean_online(self, ean: str) -> dict | None:
        """
        Versucht, Produktdaten aus kostenlosen / offenen EAN-Datenbanken zu holen.
        Aktuell:
          1. OpenFoodFacts (Lebensmittel, komplett offen & kostenlos)
        Rückgabe:
          dict mit mind. {"name": "..."} oder None
        """
        # --- 1) OpenFoodFacts ---
        try:
            url = f"https://world.openfoodfacts.net/api/v2/product/{ean}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # laut Doku: status=1 → gefunden, status=0 → nicht gefunden :contentReference[oaicite:2]{index=2}
                if data.get("status") == 1:
                    product = data.get("product", {}) or {}
                    # verschiedene Felder testen, falls product_name leer ist
                    name = (
                        product.get("product_name")
                        or product.get("product_name_de")
                        or product.get("generic_name")
                        or product.get("generic_name_de")
                        or ""
                    ).strip()

                    if name:
                        return {
                            "name": name,
                            "source": "openfoodfacts"
                        }
        except Exception as exc:
            print(f"[lookup_online] OpenFoodFacts Fehler für {ean}: {exc}")

        # --- 2) Platz für weitere kostenlose Datenbanken ---
        # Hier könntest du später z.B. OpenGTINDB ergänzen, wenn du dir eine
        # eigene QueryID besorgt hast. Beispiel-Skizze:
        #
        # try:
        #     url = f"https://opengtindb.org/?ean={ean}&cmd=query&queryid=DEINE_QUERY_ID"
        #     resp = requests.get(url, timeout=5)
        #     if resp.status_code == 200:
        #         text = resp.text
        #         # text/plain-Format mit Zeilen "name=..." etc. parsen
        #         info = self._parse_opengtindb(text)
        #         if info.get("name"):
        #             return {
        #                 "name": info["name"],
        #                 "source": "opengtindb"
        #             }
        # except Exception as exc:
        #     print(f"[lookup_online] OpenGTINDB Fehler für {ean}: {exc}")

        # Wenn nichts gefunden wurde:
        return None


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
    Speichert ein JPEG-Bild für diese EAN unter images/<ean>.jpg,
    skaliert auf max. 800px Kantenlänge und ca. 70% Qualität.
    Aktualisiert products.image_path. Gibt den Dateipfad zurück.
    """
    # Base64 -> Bytes
    img_bytes = base64.b64decode(image_b64)

    # Bytes mit Pillow öffnen
    try:
        img = Image.open(BytesIO(img_bytes))
    except Exception as exc:
        print(f"[save_image_for_ean] Fehler beim Öffnen des Bildes für EAN={ean}: {exc}")
        # Fallback: Raw-Bytes trotzdem speichern (nicht schön, aber besser als nichts)
        filename_raw = f"{ean}_raw.bin"
        filepath_raw = os.path.join(IMAGE_DIR, filename_raw)
        with open(filepath_raw, "wb") as f:
            f.write(img_bytes)
        return filepath_raw

    # In einheitliches Format bringen
    img = img.convert("RGB")

    # Runterskalieren: lange Seite max. 800px
    max_size = 800
    w, h = img.size
    if max(w, h) > max_size:
        img.thumbnail((max_size, max_size), Image.LANCZOS)

    # Ziel-Datei
    filename = f"{ean}.jpg"
    filepath = os.path.join(IMAGE_DIR, filename)

    os.makedirs(IMAGE_DIR, exist_ok=True)
    # JPEG mit mittlerer Qualität speichern
    img.save(filepath, format="JPEG", quality=70)

    print(f"[save_image_for_ean] EAN={ean}, gespeichert: {filepath}, size={os.path.getsize(filepath)} bytes, orig={w}x{h}")

    # In der DB den Pfad hinterlegen / aktualisieren
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM items WHERE ean = %s", (ean,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE items SET image_path = %s WHERE ean = %s", (filepath, ean))
    else:
        cur.execute("""
            INSERT INTO items (ean, name, image_path)
            VALUES (%s, %s, %s)
        """, (ean, "", filepath))
    conn.commit()
    cur.close()
    conn.close()
    return filepath


def update_product_name(ean: str, name: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT ean FROM products WHERE ean = ?", (ean,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE products SET name = ? WHERE ean = ?", (name, ean))
    else:
        cur.execute("""
            INSERT INTO products (ean, name, image_path)
            VALUES (?, ?, ?)
        """, (ean, name, None))
    conn.commit()
    conn.close()
    print(f"[update_product_name] EAN={ean}, name={name}")



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
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT image_path FROM items WHERE ean = %s", (ean,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    candidate = None
    if row and row[0]:
        candidate = row[0]

    if candidate and os.path.exists(candidate):
        print(f"[product_image] Serving {candidate} as image/jpeg")
        return send_file(candidate, mimetype="image/jpeg")

    print(f"[product_image] No image for {ean}, using dummy {DUMMY_IMAGE_PATH}")
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

def get_image_base64_for_ean(ean: str) -> str | None:
    """
    Liest images/<ean>.jpg, falls vorhanden, und gibt Base64-String zurück.
    """
    candidate = os.path.join(IMAGE_DIR, f"{ean}.jpg")
    if os.path.exists(candidate):
        with open(candidate, "rb") as f:
            img_bytes = f.read()
        return base64.b64encode(img_bytes).decode("ascii")
    return None

async def ws_handler(websocket):
    global last_article
    connected_clients.add(websocket)
    print("[ws_handler] Client verbunden")
    try:
        async for message in websocket:
            # Rohdaten-Länge loggen
            try:
                print(f"[ws_handler] raw message length: {len(message)}")
            except TypeError:
                # falls es binär wäre
                print(f"[ws_handler] received non-text message of type {type(message)}")

            # JSON parsen
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                print("[ws_handler] JSONDecodeError, Nachricht ignoriert")
                continue

            msg_type = data.get("type")
            print(f"[ws_handler] msg_type = {msg_type}")

            if msg_type == "set_article":
                # kommt vom Desktop
                ean = data.get("ean", "")
                name = data.get("name", "")
                last_article = {"ean": ean, "name": name}
                print(f"[ws_handler] set_article: ean={ean}, name={name}")

                image_b64 = get_image_base64_for_ean(ean) if ean else None

                msg = {
                    "type": "current_article",
                    "ean": ean,
                    "name": name,
                }
                if image_b64:
                    msg["image_base64"] = image_b64
                    print(f"[ws_handler] set_article: image_base64 length={len(image_b64)}")

                await broadcast(msg)

            elif msg_type == "request_current_article":
                print("[ws_handler] request_current_article")
                if last_article:
                    ean = last_article.get("ean", "")
                    name = last_article.get("name", "")
                    image_b64 = get_image_base64_for_ean(ean) if ean else None

                    msg = {
                        "type": "current_article",
                        "ean": ean,
                        "name": name,
                    }
                    if image_b64:
                        msg["image_base64"] = image_b64
                        print(f"[ws_handler] current_article: image_base64 length={len(image_b64)}")

                    await websocket.send(json.dumps(msg))

            elif msg_type == "upload_image":
                print("[ws_handler] upload_image empfangen")
                ean = data.get("ean", "").strip()
                image_b64 = data.get("image_base64", "")
                print(f"[ws_handler] upload_image: ean={ean}, b64len={len(image_b64)}")

                if not ean or not image_b64:
                    print("[ws_handler] upload_image: ean oder image_base64 fehlt")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "ean und image_base64 erforderlich"
                    }))
                    continue

                filepath = save_image_for_ean(ean, image_b64)
                print(f"[ws_handler] upload_image: gespeichert unter {filepath}")

                msg = {
                    "type": "image_updated",
                    "ean": ean,
                    "image_path": filepath,
                    "timestamp": int(time.time()),
                    "image_base64": image_b64,
                }
                await broadcast(msg)
                print("[ws_handler] upload_image: image_updated broadcastet")

            elif msg_type == "save_name":
                print("[ws_handler] save_name empfangen")
                ean = data.get("ean", "").strip()
                name = data.get("name", "").strip()
                print(f"[ws_handler] save_name: ean={ean}, name={name}")

                if not ean:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "ean erforderlich"
                    }))
                    continue

                update_product_name(ean, name)

                # last_article aktualisieren
                last_article = {"ean": ean, "name": name}

                # Bild (falls vorhanden)
                image_b64 = get_image_base64_for_ean(ean) if ean else None

                msg = {
                    "type": "current_article",
                    "ean": ean,
                    "name": name,
                }
                if image_b64:
                    msg["image_base64"] = image_b64

                await broadcast(msg)
                print("[ws_handler] save_name: current_article broadcastet")


            else:
                print(f"[ws_handler] Unbekannter msg_type: {msg_type}")

    finally:
        connected_clients.discard(websocket)
        print("[ws_handler] Client getrennt")



def start_ws_server():
    async def main_ws():
        print("WS-Server auf ws://0.0.0.0:8765")
        async with websockets.serve(
            ws_handler,
            "0.0.0.0",
            8765,
            max_size=None, 
        ):
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
		fullscreen=True
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
