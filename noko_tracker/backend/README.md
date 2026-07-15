# Heim-ERP Backend

FastAPI-Backend fuer ein privates Heim-ERP mit SQLite, SQLAlchemy und Pydantic.

## Start

```powershell
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Die API-Dokumentation ist danach unter http://127.0.0.1:8000/docs erreichbar.

## Bereiche

- `users`: Benutzerverwaltung
- `calendar/events`: Kalendereintraege
- `inventory`: Haushaltslager mit Mindestmengen, Lagerorten, Einlagerungsdatum, Haltbarkeit in Tagen, Preisen und Warnungen
- `foods`: Lebensmittelstammdaten mit Naehrwerten
- `product-groups`: Produktgruppen fuer Lebensmittel
- `product-units`: Einheiten fuer Lebensmittel und Bestandsmengen
- `recipes`: Rezepte und Rezeptzutaten
- `meals/logs`: Mahlzeitenprotokoll
- `nutrition`: Naehrwertberechnungen fuer Foods, Recipes, MealLogs und Tagesuebersichten
- `shopping-list`: Einkaufsliste mit Abhakstatus, Prioritaet und Low-Stock-Generierung
- `dashboard/summary`: kompakte Uebersicht

## Beziehungen

- `Recipe` hat viele `RecipeIngredient`-Eintraege.
- `RecipeIngredient` gehoert genau zu einem `Recipe` und referenziert genau ein `Food`.
- `InventoryItem` haelt Lagerdaten, berechnet das Ablaufdatum aus Einlagerungsdatum und Haltbarkeitstagen und referenziert den zentralen `Food`-Stammdatensatz.
- Beim Loeschen eines Rezepts werden dessen Zutaten per Cascade entfernt.
- Ein `Food`, das in Rezeptzutaten oder Mahlzeiten referenziert wird, ist per Foreign Key geschuetzt.

SQLite wird automatisch als `home_erp.db` im Arbeitsverzeichnis angelegt, aus dem `uvicorn` gestartet wird.

## Kalorientracker

Tageswerte fuer einen User:

```text
GET /nutrition/day?user_id=1&date=2026-05-20
```

Der Endpoint berechnet `totals`, fixe Tagesziele, verbleibende Werte und Prozentwerte fuer `calories`, `protein`, `fat` und `carbs`.

## Inventory

```text
GET /inventory
GET /inventory/{item_id}
POST /inventory
PUT /inventory/{item_id}
DELETE /inventory/{item_id}
POST /inventory/{item_id}/increase
POST /inventory/{item_id}/decrease
GET /inventory/low-stock
GET /inventory/expiring-soon?days=7
GET /inventory/expired
GET /inventory/warnings
```

`decrease` lehnt Abzuege ab, die die Menge unter `0` setzen wuerden.

## Einkaufsliste

```text
GET /shopping-list
POST /shopping-list
PUT /shopping-list/{item_id}
DELETE /shopping-list/{item_id}
POST /shopping-list/{item_id}/check
POST /shopping-list/{item_id}/uncheck
POST /shopping-list/generate-from-low-stock
```

`generate-from-low-stock` erzeugt Eintraege aus InventoryItems mit `quantity <= minimum_quantity` und ueberspringt Artikel, die bereits offen auf der Einkaufsliste stehen.
