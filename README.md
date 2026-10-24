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
python -m pip install mlx-vlm Pillow
export LLM_MODEL='YOUR-COMPATIBLE-MLX-VISION-MODEL'
python -m heat_pump_ready --runner mlx
```

Eine kompatible Python-/MLX-Version und genügend Speicher sind erforderlich. Der gewünschte Gemma-Modellpfad kann über `LLM_MODEL` eingesetzt werden; Verfügbarkeit und Kompatibilität des konkreten Modells wurden hier nicht live verifiziert. Die vorhandene Gemma-Experimentdatei bleibt erhalten, wird aber nicht importiert.

## Tests

```bash
python3 -B -m unittest discover -s tests -v
```

## Demonstrationsgrenzen

- Einfache Amortisation ohne Zinsen, Wartung, Grundpreise und Preisentwicklung.
- Breite Demo-Heizlastspanne für nicht eindeutig definierte Gebäudeklassen.
- Konservative, noch nicht vollständig kalibrierte technische Ampel.
- Kein Vergleichstarif für Flüssiggas, Fernwärme oder direkte Elektroheizung.
- PDFs werden angenommen, aber noch nicht ausgewertet; für Modellanalyse Rechnungsfotos verwenden.
- Außenstandortfotos und Freitext werden noch nicht fachlich ausgewertet.
- Entwicklungs-CSV/JSON sind vorhanden, aber noch nicht an die Browser-Demo angebunden. Eval-Quelldateien fehlen; fachliche Abweichungen sind im Testprotokoll dokumentiert.
- API/MLX-Inferenz benötigt separat konfigurierte Ressourcen; der Standardstart lädt kein Modell.

Die Anwendung speichert Uploads nicht dauerhaft. Der lokale Standardbibliothek-Server ist für den Hackathon vorgesehen und darf nicht als öffentlicher Produktionsserver eingesetzt werden.
