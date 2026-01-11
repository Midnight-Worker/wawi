window.addEventListener('pywebviewready', () => {
    $(document).ready(function () {

        const eanInput = document.getElementById("ean");
        const nameInput = document.getElementById("name");
        const toggleOnline = document.getElementById("toggle-online-lookup");
        let useOnlineLookup = toggleOnline ? toggleOnline.checked : false;

        console.log("main.js gestartet");

        if (toggleOnline) {
            toggleOnline.addEventListener("change", () => {
                useOnlineLookup = toggleOnline.checked;
                console.log("Online-Lookup:", useOnlineLookup);
            });
        }

        $("#reloadbutton").on('click', function () {
            window.location.reload();
        });

        // Beim Start Fokus + Selektion erzwingen (Barcode-Scanner-Workflow)
        setTimeout(() => {
            eanInput.focus();
            eanInput.select();
        }, 0);

        // Enter im EAN-Feld -> lookup()
        eanInput.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter") {
                ev.preventDefault();
                lookup();
            }
        });

        let wsDesktop = null;
        let currentArticle = { ean: null, name: null };

        function connectWebSocketDesktop() {
            const wsUrl = "ws://127.0.0.1:8765";
            wsDesktop = new WebSocket(wsUrl);

            wsDesktop.onopen = () => {
                console.log("Desktop-WS verbunden:", wsUrl);
            };
            wsDesktop.onclose = () => console.log("Desktop-WS geschlossen");
            wsDesktop.onerror = (e) => console.log("Desktop-WS Fehler:", e);
            wsDesktop.onmessage = (e) => {
                console.log("Desktop-WS Nachricht:", e.data);
                let msg;
                try {
                    msg = JSON.parse(e.data);
                } catch {
                    return;
                }

                // Bild-Update vom Server (wenn Mobile ein neues Foto hochgeladen hat)
                if (msg.type === "image_updated") {
                    console.log("Desktop: image_updated für EAN", msg.ean);
                    if (currentArticle.ean && msg.ean === currentArticle.ean) {
                        const img = document.getElementById("product-image");
                        img.src = "/image/" + encodeURIComponent(msg.ean) + "?t=" + Date.now();
                        img.style.display = "block";
                    }
                }

                // Optional: current_article ignorieren oder bei Bedarf verwenden
            };
        }

        connectWebSocketDesktop();

        async function lookup() {
            const ean = eanInput.value.trim();
            if (!ean) {
                alert("Bitte EAN eingeben.");
                // Nach dem Alert wieder Fokus + Selektion
                setTimeout(() => {
                    eanInput.focus();
                    eanInput.select();
                }, 0);
                return;
            }

            // pywebview-Backend aufrufen
            const result = await window.pywebview.api.lookup_ean(ean, useOnlineLookup);

            // aktuellen Artikel merken
            currentArticle.ean = result.ean || null;
            currentArticle.name = result.name || "";

            // Formular & Anzeige aktualisieren
            eanInput.value = result.ean || "";
            nameInput.value = result.name || "";
            document.getElementById("db-result").textContent =
                JSON.stringify(result, null, 2);

            // Bild anzeigen: über den HTTP-Endpoint /image/<ean>
            const img = document.getElementById("product-image");
            if (result.ean) {
                // Cache-Buster dran, falls gerade neues Bild hochgeladen wurde
                img.src = "/image/" + encodeURIComponent(result.ean) + "?t=" + Date.now();
                img.style.display = "block";
            } else {
                img.src = "";
                img.style.display = "none";
            }

            // aktuellen Artikel an WS-Server senden (für Mobile)
            if (wsDesktop && wsDesktop.readyState === WebSocket.OPEN) {
                const payload = {
                    type: "set_article",
                    ean: result.ean,
                    name: result.name
                };
                wsDesktop.send(JSON.stringify(payload));
            }

            // Nach jeder Suche: EAN-Feld fokussieren & komplett selektieren
            setTimeout(() => {
                eanInput.focus();
                eanInput.select();
            }, 0);
        }

        async function saveManual() {
            const ean = eanInput.value.trim();
            const name = nameInput.value.trim();
            const res = await window.pywebview.api.save_product(ean, name);
            alert(res.message || "OK");

            // Nach dem Speichern wieder bereit für den nächsten Scan
            setTimeout(() => {
                eanInput.focus();
                eanInput.select();
            }, 0);
        }

        // Damit Buttons weiter funktionieren
        window.lookup = lookup;
        window.saveManual = saveManual;
    });
});
