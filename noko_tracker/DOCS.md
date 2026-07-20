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

## Lokaler API-Healthcheck

```text
GET /health
```
