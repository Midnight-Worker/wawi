import os
import threading
import asyncio
import json
import base64
import time

from io import BytesIO

import webview
from flask import Flask, send_file, send_from_directory, request, jsonify
import qrcode
import websockets

from PIL import Image

import mysql.connector
from mysql.connector import Error


# ------------------------------------------------------------
# Pfade & Basis-Konfiguration
# ------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, "images")
VIEWS_DIR = os.path.join(BASE_DIR, "views")
MOBILE_VIEWS_DIR = os.path.join(BASE_DIR, "mobile_views")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

# Mobile-URL für den QR-Code
MOBILE_URL = "http://192.168.0.30:8000/mobile"

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIEWS_DIR, exist_ok=True)
os.makedirs(MOBILE_VIEWS_DIR, exist_ok=True)

# Dummy-Bild (z. B. graues PNG 200x200)
DUMMY_IMAGE_PATH = os.path.join(IMAGE_DIR, "dummy.png")

# ------------------------------------------------------------
# MySQL/MariaDB Konfiguration
# ------------------------------------------------------------

DB_CONFIG = {
    "host": "localhost",
    "user": "wawi_user",        # ANPASSEN
    "password": "poke",# ANPASSEN
    "database": "wawi_b7",
}


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def init_db():
    """
    Aktuell nur Platzhalter: Die Tabellenstruktur liegt bereits in MySQL an.
    Hier könntest du später prüfen, ob items.ean / items.image_path existieren.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SHOW TABLES LIKE 'items'")
        row = cur.fetchone()
        if not row:
            print("[init_db] WARNUNG: Tabelle 'items' existiert nicht in wawi_b7.")
        cur.close()
        conn.close()
    except Error as e:
        print(f"[init_db] DB-Fehler: {e}")


# ------------------------------------------------------------
# Flask-App
# ------------------------------------------------------------

flask_app = Flask(
    __name__,
    static_folder=PUBLIC_DIR,
    static_url_path="/public"
)


@flask_app.route("/")
def root():
    return "<h1>Server läuft</h1><p>Desktop: /desktop, Mobile: /mobile</p>"


@flask_app.route("/desktop")
def desktop_page():
    return send_from_directory(VIEWS_DIR, "index.html")


@flask_app.route("/desktop_alt")
def desktop_alt_page():
    return send_from_directory(VIEWS_DIR, "desktop_alternative.html")



@flask_app.route("/mobile")
def mobile_page():
    return send_from_directory(MOBILE_VIEWS_DIR, "mobile.html")


@flask_app.route("/image/<ean>")
def product_image(ean):
    """
    Liefert das Bild zu einer EAN, falls in items.image_path hinterlegt.
    Sonst Dummy.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT image_path FROM items WHERE ean = %s", (ean,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    candidate = row[0] if row and row[0] else None

    if candidate and os.path.exists(candidate):
        print(f"[product_image] Serving {candidate} as image/jpeg")
        return send_file(candidate, mimetype="image/jpeg")

    print(f"[product_image] No image for {ean}, using dummy {DUMMY_IMAGE_PATH}")
    return send_file(DUMMY_IMAGE_PATH, mimetype="image/png")


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


@flask_app.route("/upload_image/<ean>", methods=["POST"])
def upload_image_http(ean):
    """
    HTTP-Upload-Endpunkt, falls du in mobile.js FormData + fetch() nutzt.
    Erwartet Multipart-Formular mit Feld 'image'.
    """
    ean = (ean or "").strip()
    if not ean:
        return jsonify({"ok": False, "message": "EAN fehlt"}), 400

    file = request.files.get("image")
    if not file:
        return jsonify({"ok": False, "message": "Kein Bild übermittelt"}), 400

    try:
        img_bytes = file.read()
        image_b64 = base64.b64encode(img_bytes).decode("ascii")

        filepath = save_image_for_ean(ean, image_b64)
        print(f"[upload_image_http] EAN={ean}, gespeichert unter {filepath}")

        # Nur JSON zurückgeben – Bild kommt über /image/<ean>
        return jsonify({"ok": True, "message": "Bild gespeichert", "ean": ean})
    except Exception as exc:
        print(f"[upload_image_http] Fehler bei EAN={ean}: {exc}")
        return jsonify({"ok": False, "message": "Fehler beim Speichern"}), 500


# ------------------------------------------------------------
# DB-Helferfunktionen für items (EAN, Name, Bild)
# ------------------------------------------------------------

def get_user_id_by_rfid(rfid_uid: str) -> int | None:
    """
    Liefert users.id zu einem RFID-Tag (users.rfid_uid) oder None.
    """
    if not rfid_uid:
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE rfid_uid = %s", (rfid_uid,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None

def update_product_name(ean: str, name: str, user_id: int | None = None) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM items WHERE ean = %s", (ean,))
    row = cur.fetchone()

    if row:
        cur.execute("""
            UPDATE items
            SET name = %s,
                last_user_id = %s,
                last_change_at = NOW()
            WHERE ean = %s
        """, (name, user_id, ean))
    else:
        cur.execute("""
            INSERT INTO items (ean, name, image_path, qty, last_user_id, last_change_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (ean, name, None, 0.000, user_id))

    conn.commit()
    cur.close()
    conn.close()
    print(f"[update_product_name] EAN={ean}, name={name}, user_id={user_id}")


class Api:
    def __init__(self):
        init_db()

    def _db_get_product(self, ean: str):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT ean, name, image_path, qty, shop_id, last_user_id, last_change_at
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
                "image_path": row[2] or "",
                "qty": float(row[3]) if row[3] is not None else 0.0,
                "shop_id": row[4],
                "last_user_id": row[5],
                "last_change_at": row[6].isoformat() if row[6] else None,
            }
        return None

    def _db_save_product(
        self,
        ean: str,
        name: str,
        shop_id: int | None,
        qty: float,
        last_user_id: int | None = None,
    ):
        conn = get_db_connection()
        cur = conn.cursor()

        # vorhandene Werte holen, um image_path nicht zu verlieren
        cur.execute("""
            SELECT image_path, qty, shop_id, last_user_id
            FROM items
            WHERE ean = %s
        """, (ean,))
        row = cur.fetchone()

        image_path = None
        if row:
            existing_image_path, existing_qty, existing_shop_id, existing_last_user_id = row
            image_path = existing_image_path
            if shop_id is None:
                shop_id = existing_shop_id
            if qty is None:
                qty = existing_qty if existing_qty is not None else 0.0
            if last_user_id is None:
                last_user_id = existing_last_user_id
        else:
            if qty is None:
                qty = 0.0

        cur.execute("""
            INSERT INTO items (ean, name, image_path, shop_id, qty, last_user_id, last_change_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                image_path = COALESCE(VALUES(image_path), image_path),
                shop_id = VALUES(shop_id),
                qty = VALUES(qty),
                last_user_id = VALUES(last_user_id),
                last_change_at = NOW()
        """, (ean, name, image_path, shop_id, qty, last_user_id))

        conn.commit()
        cur.close()
        conn.close()

    def get_shops(self):
        """
        Liefert eine Liste der Shops für das Dropdown im Eingabemodus.
        Wenn es noch keine Tabelle 'shops' gibt, wird einfach [] zurückgegeben.
        """
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Prüfen, ob Tabelle 'shops' existiert
            cur.execute("SHOW TABLES LIKE 'shops'")
            row = cur.fetchone()
            if not row:
                print("[get_shops] Tabelle 'shops' existiert noch nicht – leere Liste.")
                cur.close()
                conn.close()
                return []

            cur.execute("""
                SELECT id, code, name, NULL
                FROM shops
                ORDER BY name
            """)
            rows = cur.fetchall()
            cur.close()
            conn.close()

            return [
                {
                    "id": r[0],
                    "code": r[1],
                    "name": r[2],
                    "web_url": r[3],
                }
                for r in rows
            ]
        except Error as e:
            print(f"[get_shops] DB-Fehler: {e}")
            return []
        except Exception as e:
            print(f"[get_shops] Unerwarteter Fehler: {e}")
            return []




def save_image_for_ean(ean: str, image_b64: str) -> str:
    """
    Speichert ein JPEG-Bild für diese EAN unter images/<ean>.jpg,
    skaliert auf max. 800px Kantenlänge und ca. 70% Qualität.
    Aktualisiert items.image_path. Gibt den Dateipfad zurück.
    """
    img_bytes = base64.b64decode(image_b64)

    try:
        img = Image.open(BytesIO(img_bytes))
    except Exception as exc:
        print(f"[save_image_for_ean] Fehler beim Öffnen des Bildes für EAN={ean}: {exc}")
        # Notfall: Rohbytes ablegen
        filename_raw = f"{ean}_raw.bin"
        filepath_raw = os.path.join(IMAGE_DIR, filename_raw)
        with open(filepath_raw, "wb") as f:
            f.write(img_bytes)
        return filepath_raw

    img = img.convert("RGB")

    max_size = 800
    w, h = img.size
    if max(w, h) > max_size:
        img.thumbnail((max_size, max_size), Image.LANCZOS)

    filename = f"{ean}.jpg"
    filepath = os.path.join(IMAGE_DIR, filename)

    os.makedirs(IMAGE_DIR, exist_ok=True)
    img.save(filepath, format="JPEG", quality=70)

    print(f"[save_image_for_ean] EAN={ean}, gespeichert: {filepath}, size={os.path.getsize(filepath)} bytes, orig={w}x{h}")

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


# ------------------------------------------------------------
# Api-Klasse für pywebview (lookup_ean / save_product)
# ------------------------------------------------------------

class Api:
    def __init__(self):
        init_db()

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

    def lookup_ean(self, ean: str, use_online: bool = False):
        ean = (ean or "").strip()
        if not ean:
            return {"ean": "", "name": "", "image_path": "", "qty": 0.0, "shop_id": None, "source": "none"}

        row = self._db_get_product(ean)
        if row:
            row["source"] = "local"
            return row

        # TODO: hier könnte externe EAN-API hin, wenn use_online True
        return {"ean": ean, "name": "", "image_path": "", "qty": 0.0, "shop_id": None, "source": "none"}



    def save_product(
        self,
        ean: str,
        name: str,
        shop_id: int | None = None,
        qty: float = 0.0,
        rfid_uid: str | None = None,
    ):
        ean = (ean or "").strip()
        name = (name or "").strip()

        if not ean:
            return {"ok": False, "message": "EAN fehlt"}

        # RFID → users.id (last_user_id)
        user_id = None
        if rfid_uid:
            user_id = get_user_id_by_rfid(rfid_uid)

        try:
            self._db_save_product(ean, name, shop_id, qty, last_user_id=user_id)
            return {"ok": True, "message": "Gespeichert"}
        except Exception as exc:
            print(f"[save_product] Fehler: {exc}")
            return {"ok": False, "message": f"Fehler beim Speichern: {exc}"}



# ------------------------------------------------------------
# WebSocket-Server Desktop <-> Mobile
# ------------------------------------------------------------

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
    print("[ws_handler] Client verbunden")
    try:
        async for message in websocket:
            try:
                print(f"[ws_handler] raw message length: {len(message)}")
            except TypeError:
                print(f"[ws_handler] received non-text message of type {type(message)}")

            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                print("[ws_handler] JSONDecodeError, Nachricht ignoriert")
                continue

            msg_type = data.get("type")
            print(f"[ws_handler] msg_type = {msg_type}")

            if msg_type == "set_article":
                ean = (data.get("ean") or "").strip()
                name = (data.get("name") or "").strip()
                print(f"[ws_handler] set_article: ean={ean}, name={name}")
                last_article = {"ean": ean, "name": name}
                await broadcast({"type": "current_article", **last_article})

            elif msg_type == "request_current_article":
                print("[ws_handler] request_current_article")
                if last_article:
                    await websocket.send(json.dumps({
                        "type": "current_article",
                        **last_article
                    }))

            elif msg_type == "upload_image":
                ean = (data.get("ean") or "").strip()
                image_b64 = data.get("image_base64", "")
                print(f"[ws_handler] upload_image: ean={ean}, len={len(image_b64)}")
                if not ean or not image_b64:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "ean und image_base64 erforderlich"
                    }))
                    continue
                filepath = save_image_for_ean(ean, image_b64)
                await broadcast({
                    "type": "image_updated",
                    "ean": ean,
                    "image_path": filepath,
                    "timestamp": int(time.time())
                })
                print("[ws_handler] upload_image: image_updated broadcastet")

            elif msg_type == "image_uploaded":
                # Nur kurze Nachricht vom Handy nach HTTP-Upload
                ean = (data.get("ean") or "").strip()
                print(f"[ws_handler] image_uploaded: ean={ean}")
                if not ean:
                    continue
                await broadcast({
                    "type": "image_updated",
                    "ean": ean,
                    "timestamp": int(time.time())
                })
                print("[ws_handler] image_uploaded: image_updated broadcastet")

            elif msg_type == "save_name":
                print("[ws_handler] save_name empfangen")
                ean = (data.get("ean") or "").strip()
                name = (data.get("name") or "").strip()
                print(f"[ws_handler] save_name: ean={ean}, name={name}")

                if not ean:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "ean erforderlich"
                    }))
                    continue

                update_product_name(ean, name)
                last_article = {"ean": ean, "name": name}

                await broadcast({
                    "type": "current_article",
                    "ean": ean,
                    "name": name,
                })
                print("[ws_handler] save_name: current_article broadcastet")

            else:
                print(f"[ws_handler] Unbekannter msg_type: {msg_type}")

    except Exception as e:
        print(f"[ws_handler] Unerwarteter Fehler: {e}")
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
            max_size=None,  # kein Limit, wir begrenzen per Pillow
        ):
            await asyncio.Future()

    asyncio.run(main_ws())


def start_http_server():
    print("HTTP-Server auf http://0.0.0.0:8000")
    flask_app.run(host="0.0.0.0", port=8000)


# ------------------------------------------------------------
# pywebview starten
# ------------------------------------------------------------

def main():
    api = Api()

    threading.Thread(target=start_ws_server, daemon=True).start()
    threading.Thread(target=start_http_server, daemon=True).start()

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
