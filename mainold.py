import webview
import json
import threading
import requests


class Api:
	def do_something(self):
		print("did something")

	def lookup_ean(self, ean):
		"""
		Wird aus JavaScript aufgerufen.
		Holt Produktdaten aus einer Online-Datenbank.
		"""
		try:
			# Beispiel: OpenFoodFacts API
			url = f"https://world.openfoodfacts.org/api/v0/product/{ean}.json"
			resp = requests.get(url, timeout=5)
			resp.raise_for_status()
			data = resp.json()

			if data.get("status") != 1:
				return {"ok": False, "message": "Kein Produkt gefunden"}

			product = data.get("product", {})
			name = product.get("product_name", "Unbekannt")
			brand = ", ".join(product.get("brands_tags", [])) or product.get("brands", "")

			result = {
				"ok": True,
				"ean": ean,
				"name": name,
				"brand": brand,
			}
			return result

		except Exception as e:
			return {"ok": False, "message": f"Fehler: {e}"}

api=Api()

webview.create_window(
	"Wareneingang B7",
	url="public/index.html",
	fullscreen=True,
	js_api=api
)

webview.start()
