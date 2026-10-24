# Lokale Vertriebsdemo

Die Erweiterung läuft mit Python-Standardbibliothek und SQLite. Es sind keine zusätzlichen Pakete und kein E-Mail-Konto erforderlich. Die vorhandenen Berechnungsmodule und die bestehenden Frontend-Dateien bleiben unverändert.

## Lokal starten

```text
python -B -m heat_pump_ready --runner disabled --port 8012
```

Auf macOS `python3` statt `python` verwenden. Falls der Port bereits durch die öffentliche Demo belegt ist, zuerst diese beenden oder einen anderen Port wählen.

- Check: `http://localhost:8012/`
- Vertrieb: `http://localhost:8012/sales`
- Benutzername: `default`
- Passwort: `0000`

Der Button „Vertrieb · Login“ erscheint automatisch im Header des Checks. Der Server ergänzt außerdem ein optionales Kunden-E-Mail-Feld und einen Speicherhinweis. Die bestehenden HTML-, CSS- und JavaScript-Dateien werden dafür nicht bearbeitet.

Für die bereits gestartete öffentliche Laptop-Demo unter Windows:

```powershell
.\Start-PublicDemo.ps1 -Restart
```

Der laufende Tunnel-Link bleibt erhalten. Rein lokal funktioniert alles auch ohne Cloudflare. Abmelden beendet die jeweilige Sitzung. Sitzungen laufen nach acht Stunden ab. Benutzername und Passwort lassen sich optional über `SALES_USERNAME` und `SALES_PASSWORD` beim Serverstart setzen.

## Einträge

Jede erfolgreich abgeschickte Berechnung wird ab Aktivierung in `.runtime/sales.sqlite3` gespeichert. Vorherige Berechnungen wurden nicht protokolliert und können deshalb nicht rückwirkend angezeigt werden. Die Liste enthält alle seitdem gespeicherten Checks und bietet Suchfunktion und Detailansichten.

Gespeichert werden validierte Gebäudeangaben, die optionale Kontakt-E-Mail und die bestehenden Ergebnisse. Upload-Dateien werden nicht gespeichert. `.runtime/` ist bereits von Git ausgeschlossen. Die Daten und Sitzungen bleiben bei einem Serverneustart erhalten.

## Ranking

- A: technisch geeignet und nach dem bestehenden Modell wirtschaftlich positiv.
- B: technisch geeignet, wirtschaftliche Beurteilung noch offen.
- C: technische Klärung erforderlich.
- D: widersprüchliche Angaben, unzureichende technische Belege oder negative Wirtschaftlichkeit.

Innerhalb jeder Gruppe werden zuerst höhere verfügbare Jahresersparnis, dann kürzere verfügbare Amortisation und schließlich neuere Eingänge bevorzugt. Fehlende Werte stehen hinter verfügbaren Werten. Die Gruppen sind eine zusätzliche Priorisierung für die Demo und ändern weder Rechenwerte noch technische Entscheidungen.

## E-Mail-Demo

Bei fehlenden Kernangaben erscheint „Daten per E-Mail anfragen“. Der Server formuliert automatisch eine freundliche Nachricht mit den konkreten offenen Angaben und legt sie im lokalen Demo-Postausgang ab. Fehlt die Empfängeradresse, wird zuerst die Detailansicht zur Eingabe geöffnet. Die Liste der offenen Angaben und der Empfänger sind dort vorab sichtbar.

**Es wird keine echte E-Mail versendet.** Es gibt keine SMTP-Verbindung, keinen Mailanbieter und keinen LLM-Aufruf für die Nachricht. Der Menüpunkt „Demo-Postausgang“ zeigt die lokal erstellten Nachrichten. Wiederholtes Absenden desselben Formulars legt die Nachricht nicht doppelt an.

## Umsetzung und Prüfung

- `heat_pump_ready/server.py`: Routen, Login, Cookie-Prüfung, Formularverarbeitung und Speicherung erfolgreicher Checks.
- `heat_pump_ready/sales.py`: SQLite-Speicher, Ranking und serverseitig gerenderte Vertriebsseiten einschließlich Demo-Postausgang.
- `tests/test_sales.py`: HTTP- und Persistenztests für Zugriffsschutz, Ranking, unveränderte Beispielberechnung, HTML-Escaping und Demo-E-Mails.

Anmelde-Cookies sind `HttpOnly` und `SameSite=Strict`, bei Verwendung der konfigurierten öffentlichen HTTPS-Adresse zusätzlich `Secure`. Schreibende Vertriebsformulare prüfen einen Sitzungstoken gegen fremde Formularaufrufe. Datenbank und Uploads werden über keine öffentliche Dateiroute ausgeliefert.
