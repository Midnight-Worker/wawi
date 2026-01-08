import webview
import json
import threading
import requests


# Python-API für JS
class Api:
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


def create_window():
    api = Api()
    # HTML direkt aus String, du kannst das auch in eine externe Datei auslagern
    html = """
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <title>EAN Scanner</title>
        <style>
            body {
                font-family: sans-serif;
                margin: 20px;
            }
            #ean-input {
                width: 100%;
                font-size: 2rem;
                padding: 10px;
                box-sizing: border-box;
            }
            #result {
                margin-top: 20px;
                font-size: 1.2rem;
            }
            .error {
                color: red;
            }
        </style>
    </head>
    <body>
        <h1>EAN-Scanner</h1>
        <p>Cursor ins Feld setzen und mit Handscanner scannen (oder EAN eintippen und Enter).</p>
        <input id="ean-input" type="text" autofocus placeholder="EAN scannen..." />
        <div id="result"></div>

        <script>
            const input = document.getElementById('ean-input');
            const resultDiv = document.getElementById('result');

            function showResult(data) {
                if (!data.ok) {
                    resultDiv.innerHTML = '<p class="error">' + (data.message || 'Unbekannter Fehler') + '</p>';
                    return;
                }
                resultDiv.innerHTML = `
                    <p><strong>EAN:</strong> ${data.ean}</p>
                    <p><strong>Name:</strong> ${data.name}</p>
                    <p><strong>Marke:</strong> ${data.brand || '-'}</p>
                `;
            }

            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    const ean = input.value.trim();
                    if (!ean) return;

                    resultDiv.innerHTML = '<p>Suche nach ' + ean + ' ...</p>';

                    // Python-API über pywebview aufrufen
                    if (window.pywebview && window.pywebview.api) {
                        window.pywebview.api.lookup_ean(ean).then(showResult);
                    } else {
                        resultDiv.innerHTML = '<p class="error">pywebview API nicht verfügbar.</p>';
                    }

                    // optional: Feld leeren für nächsten Scan
                    input.value = '';
                }
            });

            // Sicherstellen, dass der Fokus im Feld bleibt (z.B. nach Klick)
            window.addEventListener('click', () => input.focus());
        </script>
    </body>
    </html>
    """

    window = webview.create_window(
        'EAN-Scanner',
        html=html,
        js_api=api,
        width=600,
        height=400,
        min_size=(400, 300),
    )
    webview.start()


if __name__ == '__main__':
    create_window()

