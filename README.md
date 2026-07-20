# NokoTracker

NokoTracker ist eine private Heim-ERP-App mit React/Vite-Frontend und FastAPI-Backend. Sie verwaltet unter anderem Vorrat, Lebensmittel, Produktgruppen, Rezepte, Mahlzeiten, Kalenderdaten und Einkaufsliste.

## Struktur

- `frontend/`: React, TypeScript und Vite
- `backend/`: FastAPI, SQLAlchemy, Pydantic und SQLite
- `noko_tracker/`: Home-Assistant-Add-on mit kombiniertem Frontend und Backend

## Backend starten

```powershell
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Die API ist danach unter `http://127.0.0.1:8000` erreichbar, die OpenAPI-Dokumentation unter `http://127.0.0.1:8000/docs`.

## Frontend starten

```powershell
cd frontend
npm install
npm run dev
```

Das Frontend laeuft standardmaessig unter `http://127.0.0.1:5173`.

## Lokal alles starten

Unter Windows kannst du im Projektordner auch direkt starten:

```cmd
start-local.cmd
```

Das oeffnet zwei CMD-Fenster:

- Frontend: `http://127.0.0.1:5173`
- Backend/API-Doku: `http://127.0.0.1:8000/docs`

Dass `http://127.0.0.1:8000` nur JSON ausgibt, ist normal. Die Bedienoberflaeche laeuft lokal ueber den Frontend-Devserver auf Port `5173`.

## Konfiguration

Das Frontend nutzt standardmaessig `http://127.0.0.1:8000` als API-Basis. Fuer andere Umgebungen kann `VITE_API_BASE_URL` gesetzt werden.

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
npm run dev
```

SQLite-Datenbanken und lokale Laufzeitdateien werden nicht versioniert.

## Home Assistant Add-on

Die Branch `home-assistant-addon` enthaelt ein installierbares Home-Assistant-Add-on in `noko_tracker/`.

Das Add-on baut das Frontend im Docker-Image, startet das FastAPI-Backend auf Port `8000` und liefert die UI ueber Home-Assistant-Ingress aus. Die SQLite-Datenbank liegt persistent unter `/data/noko_tracker.db`.

## Import und Export

In den Einstellungen kannst du die NokoTracker-Datenbank als SQLite-Datei herunterladen oder eine vorhandene `.db`/`.sqlite`-Datei hochladen. Beim Import wird die bestehende Datenbank vorher automatisch als Backup gesichert.

Der Grocy-Import kann weiterhin einen Serverordner lesen und zusaetzlich direkt im Browser CSV-Dateien oder ein ZIP-Archiv aus deinem PC hochladen.
