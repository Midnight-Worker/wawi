# db.py
import os
import base64
from io import BytesIO

import mysql.connector
from mysql.connector import Error
from PIL import Image

from config import DB_CONFIG, IMAGE_DIR

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def init_db():
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
    img_bytes = base64.b64decode(image_b64)

    try:
        img = Image.open(BytesIO(img_bytes))
    except Exception as exc:
        print(f"[save_image_for_ean] Fehler beim Öffnen des Bildes für EAN={ean}: {exc}")
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


def db_get_product(ean: str):
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


def db_save_product(ean: str, name: str, shop_id: int | None, qty: float, last_user_id: int | None):
    conn = get_db_connection()
    cur = conn.cursor()
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


def get_shops():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

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
            {"id": r[0], "code": r[1], "name": r[2], "web_url": r[3]}
            for r in rows
        ]
    except Error as e:
        print(f"[get_shops] DB-Fehler: {e}")
        return []
    except Exception as e:
        print(f"[get_shops] Unerwarteter Fehler: {e}")
        return []
