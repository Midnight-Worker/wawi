// ------------------------------------------------------------
// DOM-Elemente
// ------------------------------------------------------------
const eanEl = document.getElementById("ean");
const nameEl = document.getElementById("name");
const imgEl = document.getElementById("product-image");
const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");
const fileInput = document.getElementById("fileInput");
const saveNameBtn = document.getElementById("save-name-btn");
const userStatusEl = document.getElementById("user-status");
const captureControlsEl = document.getElementById("capture-controls");
const shopSelectEl = document.getElementById("shop-select");
const qtyEl = document.getElementById("qty");
const saveItemBtn = document.getElementById("save-item-btn");

// ------------------------------------------------------------
// State
// ------------------------------------------------------------
let loggedInUser = null;
let shops = [];
let lastSelectedShopId = null;
let wsMobile = null;
let currentArticle = null;   // { ean, name }
let reconnectTimeout = null;
let pendingUpload = null;    // { type, ean, image_base64 }

// ------------------------------------------------------------
// Helper
// ------------------------------------------------------------
function log(msg) {
    if (!logEl) return;
    logEl.textContent += msg + "\n";
    logEl.scrollTop = logEl.scrollHeight;
}

function updateUserStatus() {
    if (!userStatusEl || !captureControlsEl) return;

    if (loggedInUser && loggedInUser.user_id) {
        userStatusEl.textContent =
            "Modus: Eingabemodus (angemeldet: " + (loggedInUser.user_name || "?") + ")";
        captureControlsEl.style.display = "block";
    } else {
        userStatusEl.textContent = "Modus: Scanmodus (kein Benutzer angemeldet)";
        captureControlsEl.style.display = "none";
    }
}

// ------------------------------------------------------------
// Shops laden
// ------------------------------------------------------------
async function loadShops() {
    try {
        const res = await fetch("/api/shops");
        if (!res.ok) {
            return;
        }
        const data = await res.json();
        shops = data.shops || [];

        if (!shopSelectEl) return;

        shopSelectEl.innerHTML = "";
        shops.forEach((shop) => {
            const opt = document.createElement("option");
            opt.value = shop.id;
            opt.textContent = shop.name;
            shopSelectEl.appendChild(opt);
        });

        if (lastSelectedShopId) {
            shopSelectEl.value = String(lastSelectedShopId);
        }
    } catch (e) {
        log("Fehler bei /api/shops: " + e);
    }
}

if (shopSelectEl) {
    shopSelectEl.addEventListener("change", () => {
        lastSelectedShopId = shopSelectEl.value || null;
    });
}

// ------------------------------------------------------------
// Artikel-Rendering
// ------------------------------------------------------------
function updateImage(ean) {
    const key = ean || "dummy";
    imgEl.src = "/image/" + encodeURIComponent(key) + "?t=" + Date.now();
}

function renderArticle(article, imageBase64) {
    if (eanEl) {
        eanEl.textContent = article.ean || "–";
    }
    if (nameEl) {
        nameEl.value = article.name || ""; // vorhanden, aber editierbar
    }
    if (qtyEl) {
        qtyEl.value = "1";
    }

    if (imageBase64) {
        imgEl.src = "data:image/jpeg;base64," + imageBase64;
    } else {
        updateImage(article.ean);
    }
}


async function lookupAndRenderArticle(ean, imageBase64FromWs) {
    try {
        // 1) Artikel-Daten aus der API holen
        const res = await fetch("/api/lookup_ean?ean=" + encodeURIComponent(ean));
        const data = await res.json();

        const finalEan = data.ean || ean || "";
        const finalName =
            data.name ||
            (currentArticle && currentArticle.name) ||
            "";

        // globalen State aktualisieren
        currentArticle = {
            ean: finalEan,
            name: finalName,
        };

        // EAN & Name in die Felder schreiben
        if (eanEl) {
            eanEl.textContent = finalEan || "–";
        }
        if (nameEl) {
            nameEl.value = finalName;
        }

        // Menge aus DB übernehmen (falls vorhanden), sonst 1
        if (qtyEl) {
            if (
                data.qty != null &&
                !isNaN(data.qty) &&
                data.qty > 0
            ) {
                qtyEl.value = String(data.qty);
            } else {
                qtyEl.value = "1";
            }
        }

        // Shop aus DB übernehmen (falls vorhanden)
        if (data.shop_id) {
            lastSelectedShopId = String(data.shop_id);

            if (shopSelectEl) {
                shopSelectEl.value = lastSelectedShopId;
            }
        }

        // Bild setzen: erst WS-Bild, sonst normales /image/<ean>
        if (imageBase64FromWs) {
            imgEl.src = "data:image/jpeg;base64," + imageBase64FromWs;
        } else {
            updateImage(finalEan);
        }
    } catch (e) {
        log("lookupAndRenderArticle Fehler: " + e);
        // Fallback: wenigstens das anzeigen, was wir vom WS kennen
        if (currentArticle) {
            renderArticle(currentArticle, imageBase64FromWs);
        } else {
            renderArticle({ ean: ean, name: "" }, imageBase64FromWs);
        }
    }
}


// ------------------------------------------------------------
// Artikel speichern (/api/save_item)
// ------------------------------------------------------------
if (saveItemBtn) {
    saveItemBtn.addEventListener("click", async () => {
        if (!currentArticle || !currentArticle.ean) {
            log("Kein aktueller Artikel, nichts zu speichern.");
            return;
        }
        if (!loggedInUser || !loggedInUser.user_id) {
            log("Kein Benutzer eingeloggt – Artikel wird nicht gespeichert.");
            return;
        }

        const ean = currentArticle.ean;
        const name = (nameEl && nameEl.value.trim()) || "";
        const qtyVal = qtyEl ? qtyEl.value : "1";
        const shopId = shopSelectEl && shopSelectEl.value ? shopSelectEl.value : null;

        const payload = {
            ean: ean,
            name: name,
            qty: qtyVal,
            shop_id: shopId ? parseInt(shopId, 10) : null,
        };

        try {
            const res = await fetch("/api/save_item", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (data.ok) {
                log("Artikel gespeichert: " + (data.message || ""));
                if (qtyEl) {
                    qtyEl.value = "1";
                }
                // Nächster Artikel kommt vom Desktop per WS (current_article)
            } else {
                log("Fehler beim Speichern: " + (data.message || "Unbekannt"));
            }
        } catch (e) {
            log("Fehler bei /api/save_item: " + e);
        }
    });
}

// ------------------------------------------------------------
// WebSocket-Verbindung
// ------------------------------------------------------------
function connectWebSocketMobile() {
    const wsUrl = "ws://" + window.location.hostname + ":8765";
    log("Verbinde mit: " + wsUrl);

    wsMobile = new WebSocket(wsUrl);

    wsMobile.onopen = () => {
        if (statusEl) statusEl.textContent = "Verbindungsstatus: verbunden";
        log("WS verbunden");

        // aktuellen Artikel anfordern
        wsMobile.send(JSON.stringify({ type: "request_current_article" }));

        // ggf. ausstehenden Upload nachholen
        if (pendingUpload) {
            wsMobile.send(JSON.stringify(pendingUpload));
            log(
                "Nachträglich Bild nach Reconnect gesendet. Länge: " +
                    pendingUpload.image_base64.length
            );
            pendingUpload = null;
        }
    };

    wsMobile.onmessage = (e) => {
        log("WS Nachricht: " + e.data);
        let data;
        try {
            data = JSON.parse(e.data);
        } catch {
            return;
        }

        switch (data.type) {
            case "user_login":
                // User-Status im Frontend setzen
                loggedInUser = {
                    user_id: data.user_id,
                    user_name: data.user_name,
                };
                updateUserStatus();

                // von /mobile auf /mobile/erfassung wechseln
                if (window.location.pathname === "/mobile") {
                    log("user_login empfangen, wechsle zu /mobile/erfassung");
                    window.location.href = "/mobile/erfassung";
                }
                break;

            case "user_logout":
                // User ausloggen und Status anpassen
                loggedInUser = null;
                updateUserStatus();

                // egal wo wir sind → zurück zur Mobile-Startseite
                if (window.location.pathname !== "/mobile") {
                    log("user_logout empfangen, wechsle zurück zu /mobile");
                    window.location.href = "/mobile";
                }
                break;

            case "current_article":
                currentArticle = { ean: data.ean, name: data.name };
                // statt direkt renderArticle -> DB-Lookup + Rendering
                lookupAndRenderArticle(currentArticle.ean, data.image_base64);
                break;

            case "image_updated":
                if (currentArticle && currentArticle.ean === data.ean) {
                    if (data.image_base64) {
                        imgEl.src = "data:image/jpeg;base64," + data.image_base64;
                    } else {
                        updateImage(currentArticle.ean);
                    }
                }
                break;

            default:
                // andere Typen ignorieren
                break;
        }
    };

    wsMobile.onclose = () => {
        if (statusEl) statusEl.textContent = "Verbindungsstatus: getrennt";
        log("WS geschlossen, versuche Reconnect in 2s...");
        wsMobile = null;

        if (!reconnectTimeout) {
            reconnectTimeout = setTimeout(() => {
                reconnectTimeout = null;
                connectWebSocketMobile();
            }, 2000);
        }
    };

    wsMobile.onerror = (e) => {
        if (statusEl) statusEl.textContent = "Verbindungsstatus: Fehler";
        log("WS Fehler: " + e);
    };
}

// ------------------------------------------------------------
// Bild aufnehmen / hochladen
// ------------------------------------------------------------

// Bild antippen -> Kamera
if (imgEl && fileInput) {
    imgEl.addEventListener("click", () => {
        if (!currentArticle || !currentArticle.ean) {
            log("Kein aktueller Artikel (EAN) vorhanden.");
            return;
        }
        fileInput.value = "";
        fileInput.click();
    });

    // Bildauswahl -> per WS senden oder puffern
    fileInput.addEventListener("change", () => {
        const file = fileInput.files[0];
        if (!file) {
            log("Kein Bild ausgewählt.");
            return;
        }
        if (!currentArticle || !currentArticle.ean) {
            log("Kein aktueller Artikel gesetzt.");
            return;
        }

        const img = new Image();
        const url = URL.createObjectURL(file);

        img.onload = () => {
            URL.revokeObjectURL(url); // Blob-URL freigeben

            const MAX_SIZE = 600; // längere Seite max. 600px
            let w = img.width;
            let h = img.height;

            if (w > h && w > MAX_SIZE) {
                h = Math.round(h * (MAX_SIZE / w));
                w = MAX_SIZE;
            } else if (h >= w && h > MAX_SIZE) {
                w = Math.round(w * (MAX_SIZE / h));
                h = MAX_SIZE;
            }

            const canvas = document.createElement("canvas");
            canvas.width = w;
            canvas.height = h;
            const ctx = canvas.getContext("2d");
            ctx.drawImage(img, 0, 0, w, h);

            const compressedDataUrl = canvas.toDataURL("image/jpeg", 0.6);
            const base64Data = compressedDataUrl.split(",")[1];

            log(
                "Bild skaliert: " +
                    img.width +
                    "x" +
                    img.height +
                    " -> " +
                    w +
                    "x" +
                    h +
                    ", Base64-Länge: " +
                    Math.round(base64Data.length / 1024) +
                    " KB"
            );

            const payload = {
                type: "upload_image",
                ean: currentArticle.ean,
                image_base64: base64Data,
            };

            if (wsMobile && wsMobile.readyState === WebSocket.OPEN) {
                wsMobile.send(JSON.stringify(payload));
                log("Bild (skaliert) gesendet.");
            } else {
                pendingUpload = payload;
                log("WS nicht verbunden, Upload wird nach Reconnect gesendet.");
                if (!wsMobile || wsMobile.readyState === WebSocket.CLOSED) {
                    connectWebSocketMobile();
                }
            }
        };

        img.onerror = (e) => {
            log("Fehler beim Laden des Bildes: " + e);
            URL.revokeObjectURL(url);
        };

        img.src = url;
    });
}

// ------------------------------------------------------------
// Name speichern (per WS)
// ------------------------------------------------------------
function saveName() {
    if (!currentArticle || !currentArticle.ean) {
        log("Kein aktueller Artikel gesetzt, Name kann nicht gespeichert werden.");
        return;
    }

    const newName = nameEl.value.trim();
    if (!newName) {
        log("Leerer Name, nichts zu speichern.");
        return;
    }

    const payload = {
        type: "save_name",
        ean: currentArticle.ean,
        name: newName,
    };

    if (wsMobile && wsMobile.readyState === WebSocket.OPEN) {
        wsMobile.send(JSON.stringify(payload));
        log("Name für EAN " + currentArticle.ean + " gespeichert: " + newName);
        currentArticle.name = newName;
    } else {
        log("WebSocket nicht verbunden, Name konnte nicht gesendet werden.");
    }
}

if (nameEl) {
    nameEl.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
            ev.preventDefault();
            saveName();
        }
    });
}

if (saveNameBtn) {
    saveNameBtn.addEventListener("click", () => {
        saveName();
    });
}

// ------------------------------------------------------------
// Initialisierung
// ------------------------------------------------------------
window.addEventListener("load", () => {
    connectWebSocketMobile();
    loadShops();
    updateUserStatus(); // initial (kein User)
});
