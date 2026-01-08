import webview
import requests
import sqlite3
from openean.OpenEAN import OpenEAN

DB_PATH = "products.db"

# OpenEAN / OpenGTINDB User-ID
# Für Tests geht oft 400000000, für ernsthafte Nutzung eigene queryid von opengtindb.org besorgen.
OPENEAN_USER_ID = "400000000"
openean_api = OpenEAN(OPENEAN_USER_ID)


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
            source TEXT
        )
    """)
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
        cur.execute("SELECT ean, name, brand, source FROM products WHERE ean = ?", (ean,))
        row = cur.fetchone()
        conn.close()
        if row:
            return {
                "ean": row[0],
                "name": row[1],
                "brand": row[2],
                "source": row[3] or "local"
            }
        return None

    def _db_save_product(self, ean: str, name: str, brand: str, source: str = "local"):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO products (ean, name, brand, source)
            VALUES (?, ?, ?, ?)
        """, (ean, name, brand, source))
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

        def make_result(source, ean, name=None, brand=None, ok=True, message=None):
            return {
                "ok": ok,
                "ean": ean,
                "name": name or "",
                "brand": brand or "",
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





# ----------------- Fenster erstellen & starten -----------------

def main():
    print("Starte EAN-Scanner...")
    api = Api()
    window = webview.create_window(
        'EAN-Scanner',
        url="views/index.html",
        js_api=api,
        width=800,
        height=600,
        min_size=(600, 400),
    )
    webview.start()


if __name__ == '__main__':
    main()

