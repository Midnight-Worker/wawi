import os
import threading
import asyncio
import json
import base64
import time
import serial
from datetime import datetime, timedelta, timezone

from io import BytesIO

import webview
from flask import Flask, send_file, send_from_directory, request, jsonify
import qrcode
import websockets
import requests

from PIL import Image
import nfc  # aktuell ungenutzt, aber ok

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
API_INSTANCE = None

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
    "password": "poke",         # ANPASSEN
    "database": "wawi_b7",
}

# ------------------------------------------------------------
# Online-EAN-Quellen (optional)
# ------------------------------------------------------------

# Open Food Facts: frei nutzbar, kein Key nötig
OPENFOODFACTS_BASE_URL = "https://world.openfoodfacts.org/api/v0/product"

# OpenGTINDB / Open EAN Database:
# http://opengtindb.org/?ean=[ean]&cmd=query&queryid=[userid]
# queryid musst du dir ggf. dort registrieren.
OPENGTINDB_QUERY_ID = ""  # z.B. "123456789" – leer lassen zum Deaktivieren


# ------------------------------------------------------------
# WebSocket-Globals
# ------------------------------------------------------------

connected_clients = set()
last_article = None  # {"ean": "...", "name": "..."}
WS_LOOP = None       # Event-Loop des WS-Servers


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


@flask_app.route("/desktop_input")
def desktop_input_page():
    return send_from_directory(VIEWS_DIR, "desktop_eingabe.html")


@flask_app.route("/mobile")
def mobile_page():
    return send_from_directory(MOBILE_VIEWS_DIR, "mobile.html")


@flask_app.route("/mobile/erfassung")
def mobile_erfassung_page():
    return send_from_directory(MOBILE_VIEWS_DIR, "erfassung.html")


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


@flask_app.route("/api/current_user")
def api_current_user():
    """
    Wird von mobile.js per fetch() aufgerufen, um zu sehen,
    ob jemand eingeloggt ist und wie der Timeout ist.
    """
    global API_INSTANCE
    if API_INSTANCE is None:
        return jsonify({
            "user_id": None,
            "user_name": "",
            "timeout_minutes": 0,
            "expires_at": None,
        })
    return jsonify(API_INSTANCE.get_current_user())


@flask_app.route("/api/shops")
def api_shops():
    """
    Liefert eine einfache Shop-Liste für das Dropdown im Handy.
    Erwartet eine Tabelle 'shops(id, name, ...)'.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM shops ORDER BY name")
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Error as e:
        print(f"[api_shops] DB-Fehler: {e}")
        return jsonify({"shops": []}), 500

    shops = [{"id": row[0], "name": row[1]} for row in rows]
    return jsonify({"shops": shops})


@flask_app.route("/api/save_item", methods=["POST"])
def api_save_item():
    """
    Speichert Artikel-Daten (Name, Menge, Shop) und setzt last_user_id / last_change_at.
    Wird von der Mobile-View aufgerufen.
    """
    global API_INSTANCE
    data = request.get_json(silent=True) or {}

    ean = (data.get("ean") or "").strip()
    name = (data.get("name") or "").strip()
    qty = data.get("qty")
    shop_id = data.get("shop_id")

    if not ean:
        return jsonify({"ok": False, "message": "EAN fehlt"}), 400

    try:
        qty_val = float(qty)
    except (TypeError, ValueError):
        qty_val = 0.0

    try:
        shop_id_val = int(shop_id) if shop_id is not None else None
    except (TypeError, ValueError):
        shop_id_val = None

    user_id = None
    if API_INSTANCE and API_INSTANCE.current_user_id is not None:
        user_id = API_INSTANCE.current_user_id

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT id, name FROM items WHERE ean = %s", (ean,))
        row = cur.fetchone()

        if row:
            item_id = row[0]
            if not name:
                name = row[1] or ""

            cur.execute(
                """
                UPDATE items
                SET name = %s,
                    qty = %s,
                    shop_id = %s,
                    last_user_id = %s,
                    last_change_at = NOW()
                WHERE ean = %s
                """,
                (name, qty_val, shop_id_val, user_id, ean),
            )
        else:
            cur.execute(
                """
                INSERT INTO items (ean, name, qty, shop_id, last_user_id, last_change_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (ean, name, qty_val, shop_id_val, user_id),
            )
            item_id = cur.lastrowid

        conn.commit()
        cur.close()
        conn.close()
    except Error as e:
        print(f"[api_save_item] DB-Fehler: {e}")
        return jsonify({"ok": False, "message": "DB-Fehler"}), 500

    return jsonify({"ok": True, "message": "Artikel gespeichert", "item_id": item_id})


@flask_app.route("/api/lookup_ean")
def api_lookup_ean_http():
    """
    Liefert zu einer EAN die vorhandenen Item-Daten (lokal) und optional externen Lookup.
    Nutzt Api.lookup_ean().
    """
    global API_INSTANCE
    if API_INSTANCE is None:
        return jsonify({
            "ean": "",
            "name": "",
            "image_path": "",
            "qty": 0.0,
            "shop_id": None,
            "source": "none",
            "message": "API nicht initialisiert"
        }), 500

    ean = (request.args.get("ean") or "").strip()
    use_online = (request.args.get("online") == "1")

    result = API_INSTANCE.lookup_ean(ean, use_online=use_online)
    return jsonify(result)


@flask_app.route("/api/logout", methods=["POST"])
def api_logout():
    """
    Optional: HTTP-Logout, falls du per Button auf dem Handy ausloggen willst.
    """
    global API_INSTANCE
    if API_INSTANCE is None:
        return jsonify({"ok": False, "message": "API nicht initialisiert"}), 500
    result = API_INSTANCE.logout()
    return jsonify(result)


# ------------------------------------------------------------
# DB-Helferfunktionen für items (EAN, Name, Bild)
# ------------------------------------------------------------

def get_user_by_rfid(rfid_uid: str):
    rfid_uid = (rfid_uid or "").strip()
    if not rfid_uid:
        return None

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name FROM users WHERE LOWER(rfid_uid) = LOWER(%s)",
            (rfid_uid,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            print(f"[rfid] get_user_by_rfid: UID={rfid_uid} -> id={row[0]}, name={row[1]}")
            return {"id": row[0], "name": row[1]}
        else:
            print(f"[rfid] get_user_by_rfid: UID={rfid_uid} -> kein Treffer in users")
        return None
    except Error as e:
        print(f"[get_user_by_rfid] DB-Fehler: {e}")
        return None


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


def broadcast_from_anywhere(message_dict: dict):
    """
    Aus jedem Thread heraus eine WS-Broadcast-Nachricht schicken.
    """
    global WS_LOOP
    if WS_LOOP and WS_LOOP.is_running():
        asyncio.run_coroutine_threadsafe(broadcast(message_dict), WS_LOOP)
    else:
        print("[broadcast_from_anywhere] WS_LOOP läuft nicht, kann nicht senden:", message_dict)


# ------------------------------------------------------------
# Api-Klasse für pywebview (lookup_ean / save_product)
# ------------------------------------------------------------

class Api:
    def __init__(self):
        init_db()
        self.current_user_id = None
        self.current_user_name = ""
        self.session_timeout_minutes = 30  # Standard: 30 Minuten
        self.current_user_expires_at = None  # UTC-Deadline, oder None für "kein Timeout"

    def _apply_timeout(self):
        """
        Prüft, ob die aktuelle Session abgelaufen ist.
        Wird bei get_current_user aufgerufen.
        """
        if self.current_user_id is None:
            return
        if self.current_user_expires_at is None:
            return

        now = datetime.now(timezone.utc)
        if now >= self.current_user_expires_at:
            print("[session] Session abgelaufen, User wird ausgeloggt.")
            old_id = self.current_user_id
            old_name = self.current_user_name
            self.current_user_id = None
            self.current_user_name = ""
            self.current_user_expires_at = None

            # optional: Logout per WS pushen
            broadcast_from_anywhere({
                "type": "user_logout",
                "prev_user_id": old_id,
                "prev_user_name": old_name,
            })

    def rfid_login(self, rfid_uid: str):
        """
        Wird aufgerufen, wenn ein Scan als möglicher RFID interpretiert wird.
        Wenn rfid_uid in users.rfid_uid gefunden wird, setzen wir current_user_*.
        """
        user = get_user_by_rfid(rfid_uid)
        if not user:
            # Kein Alarm, nur "nicht erkannt"
            return {
                "ok": False,
                "is_rfid": False,
                "message": "RFID nicht erkannt"
            }

        self.current_user_id = user["id"]
        self.current_user_name = user["name"]

        if self.session_timeout_minutes > 0:
            self.current_user_expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=self.session_timeout_minutes
            )
        else:
            self.current_user_expires_at = None

        print(f"[rfid_login] User angemeldet: id={self.current_user_id}, name={self.current_user_name}")

        # WebSocket-Event für alle Clients -> Handy kann umschalten
        broadcast_from_anywhere({
            "type": "user_login",
            "user_id": self.current_user_id,
            "user_name": self.current_user_name,
        })

        return {
            "ok": True,
            "is_rfid": True,
            "user_id": user["id"],
            "user_name": user["name"],
            "message": f"Angemeldet als {user['name']}"
        }

    def logout(self):
        """
        Manuelles Logout (z. B. per Button oder Desktop).
        """
        print(f"[session] Logout angefordert. User war: {self.current_user_name} ({self.current_user_id})")
        old_id = self.current_user_id
        old_name = self.current_user_name

        self.current_user_id = None
        self.current_user_name = ""
        self.current_user_expires_at = None

        broadcast_from_anywhere({
            "type": "user_logout",
            "prev_user_id": old_id,
            "prev_user_name": old_name,
        })

        return {"ok": True}

    def get_current_user(self):
        self._apply_timeout()
        if self.current_user_id is None:
            return {
                "user_id": None,
                "user_name": "",
                "timeout_minutes": self.session_timeout_minutes,
                "expires_at": None,
            }
        return {
            "user_id": self.current_user_id,
            "user_name": self.current_user_name,
            "timeout_minutes": self.session_timeout_minutes,
            "expires_at": self.current_user_expires_at.isoformat() if self.current_user_expires_at else None,
        }

    def set_session_timeout(self, minutes: int):
        """
        Timeout in Minuten setzen. 0 = kein Auto-Logout.
        Wenn ein User eingeloggt ist, wird die Deadline neu gesetzt.
        """
        try:
            m = int(minutes)
        except Exception:
            m = 0
        m = max(0, min(480, m))  # 0–480 Minuten
        self.session_timeout_minutes = m
        print(f"[session] Timeout-Minuten gesetzt auf {m}")

        if self.current_user_id is not None and m > 0:
            self.current_user_expires_at = datetime.now(timezone.utc) + timedelta(minutes=m)
            print(f"[session] Neue Ablaufzeit: {self.current_user_expires_at}")
        elif self.current_user_id is not None and m == 0:
            self.current_user_expires_at = None
            print("[session] Kein Auto-Logout für aktuelle Session.")

        return {"ok": True, "timeout_minutes": self.session_timeout_minutes}

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



    def lookup_ean(self, ean: str, use_online: bool = False):
        ean = (ean or "").strip()
        if not ean:
            return {
                "ean": "",
                "name": "",
                "image_path": "",
                "qty": 0.0,
                "shop_id": None,
                "source": "none",
            }

        # 1) Lokale DB zuerst
        row = self._db_get_product(ean)
        if row:
            row["source"] = "local"
            return row

        # 2) Optional: Online-Lookup
        if use_online:
            online = self._lookup_ean_online(ean)
            if online and online.get("name"):
                # Ergebnis in lokale DB cachen, damit spätere Abfragen offline gehen
                try:
                    self._db_save_product(
                        ean=ean,
                        name=online["name"],
                        shop_id=None,
                        qty=0.0,
                        last_user_id=None,
                    )
                    print(f"[lookup_ean] Online-Ergebnis für {ean} lokal gespeichert.")
                except Exception as exc:
                    print(f"[lookup_ean] Fehler beim lokalen Speichern von Online-Ergebnis: {exc}")

                return online

        # 3) Nichts gefunden
        return {
            "ean": ean,
            "name": "",
            "image_path": "",
            "qty": 0.0,
            "shop_id": None,
            "source": "none",
        }



    def _lookup_ean_online(self, ean: str):
        """
        Versucht, für eine EAN einen Produktnamen aus freien Online-Datenbanken
        zu holen. Momentan:
          1) Open Food Facts
          2) Optional: OpenGTINDB (wenn OPENGTINDB_QUERY_ID gesetzt ist)
        Gibt bei Erfolg ein Dict im gleichen Format wie _db_get_product()
        (plus 'source') zurück oder None, wenn nichts gefunden wurde.
        """
        # 1) Open Food Facts
        try:
            url = f"{OPENFOODFACTS_BASE_URL}/{ean}.json"
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                data = r.json()
                # status == 1 -> Produkt gefunden :contentReference[oaicite:2]{index=2}
                if data.get("status") == 1:
                    product = data.get("product", {}) or {}
                    name = (product.get("product_name") or "").strip()
                    generic = (product.get("generic_name") or "").strip()
                    brands = (product.get("brands") or "").strip()

                    # sinnvoller Name:
                    # Priorität: product_name, sonst generic_name
                    base_name = name or generic

                    full_name = base_name
                    # Brand vorne anhängen, falls noch nicht im Namen
                    if brands and base_name:
                        if brands.lower() not in base_name.lower():
                            full_name = f"{brands} {base_name}"
                    elif brands and not base_name:
                        full_name = brands

                    if full_name:
                        print(f"[online] OpenFoodFacts: {ean} -> {full_name}")
                        return {
                            "ean": ean,
                            "name": full_name,
                            "image_path": "",
                            "qty": 0.0,
                            "shop_id": None,
                            "last_user_id": None,
                            "last_change_at": None,
                            "source": "online_off",
                        }
        except Exception as exc:
            print(f"[online] OpenFoodFacts Fehler für {ean}: {exc}")

        # 2) OpenGTINDB / Open EAN Database (optional)
        if OPENGTINDB_QUERY_ID:
            try:
                params = {
                    "ean": ean,
                    "cmd": "query",
                    "queryid": OPENGTINDB_QUERY_ID,
                }
                r = requests.get("http://opengtindb.org/", params=params, timeout=3)
                if r.status_code == 200:
                    text = r.text
                    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

                    error_code = None
                    fields = {}

                    for ln in lines:
                        if ln.startswith("---"):
                            # erster Datensatz reicht uns
                            break
                        if "=" in ln:
                            k, v = ln.split("=", 1)
                            k = k.strip()
                            v = v.strip()
                            if k == "error":
                                error_code = v
                            else:
                                fields[k] = v

                    if error_code == "0":
                        # Name bauen: detailname > name; optional vendor voranstellen
                        detailname = fields.get("detailname", "").strip()
                        name = fields.get("name", "").strip()
                        vendor = fields.get("vendor", "").strip()

                        base_name = detailname or name
                        full_name = base_name
                        if vendor and base_name:
                            if vendor.lower() not in base_name.lower():
                                full_name = f"{vendor} {base_name}"
                        elif vendor and not base_name:
                            full_name = vendor

                        if full_name:
                            print(f"[online] OpenGTINDB: {ean} -> {full_name}")
                            return {
                                "ean": ean,
                                "name": full_name,
                                "image_path": "",
                                "qty": 0.0,
                                "shop_id": None,
                                "last_user_id": None,
                                "last_change_at": None,
                                "source": "online_opengtindb",
                            }
            except Exception as exc:
                print(f"[online] OpenGTINDB Fehler für {ean}: {exc}")

        # nichts gefunden
        return None



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
            user_info = get_user_by_rfid(rfid_uid)
            user_id = user_info["id"] if user_info else None

        try:
            self._db_save_product(ean, name, shop_id, qty, last_user_id=user_id)
            return {"ok": True, "message": "Gespeichert"}
        except Exception as exc:
            print(f"[save_product] Fehler: {exc}")
            return {"ok": False, "message": f"Fehler beim Speichern: {exc}"}


# ------------------------------------------------------------
# WebSocket-Server Desktop <-> Mobile
# ------------------------------------------------------------

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
            await asyncio.Future()  # läuft für immer

    global WS_LOOP
    WS_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(WS_LOOP)
    WS_LOOP.run_until_complete(main_ws())


# ------------------------------------------------------------
# HTTP-Server & RFID-Monitor
# ------------------------------------------------------------

def start_http_server():
    print("HTTP-Server auf http://0.0.0.0:8000")
    flask_app.run(host="0.0.0.0", port=8000)


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


# ------------------------------------------------------------
# pywebview starten
# ------------------------------------------------------------

def main():
    global API_INSTANCE
    api = Api()
    API_INSTANCE = api

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


"""
    def lookup_ean(self, ean: str, use_online: bool = False):
        ean = (ean or "").strip()
        if not ean:
            return {"ean": "", "name": "", "image_path": "", "qty": 0.0, "shop_id": None, "source": "none"}

        row = self._db_get_product(ean)
        if row:
            row["source"] = "local"
            return row

        # optionale externe DB (noch TODO, aber use_online ist da)
        if use_online:
            # Hier kommt später dein Online-Lookup hin (OpenFoodFacts o.Ä.)
            # online = self._lookup_ean_online(ean)
            # if online:
            #     online["source"] = "online"
            #     return online
            pass

        return {"ean": ean, "name": "", "image_path": "", "qty": 0.0, "shop_id": None, "source": "none"}
"""