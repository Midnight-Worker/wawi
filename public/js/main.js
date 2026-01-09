        let wsDesktop = null;

        function connectWebSocketDesktop() {
            const wsUrl = "ws://127.0.0.1:8765";
            wsDesktop = new WebSocket(wsUrl);

            wsDesktop.onopen = () => {
                console.log("Desktop-WS verbunden:", wsUrl);
            };
            wsDesktop.onclose = () => console.log("Desktop-WS geschlossen");
            wsDesktop.onerror = (e) => console.log("Desktop-WS Fehler:", e);
            wsDesktop.onmessage = (e) => console.log("Desktop-WS Nachricht:", e.data);
        }

        window.addEventListener("load", () => {
            connectWebSocketDesktop();

            const eanInput = document.getElementById("ean");

            // Beim Start direkt ins EAN-Feld fokussieren
            eanInput.focus();

            // Enter im EAN-Feld -> lookup()
            eanInput.addEventListener("keydown", (ev) => {
                if (ev.key === "Enter") {
                    ev.preventDefault();
                    lookup();
                }
            });
        });

        async function lookup() {
            const eanInput = document.getElementById("ean");
            const ean = eanInput.value.trim();
            if (!ean) {
                alert("Bitte EAN eingeben.");
                return;
            }

            // pywebview-Backend aufrufen
            const result = await window.pywebview.api.lookup_ean(ean);

            // Formular & Anzeige aktualisieren
            document.getElementById("ean").value = result.ean || "";
            document.getElementById("name").value = result.name || "";
            document.getElementById("db-result").textContent =
                JSON.stringify(result, null, 2);

            // Bild anzeigen: über den HTTP-Endpoint /image/<ean>
            const img = document.getElementById("product-image");
            if (result.ean) {
                // Cache-Buster dran, falls gerade neues Bild hochgeladen wurde
                img.src = "http://127.0.0.1:8000/image/" + encodeURIComponent(result.ean) + "?t=" + Date.now();
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

            // EAN-Feld wieder fokussieren und komplett selektieren
            eanInput.focus();
            eanInput.select();
        }

        async function saveManual() {
            const eanInput = document.getElementById("ean");
            const ean = eanInput.value.trim();
            const name = document.getElementById("name").value.trim();
            const res = await window.pywebview.api.save_product(ean, name);
            alert(res.message || "OK");

            // Nach dem Speichern wieder bereit für den nächsten Scan
            eanInput.focus();
            eanInput.select();
        }