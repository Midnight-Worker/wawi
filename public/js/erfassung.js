 // --- Globale Zustände ---
    window.currentItem = {
      ean: "",
      name: "",
      shop_id: null,
      qty: 1,
      image_uploaded: false,
    };
    let currentStepIndex = 0;
    const stepOrder = ["scan", "name", "foto", "shop", "qty"];
    const recentItems = [];


    // --- WebSocket für EAN-Weiterleitung vom Desktop ---
    let ws = null;

    function setupWebSocket() {
      const proto = window.location.protocol === "https:" ? "wss://" : "ws://";
      const wsUrl = proto + window.location.hostname + ":8765";

      console.log("Verbinde WebSocket:", wsUrl);
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log("[WS] verbunden");
        // Optional: direkt nach aktuellem Artikel fragen
        ws.send(JSON.stringify({ type: "request_current_article" }));
      };

      ws.onmessage = (event) => {
        let data;
        try {
          data = JSON.parse(event.data);
        } catch (e) {
          console.log("[WS] JSON-Fehler:", e);
          return;
        }

        if (data.type === "current_article") {
          console.log("[WS] current_article:", data);
          const ean = (data.ean || "").trim();
          if (!ean) return;

          // Nur automatisch starten, wenn wir in der Übersicht sind
          const wizardVisible = !$("wizardStep").classList.contains("hidden");
          if (wizardVisible) {
            // Wir sind schon mitten im Wizard -> nichts tun oder ggf. bestätigen
            return;
          }

          startWizardWithEan(ean);
        }
      };

      ws.onclose = () => {
        console.log("[WS] Verbindung geschlossen, versuche neu…");
        // nach kurzer Zeit reconnecten
        setTimeout(setupWebSocket, 2000);
      };

      ws.onerror = (err) => {
        console.log("[WS] Fehler:", err);
      };
    }



    // --- DOM-Helper ---
    function $(id) {
      return document.getElementById(id);
    }

    function setStatus(el, msg, type) {
      el.textContent = msg || "";
      el.classList.remove("ok", "error");
      if (type) el.classList.add(type);
    }

    function setStep(stepName) {
      currentStepIndex = stepOrder.indexOf(stepName);
      document.querySelectorAll(".wizard-page").forEach((el) => el.classList.add("hidden"));
      document.querySelectorAll(".step").forEach((el) => el.classList.remove("active"));

      const page = $("step" + stepName.charAt(0).toUpperCase() + stepName.slice(1));
      if (page) page.classList.remove("hidden");

      document
        .querySelectorAll('.step[data-step="' + stepName + '"]')
        .forEach((el) => el.classList.add("active"));
    }

    function refreshRecent() {
      const container = $("recentList");
      container.innerHTML = "";
      if (!recentItems.length) {
        container.innerHTML =
          '<div class="overview-item">– Noch keine Artikel in dieser Session –</div>';
        return;
      }
      recentItems
        .slice(-10)
        .slice()
        .reverse()
        .forEach((item) => {
          const div = document.createElement("div");
          div.className = "overview-item";
          div.textContent =
            item.ean + " · " + (item.name || "(kein Name)") + " · " + (item.qty || 0);
          container.appendChild(div);
        });
    }

    // --- User / Session Polling ---
    async function pollCurrentUser() {
      try {
        const res = await fetch("/api/current_user");
        const data = await res.json();
        if (data.user_id) {
          $("userDisplay").textContent = data.user_name + " (ID " + data.user_id + ")";
        } else {
          $("userDisplay").textContent = "Nicht eingeloggt";
          // Falls wir auf der Erfassungs-Seite sind und der User ist weg -> zurück zur Mobile-Startseite
          window.location.href = "/mobile";
        }
      } catch (e) {
        console.log("Fehler bei /api/current_user:", e);
      }
    }

    setInterval(pollCurrentUser, 5000);
    pollCurrentUser();

    // --- Logout ---
    $("logoutBtn").addEventListener("click", async () => {
      try {
        const res = await fetch("/api/logout", { method: "POST" });
        // Du hast in Python ein Api.logout(), aber noch keine HTTP-Route.
        // Falls du eine Route /api/logout baust, kann die hier aufgerufen werden.
      } catch (e) {}
      window.location.href = "/mobile";
    });

    // --- Start: Overview (warten auf Scan) ---
    function showOverview() {
      $("overviewStep").classList.remove("hidden");
      $("wizardStep").classList.add("hidden");
      $("eanInput").value = "";
      $("eanInput").focus();
      setStatus($("overviewStatus"), "", null);
    }

    function startWizardWithEan(ean) {
      window.currentItem = {
        ean: ean,
        name: "",
        shop_id: null,
        qty: 1,
        image_uploaded: false,
      };
      $("currentEanDisplay").textContent = ean;
      $("overviewStep").classList.add("hidden");
      $("wizardStep").classList.remove("hidden");
      setStatus($("wizardStatus"), "", null);
      setStep("scan");
      lookupEan(ean);
    }

    // --- EAN-Input / Scan erkennen ---
    $("eanInput").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        const ean = $("eanInput").value.trim();
        if (!ean) {
          setStatus($("overviewStatus"), "Bitte EAN scannen/eingeben.", "error");
          return;
        }
        startWizardWithEan(ean);
      }
    });

    // --- EAN-Lookup: intern + optional extern ---
    async function lookupEan(ean) {
      setStatus($("wizardStatus"), "Prüfe interne Datenbank…", null);
      try {
        // 1) intern
        let res = await fetch("/api/lookup_ean?ean=" + encodeURIComponent(ean));
        let data = await res.json();

        if (data && data.ean) {
          window.currentItem.name = data.name || "";
          window.currentItem.shop_id = data.shop_id || null;
          window.currentItem.qty = data.qty || 1;

          if (data.name) {
            $("nameInput").value = data.name;
          } else {
            $("nameInput").value = "";
          }

          if (data.image_path) {
            $("itemImage").src = "/image/" + ean + "?t=" + Date.now();
          } else {
            $("itemImage").src = "/image/" + ean + "?t=" + Date.now();
          }

          if (data.source === "local") {
            setStatus($("wizardStatus"), "Artikel in lokaler Datenbank gefunden.", "ok");
          } else {
            setStatus(
              $("wizardStatus"),
              "Keine lokalen Daten gefunden. Optional kann später ein Name und Bild vergeben werden.",
              null
            );
          }
        } else {
          setStatus(
            $("wizardStatus"),
            "Keine lokalen Daten gefunden. Optional kann später ein Name und Bild vergeben werden.",
            null
          );
        }

        // 2) optional extern (online=1) – kann später mit echter externen API gefüllt werden
        /*
        setStatus($("wizardStatus"), "Prüfe externe Datenbank…", null);
        let resExt = await fetch("/api/lookup_ean?ean=" + encodeURIComponent(ean) + "&online=1");
        let dataExt = await resExt.json();
        if (dataExt && dataExt.name && !window.currentItem.name) {
          window.currentItem.name = dataExt.name;
          $("nameInput").value = dataExt.name;
          setStatus($("wizardStatus"), "Name aus externer Datenbank übernommen.", "ok");
        }
        */

        // Direkt zur Namens-Eingabe springen
        setStep("name");
        $("nameInput").focus();
      } catch (e) {
        console.log("lookupEan Fehler:", e);
        setStatus($("wizardStatus"), "Fehler beim Lookup der EAN.", "error");
        setStep("name");
      }
    }

    async function loadShops() {
    try {
        const res = await fetch("/api/shops");
        const data = await res.json();
        const select = $("shopSelect");
        select.innerHTML = "";

        const leer = document.createElement("option");
        leer.value = "";
        leer.textContent = "(kein Shop)";
        select.appendChild(leer);

        const currentShopId =
        window.currentItem.shop_id != null ? String(window.currentItem.shop_id) : "";

        (data.shops || []).forEach((shop) => {
        const opt = document.createElement("option");
        opt.value = String(shop.id);
        opt.textContent = shop.name;

        if (currentShopId && String(shop.id) === currentShopId) {
            opt.selected = true;   // <- vorhandenen Shop vorselektieren
        }

        select.appendChild(opt);
        });
    } catch (e) {
        console.log("Fehler beim Laden der Shops:", e);
    }
    }


    // --- Bild-Upload ---
    $("imageInput").addEventListener("change", async (ev) => {
      const file = ev.target.files[0];
      if (!file) return;
      const ean = window.currentItem.ean;
      if (!ean) return;

      setStatus($("wizardStatus"), "Lade Bild hoch…", null);
      const formData = new FormData();
      formData.append("image", file);

      try {
        const res = await fetch("/upload_image/" + encodeURIComponent(ean), {
          method: "POST",
          body: formData,
        });
        const data = await res.json();
        if (data.ok) {
          window.currentItem.image_uploaded = true;
          $("itemImage").src = "/image/" + ean + "?t=" + Date.now();
          setStatus($("wizardStatus"), "Bild gespeichert.", "ok");
        } else {
          setStatus($("wizardStatus"), data.message || "Fehler beim Speichern des Bildes.", "error");
        }
      } catch (e) {
        console.log("Bild-Upload Fehler:", e);
        setStatus($("wizardStatus"), "Fehler beim Upload.", "error");
      }
    });

    // --- Wizard Navigation ---
    $("backBtn").addEventListener("click", () => {
      if (currentStepIndex <= 0) {
        // zurück zur Übersicht
        showOverview();
        return;
      }
      currentStepIndex--;
      setStep(stepOrder[currentStepIndex]);
    });

    $("nextBtn").addEventListener("click", async () => {
      const step = stepOrder[currentStepIndex];

      if (step === "name") {
        window.currentItem.name = $("nameInput").value.trim();
        if (!window.currentItem.name) {
          setStatus($("wizardStatus"), "Bitte einen Artikelnamen eingeben.", "error");
          return;
        }
      } 
        else if (step === "shop") {
            const val = $("shopSelect").value;
            window.currentItem.shop_id = val ? parseInt(val, 10) : null;
        } 
        else if (step === "qty") {
            const val = parseFloat($("qtyInput").value.replace(",", "."));
            if (isNaN(val) || val <= 0) {
            setStatus($("wizardStatus"), "Bitte eine sinnvolle Menge eingeben.", "error");
            return;
            }
            window.currentItem.qty = val;

            // Hier wird gespeichert
            await saveItemAndFinish();
            return;
        }

      if (step === "scan") {
        setStep("name");
        $("nameInput").focus();
      } else if (step === "name") {
        setStep("foto");
      } else if (step === "foto") {
        await loadShops();
        setStep("shop");
      } else if (step === "shop") {
            setStep("qty");

            // vorhandene Menge aus der DB in das Feld eintragen (falls > 0)
            if (
            window.currentItem.qty != null &&
            !isNaN(window.currentItem.qty) &&
            window.currentItem.qty > 0
            ) {
            $("qtyInput").value = window.currentItem.qty;
            } else {
            $("qtyInput").value = 1;
            }

            $("qtyInput").focus();
        }
    });

    // --- Speichern in /api/save_item ---
    async function saveItemAndFinish() {
      const payload = {
        ean: window.currentItem.ean,
        name: window.currentItem.name,
        shop_id: window.currentItem.shop_id,
        qty: window.currentItem.qty,
      };

      setStatus($("wizardStatus"), "Speichere Artikel…", null);

      try {
        const res = await fetch("/api/save_item", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (data.ok) {
          setStatus($("wizardStatus"), "Artikel gespeichert.", "ok");
          recentItems.push({
            ean: window.currentItem.ean,
            name: window.currentItem.name,
            qty: window.currentItem.qty,
          });
          refreshRecent();

          // kurz warten und dann zurück zur Übersicht
          setTimeout(() => {
            showOverview();
          }, 800);
        } else {
          setStatus(
            $("wizardStatus"),
            data.message || "Fehler beim Speichern des Artikels.",
            "error"
          );
        }
      } catch (e) {
        console.log("save_item Fehler:", e);
        setStatus($("wizardStatus"), "Fehler beim Speichern des Artikels.", "error");
      }
    }

    // --- Initial ---
    showOverview();
    refreshRecent();
    setupWebSocket();
