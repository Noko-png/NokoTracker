# NokoTracker Add-on

Dieses Add-on startet ein FastAPI-Backend auf Port `8000` und liefert das gebaute React-Frontend aus demselben Prozess aus.

## Konfiguration

| Option | Beschreibung |
| --- | --- |
| `log_level` | Log-Level fuer den Startprozess. |

## Persistenz

Die Datenbank liegt im Add-on-Datenverzeichnis:

```text
/data/noko_tracker.db
```

Die Einstellungen bieten einen Browser-Export und -Import der SQLite-Datenbank. Ein Import ersetzt die aktive Datenbank und legt vorher ein Backup der bisherigen Datei im Datenverzeichnis an.

Grocy-CSV-Dateien koennen direkt im Browser als einzelne CSV-Dateien oder ZIP-Archiv hochgeladen werden.

## Updates

Dieses Add-on wird nur ueber die `main`-Branch des Repositorys gepflegt:

```text
https://github.com/Noko-png/NokoTracker
```

Wenn eine neue Version veroeffentlicht wurde, in Home Assistant den Add-on-Store oeffnen und oben rechts **Nach Updates suchen** ausfuehren. Danach kann das Add-on normal ueber **Update** aktualisiert werden. Das Repository muss nicht entfernt und neu hinzugefuegt werden.

Falls Home Assistant noch eine alte Repository-URL mit `/tree/home-assistant-addon` oder `/tree/main` gespeichert hat, diese einmal entfernen und die direkte Repository-URL oben eintragen.

## Lokaler API-Healthcheck

```text
GET /health
```
