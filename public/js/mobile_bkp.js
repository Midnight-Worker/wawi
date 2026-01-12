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

let loggedInUser = null;
let shops = [];
let lastSelectedShopId = null;
let wsMobile = null;
let currentArticle = null;  // {ean, name}
let reconnectTimeout = null;
let pendingUpload = null;   // { type, ean, image_base64 }

function log(msg) {
    logEl.textContent += msg + "\n";
    logEl.scrollTop = logEl.scrollHeight;
}

function updateUserStatus() {
    if (loggedInUser && loggedInUser.user_id) {
        userStatusEl.textContent =
            "Modus: Eingabemodus (angemeldet: " + (loggedInUser.user_name || "?") + ")";
        captureControlsEl.style.display = "block";
    } else {
        userStatusEl.textContent = "Modus: Scanmodus (kein Benutzer angemeldet)";
        captureControlsEl.style.display = "none";
    }
}

async function pollCurrentUser() {
    try {
        const res = await fetch("/api/current_user");
        if (!res.ok) {
            return;
        }
        const data = await res.json();
        loggedInUser = data;
        updateUserStatus();
    } catch (e) {
        log("Fehler bei /api/current_user: " + e);
    }
}


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
        shops.forEach(shop => {
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

function renderArticle(article, imageBase64) {
    eanEl.textContent = article.ean || "–";
    nameEl.value = article.name || "";
    if (qtyEl) {
        qtyEl.value = "1";
    }

    if (imageBase64) {
        imgEl.src = "data:image/jpeg;base64," + imageBase64;
    } else {
        updateImage(article.ean);
    }
}

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
        const name = nameEl.value.trim();
        const qtyVal = qtyEl.value;
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
                qtyEl.value = "1";
                // Nächster Artikel: einfach am Scanner den nächsten Code scannen,
                // Desktop schickt dann per WS den neuen current_article.
            } else {
                log("Fehler beim Speichern: " + (data.message || "Unbekannt"));
            }
        } catch (e) {
            log("Fehler bei /api/save_item: " + e);
        }
    });
}


function connectWebSocketMobile() {
    const wsUrl = "ws://" + window.location.hostname + ":8765";
    log("Verbinde mit: " + wsUrl);

    wsMobile = new WebSocket(wsUrl);

    wsMobile.onopen = () => {
        statusEl.textContent = "Verbindungsstatus: verbunden";
        log("WS verbunden");

        // aktuellen Artikel anfordern
        wsMobile.send(JSON.stringify({ type: "request_current_article" }));

        // ggf. ausstehenden Upload nachholen
        if (pendingUpload) {
            wsMobile.send(JSON.stringify(pendingUpload));
            log("Nachträglich Bild nach Reconnect gesendet. Länge: " + pendingUpload.image_base64.length);
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
            // Wenn wir auf der normalen Mobile-Ansicht sind → zur Erfassungsansicht
            if (window.location.pathname === "/mobile") {
                window.location.href = "/mobile/erfassung";
            }
            break;

        case "user_logout":
            // Egal von wo → zurück zur normalen Mobile-Ansicht
            if (window.location.pathname !== "/mobile") {
                window.location.href = "/mobile";
            }
            break;

        case "current_article":
            currentArticle = { ean: data.ean, name: data.name };
            renderArticle(currentArticle, data.image_base64);
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
        statusEl.textContent = "Verbindungsstatus: getrennt";
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
        statusEl.textContent = "Verbindungsstatus: Fehler";
        log("WS Fehler: " + e);
    };
}

function renderArticle(article, imageBase64) {
    eanEl.textContent = article.ean || "–";
    nameEl.value = article.name || "";   // vorhandener Name wird angezeigt, ist aber editierbar

    if (imageBase64) {
        imgEl.src = "data:image/jpeg;base64," + imageBase64;
    } else {
        updateImage(article.ean);
    }
}

function updateImage(ean) {
    const key = ean || "dummy";
    imgEl.src = "/image/" + encodeURIComponent(key) + "?t=" + Date.now();
}

// Bild antippen -> Kamera
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
        URL.revokeObjectURL(url); // Blob-URL wieder freigeben

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
            img.width + "x" + img.height + " -> " +
            w + "x" + h + ", Base64-Länge: " +
            Math.round(base64Data.length / 1024) + " KB"
        );

        const payload = {
            type: "upload_image",
            ean: currentArticle.ean,
            image_base64: base64Data
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

// Name mit Enter speichern
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
        name: newName
    };

    if (wsMobile && wsMobile.readyState === WebSocket.OPEN) {
        wsMobile.send(JSON.stringify(payload));
        log("Name für EAN " + currentArticle.ean + " gespeichert: " + newName);
        currentArticle.name = newName;
    } else {
        log("WebSocket nicht verbunden, Name konnte nicht gesendet werden.");
    }
}



window.addEventListener("load", connectWebSocketMobile);
window.addEventListener("load", () => {
    connectWebSocketMobile();
    loadShops();
});


// Enter im Namensfeld -> speichern
nameEl.addEventListener("keydown", (ev) => {
    console.log("keydown im Name-Feld:", ev.key);
    if (ev.key === "Enter") {
        ev.preventDefault();
        saveName();
    }
});

// Klick auf den 💾-Button -> speichern
saveNameBtn.addEventListener("click", () => {
    saveName();
});

window.addEventListener("load", connectWebSocketMobile);

async function checkLoginAndRedirect() {
  try {
    const res = await fetch("/api/current_user");
    const data = await res.json();
    if (data.user_id) {
      // User ist eingeloggt -> zur Erfassungsansicht
      window.location.href = "/mobile/erfassung";
    }
  } catch (e) {
    console.log("Fehler bei /api/current_user:", e);
  }
}

// z.B. alle 3 Sekunden prüfen
setInterval(checkLoginAndRedirect, 3000);
checkLoginAndRedirect();