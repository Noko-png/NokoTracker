# Kalenderpruefungen

`npm test` prueft die Zeitberechnung und Datumswechsel (Node.js ab 22.18).

## Speichern Im Browser

Der optionale Integrationstest reproduziert das Anlegen von Urlaub ueber
Erstellen und anschliessendes Antippen eines Arbeitstermins. Er prueft echte
HTTP-Schreibzugriffe, den Erhalt der Serie, direkte Datumseingabe, Ganztagstermine,
Fehler beim Speichern und die anschliessende normale Bearbeitung.

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
