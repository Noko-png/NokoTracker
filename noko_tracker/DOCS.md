# NokoTracker Add-on

Dieses Add-on startet ein FastAPI-Backend auf Port `8000` und liefert das gebaute React-Frontend aus demselben Prozess aus.

## Konfiguration

| Option | Beschreibung |
| --- | --- |
| `log_level` | Log-Level fuer den Startprozess. |
| `admin_username` | Exakter Home-Assistant-Anmeldename des NokoTracker-Administrators, nicht der Anzeigename. Ohne Eintrag gibt es keinen Administrator. |

## Einrichtung nach dem Update auf 3.1.9

1. In der Add-on-Konfiguration `admin_username` auf den eigenen HA-Anmeldenamen setzen, speichern und das Add-on neu starten.
2. NokoTracker ueber Home Assistant oeffnen. Der konfigurierte Administrator sieht weiterhin alle bestehenden Profile.
3. In NokoTracker unter Einstellungen das passende Profil bearbeiten und die HA-Benutzer-ID eintragen. Die eigene ID steht in den Einstellungen; noch nicht zugeordnete Nutzer sehen ihre ID auf der Startseite.
4. Fuer weitere HA-Nutzer deren ID im passenden bestehenden oder neu angelegten Profil hinterlegen. Eine HA-ID kann nur einem Profil zugeordnet werden. Ohne Zuordnung sehen normale Nutzer keine Daten.

Gewicht, Training, Mahlzeiten, Mealprep und ToDos sind persoenlich. Bestand, Lebensmittel, Rezepte, Einkaufsliste und Kalendertermine bleiben gemeinsam. Der konfigurierte Administrator verwaltet Profile, Datenbanksicherungen und Grocy-Importe. Kassenzettel koennen weiterhin fuer den gemeinsamen Bestand gebucht werden.

Das Add-on akzeptiert ausschliesslich Verbindungen des HA-Ingress-Supervisors. Direkter Portzugriff ist entfernt. Die HA-Anmeldung ersetzt die bisher wirkungslosen NokoTracker-Passwoerter; vorhandene Passwortwerte werden beim Start entfernt. Das Add-on benoetigt keine zusaetzlichen Supervisor- oder Core-API-Rechte.

## Bestandsbuchungen ab 3.1.10

Beim Aktualisieren werden die neuen Buchungstabellen automatisch angelegt; vorhandene Bestaende bleiben erhalten. Mahlzeit und Bestandsabzug werden gemeinsam gespeichert. Wird eine neu gebuchte Mahlzeit korrigiert oder geloescht, werden die dokumentierten Abbuchungen entsprechend angepasst oder zurueckgenommen. Bei fehlendem Bestand bleibt die bisherige Buchung erhalten.

Einkaeufe und Zubereitungen erhalten jeweils eine eigene Charge. Dadurch bleiben Einheiten und Ablaufdaten vorhandener Ware erhalten. Ein bereits gebuchter Kassenzettel wird bei erneutem Einlesen oder Senden abgewiesen. Wurde ein Bestand zwischen Oeffnen und Speichern eines Formulars geaendert, muss der Eintrag neu geladen und erneut bearbeitet werden.

Alte Abbuchungen vor 3.1.10 besitzen keinen verlaesslichen Chargennachweis. Bereits markierte Altbuchungen lassen deshalb keine automatische Mengenkorrektur oder Rueckbuchung beim Loeschen zu; Notizen und Datum bleiben bearbeitbar. Bereits vorhandene Fehlbestaende muessen anhand des tatsaechlichen Vorrats manuell berichtigt werden. Aeltere Sicherungen sind weiterhin importierbar, enthalten aber keine Nachweise oder Belegkennungen aus der Zeit vor diesem Update.

## Persistenz

Die Datenbank liegt im Add-on-Datenverzeichnis:

```text
/data/noko_tracker.db
```

Die Einstellungen bieten einen Browser-Export und -Import der SQLite-Datenbank. Ein Import ersetzt die aktive Datenbank und legt vorher ein Backup der bisherigen Datei im Datenverzeichnis an.

Sicherungen enthalten keine Passwoerter oder HA-Profilzuordnungen. Beim Wiederherstellen bleiben die lokalen Zuordnungen fuer identische Profilnamen erhalten. Auf einer neuen Installation muessen sie neu vergeben werden. Alte NokoTracker-Sicherungen bleiben importierbar. Unbekannte Tabellen werden mit Hinweis ausgelassen; Trigger, Views und virtuelle Tabellen werden abgewiesen. Die Anwendung erstellt das Datenbankschema selbst und uebernimmt nur die Daten. Wiederherstellungen sperren andere Datenbankzugriffe bis zum atomaren Austausch.

Importgrenzen: Datenbank 64 MB / 200000 Datensaetze; CSV/ZIP zusammen 32 MB Upload, 64 MB entpackt, 16 MB je CSV und maximal 64 Dateien. ZIP-Dateien mit mehr als 100-facher Kompression werden abgewiesen. Serverordner-Importe sind im Add-on auf `/data/imports` beschraenkt. PDF-Kassenzettel: 8 MB, maximal 30 Seiten, 12 Sekunden Verarbeitung in einem getrennten Prozess; unter Linux maximal 256 MB virtueller Arbeitsspeicher und 8 CPU-Sekunden.

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
