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

## Lokaler API-Healthcheck

```text
GET /health
```
