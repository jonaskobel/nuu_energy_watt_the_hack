# Wärmeweise · Wärmepumpen-Check

Aktuelle v2-Website mit fünf Formularschritten, Ergebnisansicht und vorbereitetem Chatfeld. **Es ist kein lokales LLM installiert oder aktiviert.** Die Berechnungen laufen mit den bestehenden Python-Modulen.

## Öffentliche Demo

[Öffentliche Website öffnen](https://truly-freebsd-graduates-harvey.trycloudflare.com)

Der Link ist temporär und funktioniert, solange der Laptop und sein Tunnel laufen. GitHub enthält den vollständigen Quellcode und die Startskripte; GitHub selbst führt den Python-Server nicht aus.

## Unter Windows starten

Python 3.9 oder neuer ist erforderlich. Im ausgecheckten Repository-Ordner:

```powershell
.\Start-PublicDemo.ps1
```

Das Skript lädt bei Bedarf das offizielle `cloudflared` herunter, startet die Website und gibt den öffentlichen Link aus. Die lokale Adresse ist dann **http://localhost:8012**. Keine zusätzlichen Python-Pakete nötig.

Nach einem Update der Dateien den Webserver neu laden, ohne den laufenden öffentlichen Link zu ändern:

```powershell
git pull --ff-only
.\Start-PublicDemo.ps1 -Restart
```

Beenden: `.\Stop-PublicDemo.ps1`. Details stehen in [PUBLIC_DEMO.md](PUBLIC_DEMO.md). Programmdateien und Laufzeitdaten liegen im ignorierten Ordner `.runtime/` und werden nicht in Git hochgeladen.

---


Lokaler Hackathon-Prototyp für die nuuEnergy Challenge. Eingaben → Einzelkennzahlmodule → Output-Dataclass → separater Validator.

## Start

Python 3.9 oder neuer, keine Pflichtpakete:

```bash
python3 -m heat_pump_ready
```

Öffnen: **http://localhost:8000**. Beenden mit `Ctrl+C`. Alternativer Port: `python3 -m heat_pump_ready --port 8001`.

Für eine vollständige Demo im Formular **„Vollständiges Demohaus (synthetisch)“** auswählen und berechnen. Die B-01–B-05-Beispiele enthalten nur bekannte Angaben aus der Projektbeschreibung; fehlende Werte werden nicht erfunden.

## Dokumentation

- [Projektbeschreibung](project_description.md): konsolidierte Challenge-Anforderungen.
- [Ausführliches Konzept](KONZEPT.md): Verträge, Module, Berechnungen, Entscheidung und Grenzen.
- [Validierungsstand](docs/VALIDIERUNG.md): durchgeführte Prüfungen und Grenzen.
- [Coding Principles](CODING_PRINCIPLES.md): Entwicklungsregeln.
- [Originalbeschreibung](docs/project_description_original.md): unveränderte Ausgangsfassung.

## Fachliche Weiterarbeit

- [Offene Punkte und Demoannahmen](docs/OFFENE_PUNKTE.md): priorisierte Checkliste mit Abnahmekriterien.
- [Alle Berechnungen und offizielle Quellen](docs/BERECHNUNGEN.md): Formeln, Herkunft, Gültigkeit und Grenzen pro Modul.
- [Testprotokoll](docs/TESTPROTOKOLL.md): Testdaten, Rechenfälle, Fachvergleich, LLM-/Browserprüfung und Freigabe.

Die vollständigen Entwicklungsdaten sind inzwischen unter `data/dev_csv/` vorhanden. Die Browser-Beispiele verwenden weiterhin die verkürzten fest hinterlegten Angaben; der Originaldatenimport ist ein offener Arbeitspunkt. Die neue Dokumentation enthält einen Diagnosevergleich der drei dev-Fälle.

## LLM-Modi

Standard ist `disabled`: Alle numerischen Berechnungen funktionieren mit manuellen Angaben. Bild- und Rechnungserkennung bleiben unbekannt.

API-Modus für einen Chat-Completions-kompatiblen Endpunkt:

```bash
export LLM_API_URL='https://YOUR-PROVIDER/v1/chat/completions'
export LLM_MODEL='YOUR-VISION-MODEL'
# LLM_API_KEY über deine lokale Umgebung setzen, nicht ins Repository schreiben.
python3 -m heat_pump_ready --runner api
```

Der konfigurierte Anbieter muss Bildnachrichten unterstützen. Es gibt keine automatische Weiterleitung lokaler Daten an eine API. Der aktivierte API-Modus zeigt den externen Datentransfer im Uploadbereich an.

Optional lokal auf Apple Silicon:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install mlx-vlm Pillow pypdfium2
# Standardmodell: mlx-community/gemma-4-12B-it-4bit
# Optional mit LLM_MODEL ein anderes kompatibles Vision-Modell wählen.
python -m heat_pump_ready --runner mlx
```

Eine kompatible Python-/MLX-Version und genügend Speicher sind erforderlich. Im MLX-Modus wird standardmäßig das vorhandene `mlx-community/gemma-4-12B-it-4bit` verwendet; `LLM_MODEL` überschreibt diese Auswahl; Verfügbarkeit und Kompatibilität des konkreten Modells wurden hier nicht live verifiziert. Die vorhandene Gemma-Experimentdatei bleibt erhalten, wird aber nicht importiert.

Die Rohrsystem-Auswertung ist als `PipeSystemModule` in der Orchestrator-Pipeline
registriert. Heizungsanschlussfotos aus `heating_connection_images` und bestehende
Uploads der Kategorie `pipes` werden einzeln an das Modell gesendet. Jede
Bildentscheidung mit Begründung und das Stimmenverhältnis stehen in den
Ergebnisgrundlagen. Die Mehrheit der bestimmbaren Bilder entscheidet zwischen
Einrohr- und Zweirohrsystem; uneindeutige Bilder und Fehler enthalten sich.
Bei Gleichstand oder ohne bestimmbare Bilder bleibt das Rohrsystem offen.
Manuelle Rohrsystemangaben haben weiterhin Vorrang.

Das anschließende `RadiatorTypeModule` klassifiziert genau ein Foto der Kategorie
`radiator` mit demselben konfigurierten Vision-Modell. Das Prompt-Template
`RADIATOR_TYPE_PROMPT` in `calculation/modules/radiator_type.py` unterscheidet
Typ 11, 22 und 33 anhand sichtbarer Heizplatten und Konvektorlagen. Verdeckte,
uneindeutige oder nicht unterstützte Typen bleiben offen. Die strukturierte
JSON-Ausgabe wird wie beim Rohrsystem geprüft. Das Ergebnis samt Begründung
erscheint direkt unter der Rohrsystem-Auswertung.

Nach Berechnung und regelbasierter Validierung erstellt das konfigurierte Modell
zusätzlich eine ausführliche Investitionsempfehlung. Das Template steht in
`heat_pump_ready/llm/prompts/investment_recommendation.txt`. Es erhält Eingabefakten,
alle Kennzahlen mit Status und Unsicherheit sowie die Rechenannahmen und
Prüfentscheidung; Rohdateien und Testreferenzen werden nicht mitgeschickt.
Die Empfehlung erscheint unter beiden Bildauswertungen und ist als separates
`recommendation`-Objekt auch im JSON-Download enthalten. Sie erläutert technische
Eignung, Wirtschaftlichkeit, offene Punkte und nächste Schritte. Ungeklärte
Prüfergebnisse können nicht zu einer positiven Zusage aufgewertet werden.
Ein Modellfehler lässt die berechneten Ergebnisse verfügbar. Im Offline-Modus
wird die Empfehlung als deaktiviert angezeigt. Der zusätzliche Modellaufruf
benötigt mehr Zeit; die Drei-Minuten-Zielzeit muss auf der Demo-Hardware neu
gemessen werden.

Im Verbrauchsschritt gibt es zusätzlich einen eigenen Upload für Rechnungsfotos
und Rechnungs-PDFs. Beide Uploadwege verwenden die bestehende Kategorie `bill`.
`AnnualConsumptionModule` extrahiert fehlenden Jahresverbrauch mit dem Template
`BILL_CONSUMPTION_PROMPT`; ein manuell eingetragener Wert hat Vorrang.
PDF-Seiten werden mit dem optionalen `pypdfium2` nur im Speicher zu Bildern
umgewandelt. Insgesamt sind sechs Rechnungsseiten zulässig. Dokumente werden
nicht dauerhaft gespeichert. Ein annähernd jährlicher Abrechnungszeitraum
(330–400 Tage) wird mit dem dokumentierten Verbrauch ohne Hochrechnung übernommen
und als Näherung kenntlich gemacht. Monatsabschläge, Guthaben und Rechnungsbeträge
sind keine Verbrauchswerte. Bei unleserlichen oder widersprüchlichen Dokumenten
bleiben die betroffenen Kennzahlen offen.

Mit erkanntem Verbrauch berechnet die bestehende Pipeline Nutzwärme, Heizlast,
Energiekosten, Ersparnis und gegebenenfalls Amortisation neu, soweit die übrigen
Eingaben ausreichen. Die Kostenberechnung verwendet weiterhin die Challenge-Tarife,
nicht den Gesamtbetrag oder Abschlag der Rechnung. Ohne Heizflächenart und nötige
Vorlauftemperatur (bzw. die vorhandene Fußbodenheizungsannahme) fehlt die JAZ;
ohne Investitionskosten ist keine Amortisation möglich. Modellwerte bleiben als
unbestätigte Extraktion markiert. Im Ergebnis und JSON wird die verwendete
Verbrauchsgrundlage zusätzlich unter `bill_analysis` angezeigt.

## Debugging in VS Code

Python-Interpreter mit `mlx-vlm` und `Pillow` auswählen. Unter **Run and Debug**
die Konfiguration **Debug pipeline (local Gemma)** wählen und mit **F5** starten.
Danach `http://localhost:8000` öffnen und eine Berechnung absenden, um die
Pipeline mit Breakpoints zu durchlaufen, etwa in `PipeSystemModule.calculate`.

## Tests

```bash
python3 -B -m unittest discover -s tests -v
```

## Demonstrationsgrenzen

- Einfache Amortisation ohne Zinsen, Wartung, Grundpreise und Preisentwicklung.
- Breite Demo-Heizlastspanne für nicht eindeutig definierte Gebäudeklassen.
- Konservative, noch nicht vollständig kalibrierte technische Ampel.
- Kein Vergleichstarif für Flüssiggas, Fernwärme oder direkte Elektroheizung.
- Rechnungs-PDFs werden mit pypdfium2 lokal gerendert; PDFs anderer Kategorien werden nicht ausgewertet.
- Außenstandortfotos und Freitext werden noch nicht fachlich ausgewertet.
- Entwicklungs-CSV/JSON sind vorhanden, aber noch nicht an die Browser-Demo angebunden. Eval-Quelldateien fehlen; fachliche Abweichungen sind im Testprotokoll dokumentiert.
- API/MLX-Inferenz benötigt separat konfigurierte Ressourcen; der Standardstart lädt kein Modell.

Die Anwendung speichert Uploads nicht dauerhaft. Der lokale Standardbibliothek-Server ist für den Hackathon vorgesehen und darf nicht als öffentlicher Produktionsserver eingesetzt werden.
