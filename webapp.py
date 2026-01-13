# webapp.py
import os
import base64
from io import BytesIO

from flask import Flask, send_file, send_from_directory, request, jsonify
import qrcode

from config import PUBLIC_DIR, VIEWS_DIR, MOBILE_VIEWS_DIR, IMAGE_DIR, MOBILE_URL, DUMMY_IMAGE_PATH
from db import get_db_connection, save_image_for_ean
from websocket_server import broadcast_from_anywhere

API_INSTANCE = None  # wird in main.py gesetzt

flask_app = Flask(
    __name__,
    static_folder=PUBLIC_DIR,
    static_url_path="/public"
)

def set_api_instance(api):
    global API_INSTANCE
    API_INSTANCE = api


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
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT image_path FROM items WHERE ean = %s", (ean,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    candidate = row[0] if row and row[0] else None
    if candidate and os.path.exists(candidate):
        return send_file(candidate, mimetype="image/jpeg")

    return send_file(DUMMY_IMAGE_PATH, mimetype="image/png")


@flask_app.route("/qr")
def mobile_qr():
    img = qrcode.make(MOBILE_URL)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@flask_app.route("/upload_image/<ean>", methods=["POST"])
def upload_image_http(ean):
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

        return jsonify({"ok": True, "message": "Bild gespeichert", "ean": ean})
    except Exception as exc:
        print(f"[upload_image_http] Fehler bei EAN={ean}: {exc}")
        return jsonify({"ok": False, "message": "Fehler beim Speichern"}), 500


@flask_app.route("/api/current_user")
def api_current_user():
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
    from db import get_shops
    try:
        shops = get_shops()
        return jsonify({"shops": shops})
    except Exception as e:
        print(f"[api_shops] Fehler: {e}")
        return jsonify({"shops": []}), 500


@flask_app.route("/api/save_item", methods=["POST"])
def api_save_item():
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

            cur.execute("""
                UPDATE items
                SET name = %s,
                    qty = %s,
                    shop_id = %s,
                    last_user_id = %s,
                    last_change_at = NOW()
                WHERE ean = %s
            """, (name, qty_val, shop_id_val, user_id, ean))
        else:
            cur.execute("""
                INSERT INTO items (ean, name, qty, shop_id, last_user_id, last_change_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (ean, name, qty_val, shop_id_val, user_id))
            item_id = cur.lastrowid

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[api_save_item] DB-Fehler: {e}")
        return jsonify({"ok": False, "message": "DB-Fehler"}), 500

    return jsonify({"ok": True, "message": "Artikel gespeichert", "item_id": item_id})


@flask_app.route("/api/lookup_ean")
def api_lookup_ean_http():
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
    global API_INSTANCE
    if API_INSTANCE is None:
        return jsonify({"ok": False, "message": "API nicht initialisiert"}), 500
    result = API_INSTANCE.logout()
    return jsonify(result)
