# Frontend-Pruefungen

`npm test` prueft die Zeitberechnung, Datumswechsel und Wiederholungen
(Node.js ab 22.18), einschliesslich Wochenabstaenden, Monatsenden,
Schaltjahren, Serienende und Uebereinstimmung von Vorschau und Kalender.

## Speichern Im Browser

Der optionale Integrationstest reproduziert das Anlegen von Urlaub ueber
Erstellen und anschliessendes Antippen eines Arbeitstermins. Er prueft echte
HTTP-Schreibzugriffe, den Erhalt der Serie, direkte Datumseingabe, Ganztagstermine,
Fehler beim Speichern und die anschliessende normale Bearbeitung.
Zusaetzlich werden die Wiederholungsvorschau, ungueltige Abstaende und
Datumsbereiche, das Speichern und erneute Oeffnen sowie das Abschalten
einer Serie auf Handy- und Desktopbreite geprueft.

Die Testdatenbank liegt ausschliesslich im Arbeitsspeicher. Der Test setzt sie
vor jedem Fall zurueck. Die Fixture darf nur als separater Testserver laufen.

1. Aus dem Backend-Verzeichnis die Fixture starten:

   ```powershell
   python -m uvicorn calendar_ui_fixture:app --app-dir tests --host 127.0.0.1 --port 8015
   ```

2. Aus dem Frontend-Verzeichnis Vite auf einem freien Testport starten.
   Die API-Basis muss der Standard `http://127.0.0.1:8000` sein; der Browser-Test
   leitet diese Anfragen zur In-Memory-Fixture um.

   ```powershell
   npm run dev -- --port 5175 --strictPort
   ```

3. Eine eigene Chrome-Instanz im Hintergrund mit separatem Profil starten:

   ```powershell
   Start-Process 'C:\Program Files\Google\Chrome\Application\chrome.exe' -WindowStyle Hidden -ArgumentList '--headless=new','--remote-debugging-port=9225',"--user-data-dir=$env:TEMP/noko-calendar-ui-test",'about:blank'
   ```

4. Nach dem Start der Server aus dem Frontend-Verzeichnis ausfuehren:

   ```powershell
   npm run test:calendar-ui
   ```

Abweichende lokale Ports lassen sich mit `CALENDAR_TEST_API_URL`,
`CALENDAR_TEST_FRONTEND_URL` und `CALENDAR_TEST_CDP_URL` setzen.
`CALENDAR_TEST_SCREENSHOTS` kann auf ein vorhandenes Ausgabeverzeichnis zeigen.
Die Testserver und die separate Chrome-Instanz anschliessend beenden.

## Lebensmittel und Bestand bearbeiten

`npm run test:food-ui` verwendet dieselben drei Testserver wie oben. Der Test
prueft auf Handy- und Desktopbreite die Bearbeitung von Lebensmitteln mit
Umrechnungen und Bestandspositionen: Datum und Haltbarkeit, null Tage,
erneutes Oeffnen, Speicherkonflikte und Wiederholen nach einem Fehler.
Die gespeicherten Werte und das berechnete Ablaufdatum werden ueber die API
der isolierten Datenbank kontrolliert.

Abweichende Ports lassen sich mit `FOOD_TEST_API_URL`,
`FOOD_TEST_FRONTEND_URL` und `FOOD_TEST_CDP_URL` setzen.
