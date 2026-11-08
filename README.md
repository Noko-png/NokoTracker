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

Die `main`-Branch enthaelt das lokale Projekt und das installierbare Home-Assistant-Add-on in `noko_tracker/`. Fuege in Home Assistant immer nur die Repository-URL hinzu, nicht eine `/tree/...`-Branch-URL:

```text
https://github.com/Noko-png/NokoTracker
```

Das Add-on baut das Frontend im Docker-Image, startet das FastAPI-Backend auf Port `8000` und liefert die UI ueber Home-Assistant-Ingress aus. Die SQLite-Datenbank liegt persistent unter `/data/noko_tracker.db`.

### Updates

Neue Versionen laufen ausschliesslich ueber `main`. Wenn in GitHub eine neue Version gepusht wurde, in Home Assistant den Add-on-Store oeffnen und oben rechts **Nach Updates suchen** ausfuehren. Danach sollte beim Add-on der normale **Update**-Button erscheinen; das Repository muss nicht entfernt und neu hinzugefuegt werden.

Falls in Home Assistant noch eine alte URL mit `/tree/home-assistant-addon` oder `/tree/main` hinterlegt ist, diese einmal entfernen und nur die direkte Repository-URL `https://github.com/Noko-png/NokoTracker` hinzufuegen.

## EAN-Codes je Produkt

Mit **Stammdaten > Lebensmittel > Aus EAN erstellen** wird ein Produkt anhand eines eingegebenen oder gescannten EAN-Codes gesucht. Wie im Kalorientracker werden die verfuegbaren Produktdaten aus Open Food Facts uebernommen und direkt gespeichert. Bekannte Codes oeffnen das vorhandene Lebensmittel. Angaben anschliessend pruefen und bei Bedarf ergaenzen; Bestand oder Mahlzeiten entstehen dabei nicht. Bei unbekannten Codes ist die manuelle Anlage moeglich.

In den Produktstammdaten koennen unter **EAN-Codes (optional)** mehrere Codes hinzugefuegt oder entfernt werden. Beim Bearbeiten ordnet der Scanner weitere EANs dem Produkt zu. Anschliessend speichern. Alle Codes verwenden dieselben Naehrwerte, Einheiten und denselben Bestand; Tracker, Rezepte und Einkaufsliste bleiben mit demselben Produkt verbunden. Codes fuer Produkte mit unterschiedlichen Naehrwerten oder Mengeneinheiten sollten getrennten Produkten zugeordnet werden.

Bestehende Einzelcodes bleiben erhalten. Jeder Code darf nur einem Produkt gehoeren. Export und Import sichern die komplette EAN-Liste; auch alte Sicherungen mit einem Einzelcode und mehrere EANs aus Grocy werden unterstuetzt.

## Naehrwerte in den Lebensmittel-Stammdaten

Ballaststoffe und Zucker werden in Gramm je 100 g gespeichert, Koffein optional in Milligramm je 100 g. Ein leeres Koffeinfeld bedeutet "nicht angegeben"; eine eingetragene 0 bleibt als bekannter Nullwert erhalten. Beim Anlegen per EAN werden verfuegbare Angaben ebenfalls uebernommen.

Die neuen Werte sind in Datenbanksicherungen enthalten. Bestehende Installationen werden beim Start ergaenzt; aeltere Sicherungen bleiben importierbar und erhalten fuer Ballaststoffe/Zucker den Standardwert 0 sowie ein leeres Koffeinfeld.

## Test Health dashboard

Ab 3.1.16 koennen Administratoren unter **Test Health dashboard** die Health-Connect-Sensoren der Home-Assistant-Companion-App testweise abrufen. Auf dem Handy sowohl die Leserechte in Health Connect als auch die einzelnen Sensoren unter **Einstellungen > Companion App > Sensoren verwalten > Health Connect** aktivieren. Danach die App synchronisieren und das Dashboard oeffnen. Schritte, Puls/Ruhepuls und Schlafdauer werden mit Quelle, Einheit und HA-Aktualisierungszeit angezeigt. Umbenannte Sensoren koennen per Sensor-ID ausgewaehlt werden.

Die Testansicht speichert keine Messwerte, ordnet sie keinem Profil zu und ist nur fuer Administratoren erreichbar. Der Abruf benoetigt die HA-Add-on-Installation; ein lokal gestarteter NokoTracker meldet den fehlenden HA-Anschluss. Hinweise zu den neuen HA-API-Rechten stehen in der [Add-on-Dokumentation](noko_tracker/DOCS.md).

## Import und Export

Administratoren koennen unter **Einstellungen > Import und Export** die Datenbank als SQLite-Datei herunterladen oder eine `.db`-, `.sqlite`- oder `.sqlite3`-Datei hochladen. Nach der Dateipruefung stehen zwei Importmodi zur Wahl:

- **Ausgewaehlte Datenbereiche ersetzen:** Gewicht, Training, Kalender/ToDos, Rezepte, Lebensmittel/Stammdaten, Vorrat/Belegnachweise, Mahlzeiten/Mealprep und Einkaufsliste einzeln ankreuzen. Beispielsweise ersetzt nur **Gewichtsdaten** saemtliche Gewichtseintraege; die anderen Bereiche bleiben erhalten. Ein ausgewaehlter leerer Bereich wird geleert.
- **Gesamte Datenbank ersetzen:** Vollstaendige Wiederherstellung wie bisher.

Teilimporte ordnen Profile ueber den exakten Profilnamen zu, niemals ueber zufaellig gleiche IDs. Fehlende Profile vorher anlegen; Einstellungen und HA-Zuordnungen bleiben lokal. Benoetigte Haushaltsdaten werden bei Bedarf ergaenzt. Vorhandene Lebensmittel werden anhand von Name und Marke, benoetigte Rezepte anhand eindeutiger Namen zugeordnet und dabei nicht ueberschrieben. Mehrdeutige Zuordnungen und EAN-Konflikte brechen den Import ab.

Kann ein Bereich wegen Verknuepfungen zu anderen Daten nicht allein ersetzt werden, bricht der Import ohne Aenderung ab; die verbundenen Bereiche muessen gemeinsam ausgewaehlt werden. Vorratsabbuchungen lassen sich nur zusammen mit dem Vorrat vollstaendig wiederherstellen. Beim Mahlzeitenimport ohne Vorrat bleiben Abbuchungen als Altbuchungen ohne automatische Rueckbuchung erhalten. Vor jedem Import wird die aktuelle Datenbank automatisch gesichert; die Uebernahme erfolgt erst nach erfolgreicher Pruefung.

Der Grocy-Import kann weiterhin einen Serverordner lesen und zusaetzlich direkt im Browser CSV-Dateien oder ein ZIP-Archiv aus deinem PC hochladen.

## Rezepte importieren, exportieren und duplizieren

Die Rezeptfunktionen sind ab 3.1.18 direkt unter **Gerichte** erreichbar und vom allgemeinen Datenbankimport getrennt. **Rezepte importieren** oeffnet einen eigenen Dialog: Eine Rezeptdatei oder vollstaendige Datenbanksicherung laden, gewuenschte Rezepte auswaehlen und hinzufuegen. Bestehende, auch gleichnamige Rezepte bleiben erhalten. Benoetigte Zutaten werden ergaenzt oder anhand von Name und Marke zugeordnet. Rezeptdateien koennen nicht im allgemeinen Datenbankdialog importiert werden.

Im **Drei-Punkte-Menue** neben jedem Rezept stehen **Duplizieren** und fuer Administratoren **Exportieren** zur Verfuegung. Der Export enthaelt das einzelne Rezept mit Zutaten, Einheiten, Umrechnungen, EANs, Naehrwerten und Bild; persoenliche Daten und Vorrat werden nicht exportiert.

**Duplizieren** legt sofort ein eigenes Rezept mit dem Zusatz **(Kopie)** an und oeffnet es im Bearbeitungsmodus. Name, Anleitung, Bild, Tags, Portionen, Zeiten und Zutatenmengen werden uebernommen. Die Zutaten verweisen weiterhin auf vorhandene Lebensmittel; Zutatenzeilen und das Lebensmittel fuer zubereitete Portionen gehoeren der Kopie. So kann die Kopie beispielsweise in **v2** umbenannt und angepasst werden, waehrend das Original erhalten bleibt. Auch beim Abbrechen der Bearbeitung bleibt die bereits angelegte Kopie bestehen.
