# Heizlast-Schätzung (Regel `heat-load-m4-demo-v1`)

**Stand: 24. Oktober 2026.** Beschreibt die implementierte Heizlast-Schätzung, ihre Annahmen und deren Quellenstatus. Sie ist eine **Demoregel**: Teile davon sind eigene Ergänzungen, keine Normwerte.

## 1. Problem

Die verbrauchsbasierte Heizlast (`heat_load_consumption`) trifft die Referenzen der Entwicklungsgebäude nicht (B-01 −75 %, B-02 −45 %, B-03 +14 %). Sie misst die im Jahr genutzte Wärme eines Brennstoffs, die Referenz ist eine Auslegungsheizlast. Die Volllaststunden, die zur Referenz passen, streuen zwischen 500 und 2.300 h; eine einzelne Konstante kann das nicht ausgleichen (Stellschraubenanalyse in [open_topics.md](../open_topics.md)).

## 2. Rechenweg

```text
1. Gebäudeklasse (Baujahr, Sanierungsstand)  →  Band in W/m²      [heat_load_area]
2. Heizlast aus Verbrauch (wie bisher)                            [heat_load_consumption]
3. Schätzung heat_load:
   Verbrauch im Band      → Verbrauchswert
   Verbrauch unter Band   → Mitte des Bands + Hinweis (Zusatzwärme, unvollständige Daten)
   Verbrauch über Band    → Verbrauchswert + Hinweis (nicht unterschätzen)
   kein Verbrauch         → Mitte des Bands
```

Der Verbrauch geht weiterhin voll in Kosten, Ersparnis und Amortisation ein. Die Schätzung ändert nur die angezeigte Heizlast.

## 3. Klassenleiter (`calculation/heat_load_classes.py`)

| Klasse | W/m² | Herkunft |
|---|---|---|
| unsaniert, vor 1979 | 120–180 | Challenge |
| Baujahr 1980er–1990er | 80–120 | Challenge |
| saniert oder ab 2002 | 40–60 | Challenge |
| Niedrigenergiehaus | 15–40 | Challenge |

Einstufungsregeln:

| Fall | Regel | Herkunft |
|---|---|---|
| Baujahr in einer Klasse | diese Klasse | Challenge |
| `fully` / `low_energy` | „saniert“ bzw. „Niedrigenergie“ | Challenge |
| Baujahr 1979 | Klasse 1980er–1990er | **eigene Ergänzung** |
| Baujahr 2000 / 2001 | nächstliegendes Jahr: 2000 → 1980er–1990er, 2001 → „ab 2002“ | **eigene Ergänzung** |
| `partially` | eine Klasse besser als die Baujahrsklasse, höchstens „saniert oder ab 2002“ | **eigene Ergänzung** |
| `unknown` | nach Baujahr, mit Hinweis | Annahme |

Eigene Ergänzungen setzen `demonstration=True` und werden in der Oberfläche als Demoannahme markiert.

## 4. Weitere Änderungen

- **Warmwasser ohne Personenzahl:** 0 kWh, als Unsicherheit gekennzeichnet (vorher blockiert). Die verbrauchsbasierte Heizlast fällt dann eher zu hoch aus (0,5 kW je fehlender Person). Weiterhin „fehlend“, wenn unbekannt ist, ob das Warmwasser über die Heizung läuft.
- **Faktor-2-Prüfung:** blockiert nicht mehr, sondern erscheint als Hinweis in den Entscheidungsgründen.
- **Notspanne 40–180 W/m²:** entfällt.

## 5. Ergebnisse (Regressionstest `tests/test_heat_load.py`)

| Fall | Band (kW) | Verbrauch (kW) | Schätzung (kW) | Referenz |
|---|---|---|---|---|
| B-01 | 7,8–11,7 | 2,40 | 9,75 (Mitte) | 9,6 |
| B-02 | 7,2–10,8 | 5,32 | 9,00 (Mitte) | 9,7 |
| B-03 | 16,0–24,0 | 16,60 | 16,60 (Verbrauch) | 14,5 |
| B-04 | 12,8–19,2 | 9,50 | 16,00 (Mitte) | zurückgehalten |
| B-05 | 5,0–7,5 | 10,38 | 10,38 (Verbrauch, über Band) | zurückgehalten |

Auf B-01 bis B-03 liegt die mittlere Abweichung der Schätzung bei 7,8 % (Verbrauchsmethode allein: 44,9 %). **Das ist kein unabhängiger Nachweis:** Die Regel wurde gewählt, nachdem die Referenzen bekannt waren. B-03 liegt knapp außerhalb des Bands (14,5 < 16,0 kW), B-01 hängt an der Einstufung von Baujahr 2001. Den echten Test liefern B-04 und B-05, sobald deren Referenzen vorliegen; die Regel ist vorher einzufrieren.

## 6. Quellenstatus

| Annahme | Quelle | Belastbarkeit |
|---|---|---|
| Verbrauchsbasiertes Schätzverfahren existiert | [BWP-Heizlastrechner im dena-Gebäudeforum](https://www.gebaeudeforum.de/service/toolbox/heizlastrechner/): „Schätzverfahren nach Volllaststunden“, überschlägig, ersetzt DIN EN 12831 nicht | gut für das Verfahren, keine Zahlen |
| Klassen in W/m² | Challenge; stimmen mit BDH/VdZ-Überschlagswerten überein, wie [rechner-portal.de](https://rechner-portal.de/energie/heizung/heizlastrechner) sie wiedergibt (vor 1977: 130 (120–180); 1977–1994: 100 (70–130); 2002–2015: 50 (40–60)) | mittel; Originaldokument BDH/VdZ fehlt |
| 2.000 Volllaststunden | Challenge; Fachartikel nennen 1.800–2.100 h (VDI 2067 Blatt 2: 2.100 h für Einfamilienhäuser, laut Zusammenfassung) | schwach bis mittel; Norm nicht eingesehen, standortabhängig |
| Warmwasser 1.000 kWh/Person | Challenge; Quellen nennen 400–800 kWh | schwach, Challenge-Wert liegt darüber |
| Regel „Verbrauch nur im Band“, Bandmitte, Klassenregeln für 1979/2000/2001/teilsaniert | keine, eigene Ergänzung | als Vorschlag kennzeichnen |

## 7. Grenzen und offene Punkte

- Referenzmethode von nuuEnergy ist unbekannt (Norm-Heizlast oder Richtwerte?). Bis zur Klärung ist die Regel eine Annahme, siehe [open_topics.md](../open_topics.md), Abschnitt 2.
- Verbrauch über dem Band wird bewusst nicht gemittelt, damit die Auslegung nicht unterschätzt wird; ob das zu hoch ausfällt (Pool, Gewerbe), muss fachlich geprüft werden.
- Zusatzwärme (Holzofen) und Solarthermie fließen noch nicht in die Bilanz ein (F02).
- Brennwert/Heizwert-Basis des Nutzungsgrads ist ungeklärt (F01).
- Witterungsbereinigung und standortabhängige Volllaststunden fehlen (F10).
- Die Dokumente [BERECHNUNGEN.md](BERECHNUNGEN.md) (M03, M06, Heizlastkonflikt) und [OFFENE_PUNKTE.md](OFFENE_PUNKTE.md) beschreiben noch den Stand vor dieser Regel.
