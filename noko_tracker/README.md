# NokoTracker

NokoTracker kombiniert das React-Frontend und das FastAPI-Backend in einem Home-Assistant-Add-on.

## Installation

Fuege dieses Repository im Home-Assistant-Add-on-Store als benutzerdefiniertes Repository hinzu:

```text
https://github.com/Noko-png/NokoTracker
```

Installiere danach das Add-on **NokoTracker** und starte es. Die App ist ueber den Eintrag **NokoTracker** in der Home-Assistant-Seitenleiste erreichbar.

## Daten

Die SQLite-Datenbank wird persistent unter `/data/noko_tracker.db` im Add-on gespeichert und ist damit in Home-Assistant-Backups enthalten.
