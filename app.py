import os
import threading
import asyncio
import json
import base64
import sqlite3

import webview
import requests
from flask import Flask, send_from_directory
import websockets
from openean.OpenEAN import OpenEAN

DB_PATH = "products.db"
IMAGE_DIR = "images"

# OpenEAN / OpenGTINDB User-ID
OPENEAN_USER_ID = "400000000"  # für Tests ok, für Produktion eigenen holen
openean_api = OpenEAN(OPENEAN_USER_ID)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOBILE_VIEWS_DIR = os.path.join(BASE_DIR, "mobile_views")
VIEWS_DIR = os.path.join(BASE_DIR, "views")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(MOBILE_VIEWS_DIR, exist_ok=True)
os.makedirs(VIEWS_DIR, exist_ok=True)


# ----------------- Datenbank-Setup -----------------


def init_db():
    """Erzeugt eine lokale SQLite-DB, falls noch nicht vorhanden."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            ean TEXT PRIMARY KEY,
            name TEXT,
            brand TEXT,
            source TEXT,
            image_path TEXT
        )
    """)
    # Falls die Tabelle schon ohne image_path existierte, Spalte nachträglich hinzufügen
    try:
        cur.execute("ALTER TABLE products ADD COLUMN image_path TEXT")
    except sqlite3.OperationalError:
        # Spalte existiert bereits -> ignorieren
        pass
    conn.commit()
    conn.close()


# ----------------- Backend-API für pywebview -----------------


class Api:
    def __init__(self):
        init_db()

    # ---------- DB-Helfer ----------

    def _db_get_product(self, ean: str):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT ean, name, brand, source, image_path FROM products WHERE ean = ?", (ean,))
        row = cur.fetchone()
        conn.close()
        if row:
            return {
                "ean": row[0],
                "name": row[1],
                "brand": row[2],
                "source": row[3] or "local",
                "image_path": row[4] or ""
            }
        return None

    def _db_save_product(self, ean: str, name: str, brand: str, source: str = "local", image_path=None):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # vorhandenen image_path erhalten, falls keiner übergeben wurde
        cur.execute("SELECT image_path FROM products WHERE ean = ?", (ean,))
        row = cur.fetchone()
        if row and image_path is None:
            image_path = row[0]

        cur.execute("""
            INSERT OR REPLACE INTO products (ean, name, brand, source, image_path)
            VALUES (?, ?, ?, ?, ?)
        """, (ean, name, brand, source, image_path))
        conn.commit()
        conn.close()

    # ---------- OpenEAN / OpenGTINDB ----------

    def _lookup_openean(self, ean: str):
        """
        Fragt OpenEAN / OpenGTINDB ab und gibt dict mit name/brand zurück oder None.
        """
        try:
            items = openean_api.parse(ean)
            if not items:
                return None
            item = items[0]
            name = item.detailname or item.name or ""
            brand = item.vendor or ""
            if not name:
                return None
            return {"name": name, "brand": brand}
        except Exception as e:
            print("OpenEAN Fehler:", e)
            return None

    # ---------- OpenFoodFacts ----------

    def _lookup_openfoodfacts(self, ean: str):
        try:
            url = f"https://world.openfoodfacts.org/api/v0/product/{ean}.json"
            resp = requests.get(url, timeout=5)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("status") != 1:
                return None
            product = data.get("product", {})
            name = product.get("product_name", "")
            brand = ", ".join(product.get("brands_tags", [])) or product.get("brands", "")
            if not name:
                return None
            return {"name": name, "brand": brand}
        except Exception as e:
            print("OpenFoodFacts Fehler:", e)
            return None

    # ---------- API-Funktionen für JS ----------

    def lookup_ean(self, ean):
        """
        Lookup-Reihenfolge:
        1. Lokale DB
        2. OpenEAN / OpenGTINDB
        3. OpenFoodFacts
        4. -> falls alles leer: Frontend zeigt manuelles Formular
        """

        print(f"lookup_ean: {ean}")

        def make_result(source, ean, name=None, brand=None, image_path=None, ok=True, message=None):
            return {
                "ok": ok,
                "ean": ean,
                "name": name or "",
                "brand": brand or "",
                "image_path": image_path or "",
                "source": source,
                "message": message or "",
            }

        # 1) Lokale DB
        try:
            local_product = self._db_get_product(ean)
            if local_product:
                print("Treffer in lokaler DB")
                return make_result(
                    source=local_product["source"],
                    ean=local_product["ean"],
                    name=local_product["name"],
                    brand=local_product["brand"],
                    image_path=local_product["image_path"],
                )
        except Exception as e:
            print("Lokale DB Fehler:", e)

        # 2) OpenEAN
        openean_data = self._lookup_openean(ean)
        if openean_data:
            print("Treffer in OpenEAN")
            name = openean_data["name"]
            brand = openean_data["brand"]
            self._db_save_product(ean, name, brand, source="openean")
            return make_result("openean", ean, name, brand)

        # 3) OpenFoodFacts
        off_data = self._lookup_openfoodfacts(ean)
        if off_data:
            print("Treffer in OpenFoodFacts")
            name = off_data["name"]
            brand = off_data["brand"]
            self._db_save_product(ean, name, brand, source="openfoodfacts")
            return make_result("openfoodfacts", ean, name, brand)

        # 4) nichts gefunden
        print("Kein Produkt gefunden")
        return make_result(
            source="none",
            ean=ean,
            ok=False,
            message="Kein Produkt in lokaler DB, OpenEAN oder OpenFoodFacts gefunden. Bitte manuell eintragen.",
        )

    def save_product(self, ean, name, brand):
        """
        Vom Frontend aufgerufen, wenn der Nutzer manuell ein Produkt eingibt.
        """
        print(f"save_product: {ean}, {name}, {brand}")
        try:
            self._db_save_product(ean, name, brand, source="manual")
            return {"ok": True, "message": "Produkt gespeichert."}
        except Exception as e:
            return {"ok": False, "message": f"Fehler beim Speichern: {e}"}


# ----------------- Flask-Webserver für Mobile-Seite -----------------

flask_app = Flask(__name__)


@flask_app.route("/mobile")
def mobile_page():
    return send_from_directory(MOBILE_VIEWS_DIR, "mobile.html")


# ----------------- WebSocket-Server für Bildupload -----------------


async def ws_handler(websocket):
    async for message in websocket:
        try:
            data = json.loads(message)
            ean = data.get("ean")
            image_b64 = data.get("image_base64")

            if not ean or not image_b64:
                await websocket.send(json.dumps({
                    "ok": False,
                    "message": "ean und image_base64 erforderlich"
                }))
                continue

            # Bild dekodieren und speichern
            img_bytes = base64.b64decode(image_b64)
            filename = f"{ean}.jpg"
            filepath = os.path.join(IMAGE_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(img_bytes)

            # in DB Pfad speichern
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                UPDATE products
                SET image_path = ?
                WHERE ean = ?
            """, (filepath, ean))
            if cur.rowcount == 0:
                cur.execute("""
                    INSERT INTO products (ean, name, brand, source, image_path)
                    VALUES (?, '', '', 'image-only', ?)
                """, (ean, filepath))
            conn.commit()
            conn.close()

            await websocket.send(json.dumps({
                "ok": True,
                "message": "Bild gespeichert",
                "ean": ean,
                "image_path": filepath
            }))

        except Exception as e:
            print("Fehler im WebSocket-Server:", e)
            await websocket.send(json.dumps({
                "ok": False,
                "message": f"Fehler: {e}"
            }))


def start_ws_server():
    async def main_ws():
        print("Starte WebSocket-Server auf ws://0.0.0.0:8765")
        async with websockets.serve(ws_handler, "0.0.0.0", 8765):
            await asyncio.Future()  # läuft "für immer"

    asyncio.run(main_ws())


def start_http_server():
    print("Starte Flask HTTP-Server auf http://0.0.0.0:8000/mobile")
    flask_app.run(host="0.0.0.0", port=8000)


# ----------------- Fenster erstellen & starten -----------------


def main():
    print("Starte EAN-Scanner + WebSocket + HTTP-Server...")

    api = Api()

    # WebSocket-Server in separatem Thread starten
    ws_thread = threading.Thread(target=start_ws_server, daemon=True)
    ws_thread.start()

    # HTTP-Server (Flask) in separatem Thread starten
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()

    index_html_path = os.path.join(VIEWS_DIR, "index.html")

    window = webview.create_window(
        'EAN-Scanner',
        url=index_html_path,
        js_api=api,
        width=800,
        height=600,
        min_size=(600, 400),
    )
    webview.start()


if __name__ == '__main__':
    main()
