window.addEventListener('pywebviewready', function () {

const input = document.getElementById('ean-input');
const resultDiv = document.getElementById('result');
const manualSection = document.getElementById('manual-section');
const manualEanLabel = document.getElementById('manual-ean-label');
const manualName = document.getElementById('manual-name');
const manualBrand = document.getElementById('manual-brand');
const manualSaveBtn = document.getElementById('manual-save-btn');
const manualMessage = document.getElementById('manual-message');

let lastEan = "";

function showResult(data) {
    // immer erstmal die manuelle Sektion ausblenden
    manualSection.style.display = 'none';
    manualMessage.textContent = '';

    if (!data.ok) {
        resultDiv.innerHTML = '<p class="error">' + (data.message || 'Unbekannter Fehler') + '</p>';

        // Manuelles Formular anzeigen
        lastEan = data.ean;
        manualEanLabel.textContent = 'EAN: ' + data.ean;
        manualName.value = '';
        manualBrand.value = '';
        manualSection.style.display = 'block';
        return;
    }

    resultDiv.innerHTML = `
        <p><strong>Quelle:</strong> ${data.source}</p>
        <p><strong>EAN:</strong> ${data.ean}</p>
        <p><strong>Name:</strong> ${data.name}</p>
        <p><strong>Marke:</strong> ${data.brand || '-'}</p>
    `;
}

input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
        const ean = input.value.trim();
        if (!ean) return;

        lastEan = ean;
        resultDiv.innerHTML = '<p>Suche nach ' + ean + ' ...</p>';
        manualSection.style.display = 'none';
        manualMessage.textContent = '';

        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.lookup_ean(ean).then(showResult);
        } else {
            resultDiv.innerHTML = '<p class="error">pywebview API nicht verfügbar.</p>';
        }

        input.value = '';
    }
});

// Produkt speichern-Button
manualSaveBtn.addEventListener('click', function () {
    const name = manualName.value.trim();
    const brand = manualBrand.value.trim();

    if (!lastEan || !name) {
        manualMessage.textContent = 'Bitte mindestens EAN (per Scan) und Name angeben.';
        return;
    }

    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.save_product(lastEan, name, brand).then(function (res) {
            if (res.ok) {
                manualMessage.textContent = 'Gespeichert.';
            } else {
                manualMessage.textContent = 'Fehler: ' + (res.message || 'Unbekannt');
            }
        });
    } else {
        manualMessage.textContent = 'pywebview API nicht verfügbar.';
    }
});

// Fokus im Feld halten
window.addEventListener('click', () => input.focus());


});
