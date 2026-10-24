# Checkliste: Demoannahmen und offene Punkte

**Stand: 24. Oktober 2026.** Grundlage: aktueller Code, neu vorhandene Entwicklungsdaten und die in [BERECHNUNGEN.md](BERECHNUNGEN.md) dokumentierte Recherche. Diese Checkliste ändert keine Berechnung. Bereits vorhandene Codeänderungen bleiben erhalten.

## 1. Was ist derzeit eine Demo?

Nicht alle Konstanten sind frei erfundene Demowerte. Vier Kategorien unterscheiden:

- **Challenge-Vorgabe:** für die Vergleichbarkeit fest vorgegeben, aber nicht individuell gemessen.
- **Eigene Demoannahme:** vom Prototyp ergänzte, noch nicht fachlich freigegebene Regel.
- **Nutzerwert:** eingegeben oder aus einer Rechnung übernommen; muss zum richtigen Zeitraum und Gebäude gehören.
- **Fachliche Definition:** etwa Energie geteilt durch Zeit oder JAZ als Verhältnis von Wärme zu Strom. Eine richtige Formel macht unpassende Eingaben nicht richtig.

| Stelle | Aktueller Wert / Verhalten | Kategorie | Bedeutung |
|---|---|---|---|
| `config.py`: `boiler_efficiency` | 0,88 | Challenge | Pauschaler Jahresnutzungsgrad, nicht aus dem realen Kessel abgeleitet |
| `config.py`: `hot_water_kwh_per_person` | 1.000 kWh/(Person·a) | Challenge | Keine Messung; Solarthermie und individuelle Nutzung fehlen |
| `config.py`: `full_load_hours` | 2.000 h/a | Challenge | Nicht standort- oder witterungsabhängig |
| `config.py`: `fuel_kwh_per_unit` | 10 kWh/m³ bzw. kWh/l | Challenge-Näherung | Gas benötigt eigentlich Brennwert und Zustandszahl; Öl benötigt einen eigenen Energiefaktor |
| `config.py`: drei Energiepreise | Strom 0,26; Gas 0,11; Öl 0,17 €/kWh | Challenge | Keine aktuellen Angebote, Grundpreise fehlen |
| `config.py`: JAZ | 4,0 / 3,5 / 2,8 | Challenge | Tabellenzuordnung, keine Anlagenprognose nach VDI 4650 |
| `heat_load_area.py` | 15–40 / 40–60 / 80–120 / 120–180 W/m² | Challenge-Richtwerte | Klassenabhängige Schätzung, keine Norm-Heizlast |
| `heat_load_area.py` | Fallback 40–180 W/m² | **Eigene Demo** | Sehr breites Intervall bei unklarer Zuordnung; `demonstration=True` |
| `annual_performance_factor.py` | Fußbodenheizung ohne Temperatur → JAZ 4 | **Zusätzliche Annahme** | Niedrigtemperaturbetrieb wird unterstellt; bisher kein Demo-Flag |
| `annual_performance_factor.py` | Mischsystem nach einem Vorlaufwert | **Vereinfachung** | Unterschiedliche Kreise und Warmwasser-JAZ fehlen |
| `payback_period.py` | Nettoinvestition / jährliche Energieersparnis | **Demo-Wirtschaftlichkeitsmodell** | Ohne Zins, Wartung, Ersatz, Restwert oder Alternative; immer Demo-Flag |
| `config.py`: `discrepancy_ratio` | Faktor 2 | **Eigene Demo** | Frei gewählte Plausibilitätsgrenze, keine Normtoleranz |
| `readiness.py` | Ampel aus Heizlast, Temperatur und Hydraulik (`readiness-criteria-v1`) | **Eigene Demo** | Keine reale Leistungsdeckung, Elektrik oder Standortprüfung |
| `config.py`: `low_temperature_max_w_per_m2` | 60 W/m² → ohne Vorlauf wahrscheinlich ≤ 55 °C | **Eigene Ergänzung** | In Kenntnis von B-01–B-03 gewählt; W/m² ist ein Gebäudemittel, keine raumweise Heizkörperprüfung |
| `config.py`: `two_pipe_likely_from_year` | ab Baujahr 1995 Zweirohr als Indiz | **Eigene Ergänzung** | Gegenbeispiel B-04 (1987, Einrohr); nur schwaches Indiz |
| `validator.py` | Wirtschaftlichkeit anhand einfacher Amortisation | **Eigene Demo** | Keine belastbare Investitionsfreigabe |
| `contracts.py`: `horizon_years` | Standard 20 Jahre | UI-Standard | Vom Nutzer änderbar; keine garantierte Lebensdauer |
| `demo_cases.py`: `SYNTHETIC` | u. a. 24.000 kWh, 20.000 € Investition, 8.000 € Förderung | **Synthetische Testdaten** | Kein Angebot, kein Förderanspruch, kein reales Gebäude |

**Kennzeichnungslücke:** Ein fehlendes `demonstration=True` bedeutet aktuell nicht, dass die Kennzahl gemessen oder fachlich bestätigt ist. Die Demo-Flag-Weitergabe und die Verarbeitung von `uncertainty` decken nicht sämtliche Annahmen ab.

## 2. Neu festgestellter Datenstand

Vorhanden sind jetzt:

- [Entwicklungsdaten als JSON](../data/dev_csv/buildings_dev.json).
- [Entwicklungsdaten als CSV](../data/dev_csv/buildings_dev.csv).

Der Browser lädt weiterhin verkürzte, fest hinterlegte Fälle aus `demo_cases.py`, nicht diese Dateien. Eval-Quelldateien und bestätigte Bildsets wurden im Datenordner nicht gefunden. CSV und JSON enthalten unterschiedliche Textkodierung: Im JSON treten beispielsweise `FlÃ¼ssiggas` und `mÂ²` auf, im CSV die lesbaren Zeichen. Originaldateien deshalb nicht ungeprüft umkodieren; einen bereinigten Import mit Herkunft erstellen.

### Diagnose mit vollständigen Entwicklungsangaben

Read-only-Lauf mit explizitem Mapping der JSON-Felder, LPG-Korrektur aus `energy_carrier_detail`, keinen Referenzwerten im Input und deaktiviertem LLM:

| Fall | Heizlast aus Verbrauch | Referenz | Relative Abweichung | Ampel Ist / Referenz |
|---|---:|---:|---:|---|
| B-01 | 2,40 kW | 9,60 kW | −75,00 % | Gelb / Grün |
| B-02 | 5,32 kW | 9,70 kW | −45,15 % | Gelb / Grün |
| B-03 | 16,60 kW | 14,50 kW | +14,48 % | Gelb / Gelb |

Alle drei Investitionsentscheidungen bleiben offen; Investitionskosten und Förderung fehlen. Das ist erwartbar. Die Heizlastabweichungen zeigen dagegen, dass bestandene Softwaretests noch keine fachliche Validierung ersetzen.

## 3. P0 – vor belastbaren Aussagen erledigen

- [ ] **D01 – Originaldaten anbinden.** CSV-/JSON-Importer schreiben; `annual_consumption_kwh` auf internen Verbrauch mappen, CSV-`yes/no` in Boolean umwandeln, `null` als unbekannt behandeln. Referenzen separat halten. **Fertig:** Browser und Batchlauf verwenden dieselben vollständigen Eingaben.
- [ ] **D02 – LPG korrekt übernehmen.** `energy_carrier=gas` plus LPG im Detailfeld muss intern `lpg` werden. **Fertig:** B-01 erhält niemals automatisch den Erdgaspreis.
- [ ] **D03 – Datenkodierung und Konsistenz prüfen.** CSV und JSON feldweise vergleichen; bereinigte Texte mit Originalbezug ablegen. **Fertig:** Unterschiede protokolliert, keine Rohdatei überschrieben.
- [ ] **F01 – Energie-Bilanzgrenze festlegen.** Endenergie, Wärmeerzeugerausgang, Raumwärme, Warmwasser sowie Speicher-/Verteilungsverluste eindeutig zuordnen. Heizwert/Brennwertbasis des Nutzungsgrades klären. **Fertig:** jede Formel hat eine konsistente Bilanzgrenze.
- [ ] **F02 – Zusatzwärme erfassen.** Strukturierte Felder für Holzofen und Solarthermie, thermische Mengen beziehungsweise unbekannten Beitrag ergänzen. B-02 ist der erste Pflichtfall. **Fertig:** unbekannte Beiträge werden als Unsicherheit verarbeitet; Gasverbrauch wird nicht als vollständiger Gebäudebedarf ausgegeben.
- [ ] **F03 – B-01-Abweichung aufklären.** Verbrauchszeitraum, beheizte Fläche, Nutzung, LPG-Einheit und Referenzverfahren mit Datengeber prüfen. **Fertig:** nachvollziehbarer Grund für 2,4 gegenüber 9,6 kW; keine Gebäude-ID-Sonderformel.
- [ ] **F04 – Heizlastverfahren fachlich freigeben.** Challenge-Schätzung und fachliche Planung getrennt benennen; Flächenklassen samt 1979/2000/2001/Teilsanierung entscheiden. **Fertig:** versionierte Tabelle mit begründeten Gültigkeitsbereichen.
- [x] **F05 – Grün-Regel korrigieren.** Aktuell reichen JAZ und Zweirohrsystem sogar bei fehlender Heizlast für technisches Grün. **Fertig:** Grün benötigt definierte Mindestbelege; fehlende Daten und Hindernisse sind unterscheidbar. *Erledigt mit `readiness-criteria-v1` (KONZEPT §9.3, `tests/test_readiness.py`).*
- [ ] **F06 – Fußbodenheizung und Einrohrsystem differenzieren.** Unbekanntes Rohrsystem bei überwiegender Fußbodenheizung nicht pauschal wie ein ungeklärter Heizkörperring behandeln; B-02 enthält zudem einen Heizkörper. **Fertig:** mit Fachbetrieb abgestimmte Regeln und Gegenbeispiele. *Stand: Reine Fußbodenheizung braucht kein Rohrsystem mehr; der einzelne Heizkörper in B-02 wird nicht erfasst. Fachliche Abstimmung offen.*
- [ ] **F07 – Unsicherheit lückenlos weiterreichen.** Nicht nur Verbrauch und Rohrsystem berücksichtigen; Demonstrationsspannen, Zusatzwärme und Temperaturannahmen in Entscheidung einbeziehen. **Fertig:** keine unbegründete positive Aussage aus einer unsicheren entscheidenden Kennzahl.
- [ ] **W01 – Wirtschaftliche Vergleichsalternative definieren.** Weiterbetrieb, notwendiger Kesseltausch oder alternative neue Heizung? Investitionsmehrkosten unterscheiden. **Fertig:** Empfehlung nennt eindeutig das Vergleichsszenario.
- [ ] **W02 – Demo-Entscheidung eindeutig begrenzen.** Bis zur erweiterten Rechnung nur „im vereinfachten Modell“; Faktor 2 und Horizont nicht als Normvorgaben darstellen. **Fertig:** UI und JSON kennzeichnen dieselben Einschränkungen.

## 4. P1 – Berechnungsqualität und technische Robustheit

- [ ] **F08 – Verbrauchsperiode ergänzen.** Datum von/bis und tatsächliche Tage erfassen, Teiljahre und Zählerstände unterscheiden. Öl-Liefermenge nicht automatisch als Jahresverbrauch behandeln; Tankanfangs-/endbestand berücksichtigen.
- [ ] **F09 – Gasumrechnung präzisieren.** Brennwert und Zustandszahl aus Rechnung; 10 nur als sichtbare Näherung. Öl- und Gasfaktor getrennt konfigurieren.
- [ ] **F10 – Witterungsbereinigung planen.** Geeignete Referenz, Zeitraum und hinreichend genaue Ortsinformation wählen; DWD-Faktor für Energieverbrauchsausweise nicht blind mit einer lokalen Auslegungsheizlast gleichsetzen.
- [ ] **F11 – Kesselnutzungsgrad begründen.** 0,88 als Challenge-Default erhalten, reale Anlagen anhand geeigneter Mess-/Planungsdaten beurteilen. Abgasverlustmessung allein ist kein Jahresnutzungsgrad.
- [ ] **F12 – Warmwasser differenzieren.** Messwert, Personenmodell, Solarabdeckung, Speicher-/Zirkulationsverluste und getrennte JAZ klären.
- [ ] **F13 – Temperatur-/JAZ-Szenarien ergänzen.** Unbekannten Vorlauf nicht erraten; Heizkurve, Auslegungstemperatur, Quelle und Gerätemodell erfassen. Tabellenwerte als Challenge-Modus erhalten.
- [ ] **F14 – Heizkörperleistung ergänzen.** Raumlast, Maße, Hersteller/Typ und Vorlauf/Rücklauf/Raumtemperatur einbeziehen. Ein Foto von Typ 22 allein genügt nicht.
- [ ] **F15 – Faktor-2-Prüfung kalibrieren.** Prüfen, ob Intervallüberschneidung und Beleglage besser geeignet sind; Schwelle aus Entwicklungsfällen begründen und vor Eval einfrieren.
- [ ] **W03 – Gesamtkosten erweitern.** Investition, Förderung, Wartung, Messstellen-/Grundpreise, Zinsen, Ersatzinvestitionen, Restwerte und Preisannahmen nach klarer Methodik ergänzen.
- [ ] **W04 – Förderangaben belegen.** Zunächst Nutzerannahmen; für verbindliche Regeln aktuelle zuständige Förderstelle und Stichtag dokumentieren. Kein pauschaler Förderprozentsatz.
- [ ] **T01 – Kennzahlschema verschärfen.** Pro Key Werttyp, Einheit, Zahlenbereich und erlaubte Kategorie prüfen; fehlerhafte Fremdmodule dürfen keine semantisch falschen Werte einspeisen.
- [ ] **T02 – Runner live testen.** Je ein kompatibles API- und MLX-Modell konfigurieren; Bildfähigkeit, JSON-Vertrag, Zeitlimit und Fehlerverhalten prüfen. Kein automatischer Wechsel von lokal zu extern.
- [ ] **T03 – Modellabbruch ermöglichen.** Lokale Inferenz hat derzeit keinen harten Prozess-Timeout. Abbruch, Neustart und Ressourcenfreigabe definieren.
- [ ] **T04 – Extraktion bestätigen.** Nutzer muss erkannte Werte mit Beleg sehen und bestätigen können; Herkunft bei Überschreibung bewahren.
- [ ] **T05 – Bild-/Dokumenttests sammeln.** Unleserliche Bilder, falsche Dokumente, injizierte Anweisungen, unvollständige Rechnungen und mehrdeutige Ventile prüfen.
- [ ] **T06 – Performance messen.** Kaltstart getrennt von warmem Lauf; Gesamtzeit inklusive Nutzerbestätigung und Modellfehlern ausweisen.
- [ ] **T07 – Browser-/Mobilabnahme.** Formular, Datei-Upload, Modulwahl, Fehlermeldungen, JSON-Download und Darstellung auf kleinen Displays testen.

## 5. P2 – spätere Erweiterungen

- [ ] **E01 – PDF-Auswertung.** Begrenztes Rendern/OCR mit Seitenzahl-, Pixel- und Zeitlimits; aktuell werden PDFs nur angenommen.
- [ ] **E02 – Außenaufstellung.** Fotoindikatoren als Prüfhinweise, keine pauschale Standortfreigabe.
- [ ] **E03 – Strukturierte Gebäudedaten.** U-Werte, Flächen, unbeheizte Räume und Anbauten erfassen; B-01 und B-03 als erste Beispiele.
- [ ] **E04 – Zusätzliche Energieträger.** Nur mit definierten Nutzwärme- und Tarifmodellen erweitern.
- [ ] **E05 – Reproduzierbare Auswertung.** Versionierte Fallliste, maschinenlesbarer Bericht und Modell-/Promptversionen speichern.

## 6. Validierung und Freigabe

- [ ] **V01:** Rechenfälle aus [TESTPROTOKOLL.md](TESTPROTOKOLL.md) unabhängig nachrechnen.
- [ ] **V02:** Original-dev-Fälle importieren und alle Abweichungen erklären.
- [ ] **V03:** Anonymisierte, fachlich bestätigte Rechnungs-/Bildfälle beschaffen.
- [ ] **V04:** Regeln, Prompts und Parameter vor Evaluierung einfrieren.
- [ ] **V05:** Eval-Fälle ohne Nachkalibrierung ausführen; Referenzen getrennt auswerten.
- [ ] **V06:** Fachliche Freigabe mit dokumentierten Grenzen durch nuuEnergy/Fachbetrieb einholen.

## 7. Bearbeitung dokumentieren

Für jeden Punkt diese Angaben ergänzen:

```text
ID:
Verantwortlich:
Status: offen / in Arbeit / blockiert / erledigt
Entscheidung und Begründung:
Quelle oder Datenbeleg:
Betroffene Module:
Testfall-IDs:
Ergebnis/Artefakt:
Review durch / Datum:
```

Empfohlene erste Reihenfolge: D01–D03 → F01–F03 → F05–F07 → V01–V02 → W01–W03. PDF und zusätzliche Modellfunktionen erhöhen den fachlichen Nutzen erst, wenn diese Grundlagen stimmen.
