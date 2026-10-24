# Öffentliche Laptop-Demo

Im v2-Projektordner in PowerShell starten:

```powershell
.\Start-PublicDemo.ps1
```

Das Skript startet den bestehenden Python-Check auf `127.0.0.1:8012` und einen Cloudflare Quick Tunnel. Es gibt den öffentlichen HTTPS-Link aus. Der Link steht zusätzlich in `.runtime/public-url.txt`. Ein erneuter Start übernimmt eine noch laufende Demo. Nach einem Neustart des Tunnels wird eine neue Adresse vergeben. Nach `git pull` lädt `.\Start-PublicDemo.ps1 -Restart` den Webserver neu und behält den laufenden Tunnel samt URL bei.

Beenden:

```powershell
.\Stop-PublicDemo.ps1
```

Der Laptop muss eingeschaltet und online bleiben. Standby beendet die Erreichbarkeit. Es wird kein Windows-Dienst installiert und keine Router-Portfreigabe eingerichtet. Beide Hintergrundprozesse laufen ohne zusätzliches Fenster.

Die Anwendung bleibt an Loopback gebunden. Nur die beim Start ermittelte öffentliche HTTPS-Origin wird zusätzlich für Berechnung und Chat erlaubt. Unbekannte Hosts und fremde Origins bleiben abgewiesen. Die Berechnungsmodule wurden hierfür nicht verändert.

Die Demo ist für Personen mit dem Link öffentlich erreichbar und enthält die anonymisierten Beispielgebäude des Projekts. Sie läuft ausdrücklich mit deaktiviertem LLM. Der Chat zeigt daher den fehlenden Modellanschluss an; es entstehen durch ihn keine externen Modellaufrufe. Hochgeladene Dateien werden in diesem Modus nicht an einen Modellanbieter gesendet.

Programm, Prozessinformationen und Logs liegen ausschließlich im bereits ignorierten Ordner `.runtime/`. Das Stoppskript beendet nur die gespeicherten Prozesse, wenn Prozess-ID, Startzeit und Programmpfad noch passen. Die bestehende lokale Vorschau auf Port 8011 ist davon unabhängig.

Cloudflare-Informationen: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/

Der öffentliche Demo-Link ist temporär. Für dauerhaften Betrieb ist ein eigener Hostingbetrieb erforderlich.
