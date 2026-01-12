window.addEventListener('pywebviewready', () => {
    $(document).ready(function () {

        const eanInput = document.getElementById("ean");
        const nameInput = document.getElementById("name");
        const toggleOnline = document.getElementById("toggle-online-lookup");
        const modeIndicator = document.getElementById("mode-indicator");
        const timeoutInput = document.getElementById("session-timeout");
        const logoutBtn = document.getElementById("logout-btn");

        let useOnlineLookup = toggleOnline ? toggleOnline.checked : false;

        // Eingabemodus-Status (für RFID, aber ändert nix am Online-Lookup)
        let inputMode = false;
        let currentUserId = null;
        let currentUserName = "";
        let currentTimeoutMinutes = 30;

        console.log("main.js gestartet (mit Online-Checkbox und RFID-Polling)");

        function updateModeIndicator(expiresAt) {
            if (inputMode && currentUserName) {
                let extra = "";
                if (currentTimeoutMinutes > 0 && expiresAt) {
                    extra = ` (Timeout: ${currentTimeoutMinutes} min)`;
                } else if (currentTimeoutMinutes === 0) {
                    extra = " (kein Auto-Logout)";
                }
                modeIndicator.textContent = `Modus: Eingabemodus (angemeldet: ${currentUserName})` + extra;
            } else {
                modeIndicator.textContent = "Modus: Scanmodus (kein Benutzer angemeldet)";
            }
        }

        async function pollCurrentUser() {
            try {
                const res = await window.pywebview.api.get_current_user();
                inputMode = !!res.user_id;
                currentUserName = res.user_name || "";
                currentTimeoutMinutes = typeof res.timeout_minutes === "number"
                    ? res.timeout_minutes
                    : currentTimeoutMinutes;

                if (timeoutInput) {
                    timeoutInput.value = currentTimeoutMinutes;
                }

                updateModeIndicator(res.expires_at);
            } catch (e) {
                console.log("Fehler bei get_current_user:", e);
            }
        }

        if (timeoutInput) {
            timeoutInput.addEventListener("change", async () => {
                const minutes = parseInt(timeoutInput.value, 10);
                try {
                    const res = await window.pywebview.api.set_session_timeout(isNaN(minutes) ? 0 : minutes);
                    currentTimeoutMinutes = res.timeout_minutes;
                    await pollCurrentUser();
                } catch (e) {
                    console.log("Fehler bei set_session_timeout:", e);
                }
            });
        }

        if (logoutBtn) {
            logoutBtn.addEventListener("click", async () => {
                try {
                    await window.pywebview.api.logout();
                    await pollCurrentUser();
                } catch (e) {
                    console.log("Fehler bei logout:", e);
                }
            });
        }

        // RFID-Status alle 2 Sekunden abfragen
        pollCurrentUser();
        setInterval(pollCurrentUser, 5000);

        if (toggleOnline) {
            toggleOnline.addEventListener("change", () => {
                useOnlineLookup = toggleOnline.checked;
                console.log("Online-Lookup:", useOnlineLookup);
            });
        }

        $("#reloadbutton").on('click', function () {
            window.location.reload();
        });

        // Beim Start Fokus + Selektion
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

                if (msg.type === "image_updated") {
                    console.log("Desktop: image_updated für EAN", msg.ean);
                    if (currentArticle.ean && msg.ean === currentArticle.ean) {
                        const img = document.getElementById("product-image");
                        img.src = "/image/" + encodeURIComponent(msg.ean) + "?t=" + Date.now();
                        img.style.display = "block";
                    }
                }
            };
        }

        connectWebSocketDesktop();

        async function lookup() {
            const ean = eanInput.value.trim();
            if (!ean) {
                alert("Bitte EAN eingeben.");
                setTimeout(() => {
                    eanInput.focus();
                    eanInput.select();
                }, 0);
                return;
            }

            // HIER: Flag wird an Python übergeben
            const result = await window.pywebview.api.lookup_ean(ean, useOnlineLookup);

            currentArticle.ean = result.ean || null;
            currentArticle.name = result.name || "";

            eanInput.value = result.ean || "";
            nameInput.value = result.name || "";
            document.getElementById("db-result").textContent =
                JSON.stringify(result, null, 2);

            const img = document.getElementById("product-image");
            if (result.ean) {
                img.src = "/image/" + encodeURIComponent(result.ean) + "?t=" + Date.now();
                img.style.display = "block";
            } else {
                img.src = "";
                img.style.display = "none";
            }

            if (wsDesktop && wsDesktop.readyState === WebSocket.OPEN) {
                const payload = {
                    type: "set_article",
                    ean: result.ean,
                    name: result.name
                };
                wsDesktop.send(JSON.stringify(payload));
            }

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

            setTimeout(() => {
                eanInput.focus();
                eanInput.select();
            }, 0);
        }

        // für onclick in index.html
        window.lookup = lookup;
        window.saveManual = saveManual;

        updateModeIndicator();
    });
});
