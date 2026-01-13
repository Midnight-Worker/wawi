# api.py
from datetime import datetime, timedelta, timezone

from db import init_db, get_user_by_rfid, db_get_product, db_save_product, get_shops
from websocket_server import broadcast_from_anywhere


class Api:
    def __init__(self):
        init_db()
        self.current_user_id = None
        self.current_user_name = ""
        self.session_timeout_minutes = 30
        self.current_user_expires_at = None  # UTC

    def _apply_timeout(self):
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

            broadcast_from_anywhere({
                "type": "user_logout",
                "prev_user_id": old_id,
                "prev_user_name": old_name,
            })

    def rfid_login(self, rfid_uid: str):
        user = get_user_by_rfid(rfid_uid)
        if not user:
            return {"ok": False, "is_rfid": False, "message": "RFID nicht erkannt"}

        self.current_user_id = user["id"]
        self.current_user_name = user["name"]

        if self.session_timeout_minutes > 0:
            self.current_user_expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=self.session_timeout_minutes
            )
        else:
            self.current_user_expires_at = None

        print(f"[rfid_login] User angemeldet: id={self.current_user_id}, name={self.current_user_name}")

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
        try:
            m = int(minutes)
        except Exception:
            m = 0
        m = max(0, min(480, m))
        self.session_timeout_minutes = m
        print(f"[session] Timeout-Minuten gesetzt auf {m}")

        if self.current_user_id is not None and m > 0:
            self.current_user_expires_at = datetime.now(timezone.utc) + timedelta(minutes=m)
        elif self.current_user_id is not None and m == 0:
            self.current_user_expires_at = None

        return {"ok": True, "timeout_minutes": self.session_timeout_minutes}

    def lookup_ean(self, ean: str, use_online: bool = False):
        ean = (ean or "").strip()
        if not ean:
            return {"ean": "", "name": "", "image_path": "", "qty": 0.0, "shop_id": None, "source": "none"}

        row = db_get_product(ean)
        if row:
            row["source"] = "local"
            return row

        if use_online:
            # später Online-Lookup
            pass

        return {"ean": ean, "name": "", "image_path": "", "qty": 0.0, "shop_id": None, "source": "none"}

    def get_shops(self):
        return get_shops()

    def save_product(self, ean: str, name: str, shop_id: int | None = None,
                     qty: float = 0.0, rfid_uid: str | None = None):
        ean = (ean or "").strip()
        name = (name or "").strip()
        if not ean:
            return {"ok": False, "message": "EAN fehlt"}

        user_id = None
        if rfid_uid:
            user_info = get_user_by_rfid(rfid_uid)
            user_id = user_info["id"] if user_info else None

        try:
            db_save_product(ean, name, shop_id, qty, last_user_id=user_id)
            return {"ok": True, "message": "Gespeichert"}
        except Exception as exc:
            print(f"[save_product] Fehler: {exc}")
            return {"ok": False, "message": f"Fehler beim Speichern: {exc}"}
