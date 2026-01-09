const eanEl = document.getElementById("ean");
const nameEl = document.getElementById("name");
const imgEl = document.getElementById("product-image");
const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");
const fileInput = document.getElementById("fileInput");

let wsMobile = null;
let currentArticle = null;  // {ean, name}

function log(msg) {
    logEl.textContent += msg + "\n";
    logEl.scrollTop = logEl.scrollHeight;
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
    };

    wsMobile.onmessage = (e) => {
        log("WS Nachricht: " + e.data);
        let data;
        try {
            data = JSON.parse(e.data);
        } catch {
            return;
        }

        if (data.type === "current_article") {
            currentArticle = { ean: data.ean, name: data.name };
            renderArticle(currentArticle);
        } else if (data.type === "image_updated") {
            // Bild für bestimmte EAN wurde aktualisiert
            if (currentArticle && currentArticle.ean === data.ean) {
                updateImage(currentArticle.ean);
            }
        }
    };

    wsMobile.onclose = () => {
        statusEl.textContent = "Verbindungsstatus: getrennt";
        log("WS geschlossen");
    };

    wsMobile.onerror = (e) => {
        statusEl.textContent = "Verbindungsstatus: Fehler";
        log("WS Fehler: " + e);
    };
}

function renderArticle(article) {
    eanEl.textContent = article.ean || "–";
    nameEl.textContent = article.name || "–";
    updateImage(article.ean);
}

function updateImage(ean) {
    const key = ean || "dummy";
    // Cache-Buster, damit das neue Bild auch sicher geladen wird
    imgEl.src = "/image/" + encodeURIComponent(key) + "?t=" + Date.now();
}

// Klick auf das Bild -> Kamera / Dateiauswahl öffnen
imgEl.addEventListener("click", () => {
    if (!currentArticle || !currentArticle.ean) {
        log("Kein aktueller Artikel (EAN) vorhanden.");
        return;
    }
    fileInput.value = "";  // alten Wert zurücksetzen
    fileInput.click();
});

// Wenn ein Bild ausgewählt / aufgenommen wurde -> per WS senden
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

    const reader = new FileReader();
    reader.onload = () => {
        const base64Data = reader.result.split(",")[1]; // 'data:image/...;base64,...'
        const payload = {
            type: "upload_image",
            ean: currentArticle.ean,
            image_base64: base64Data
        };

        if (wsMobile && wsMobile.readyState === WebSocket.OPEN) {
            wsMobile.send(JSON.stringify(payload));
            log("Bild für EAN " + currentArticle.ean + " gesendet.");
        } else {
            log("WebSocket nicht verbunden.");
        }
    };
    reader.readAsDataURL(file);
});

window.addEventListener("load", connectWebSocketMobile);