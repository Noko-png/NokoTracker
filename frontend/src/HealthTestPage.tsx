import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Footprints, HeartPulse, Moon, RefreshCw } from "lucide-react";
import { getHealthTest, type HealthSensorSelection, type HealthTestResult, type HealthTestSensor } from "./api/client";
import "./health-test.css";

const groups = [
  { kind: "steps", label: "Schritte heute", icon: Footprints },
  { kind: "heart_rate", label: "Puls", icon: HeartPulse },
  { kind: "sleep", label: "Letzter Schlaf", icon: Moon },
] as const;

const stateLabels = {
  available: "Wert verfügbar", unknown: "Noch kein Messwert",
  unavailable: "Sensor nicht verfügbar", invalid: "Kein gültiger Zahlenwert",
  missing: "Sensor-ID nicht gefunden",
};

function timestamp(value: string | null) {
  if (!value || !Number.isFinite(new Date(value).getTime())) return "Unbekannt";
  return new Date(value).toLocaleString("de-DE");
}

function SensorReading({ sensor }: { sensor: HealthTestSensor }) {
  const unit = sensor.unit === "steps" ? "Schritte" : sensor.unit === "min" ? "Minuten" : sensor.unit;
  return <div className="health-reading" data-entity={sensor.entity_id}>
    <strong className="health-reading-name">{sensor.name}</strong>
    {sensor.kind === "resting_heart_rate" && <span className="health-reading-note">Ruhepuls</span>}
    <div className="health-reading-value">
      {sensor.state === "available" && sensor.value !== null
        ? sensor.value.toLocaleString("de-DE", { maximumFractionDigits: 2 }) : "—"}
      {sensor.state === "available" && <span>{unit ?? "Einheit fehlt"}</span>}
    </div>
    <span className="health-reading-note">{stateLabels[sensor.state]}</span>
    <span className="health-reading-note">HA-Aktualisierung: {timestamp(sensor.last_updated)}</span>
    <code>{sensor.entity_id}</code>
    {sensor.selection === "manual" && <span className="health-reading-note">Manuell ausgewählte Quelle</span>}
  </div>;
}

export function HealthTestPage() {
  const [result, setResult] = useState<HealthTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fields, setFields] = useState<HealthSensorSelection>({});
  const [selection, setSelection] = useState<HealthSensorSelection>({});
  const controller = useRef<AbortController | null>(null);

  const load = useCallback(async (chosen: HealthSensorSelection) => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await getHealthTest(chosen, current.signal);
      if (!current.signal.aborted) setResult(response);
    } catch (failure) {
      if (!current.signal.aborted) setError(failure instanceof Error ? failure.message : "Die Abfrage ist fehlgeschlagen.");
    } finally {
      if (!current.signal.aborted) setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load({});
    return () => controller.current?.abort();
  }, [load]);

  return <section className="health-test" aria-label="Test Health dashboard">
    <div className="health-test-intro">
      <div>
        <p className="eyebrow"><Activity size={16} /> Health Connect · Testansicht</p>
        <p>Schritte, Puls und Schlaf aus deiner Home-Assistant-App.</p>
        <p className="health-reading-note">Nur für Administratoren. Die Quellen können von mehreren Handys stammen. Die Abfrage speichert keine Messwerte in NokoTracker und ist keinem ausgewählten Profil zugeordnet.</p>
      </div>
      <button className="button primary" disabled={busy} onClick={() => void load(selection)} type="button">
        <RefreshCw size={16} /> {busy ? "Daten werden abgerufen …" : "Daten abrufen"}
      </button>
    </div>

    <div aria-live="polite" aria-busy={busy}>
      {busy && <p className="health-test-status">Verbindung zu Home Assistant wird geprüft …</p>}
      {error && <div className="notice error" role="alert">{error}</div>}
      {result && <div className={`health-test-status ${result.status === "connected" ? "connected" : ""}`}>
        <strong>{result.message}</strong>
        <span>Letzte Abfrage: {timestamp(result.checked_at)}</span>
      </div>}
    </div>

    {result?.status === "connected" && <>
      <div className="health-test-grid">
        {groups.map(({ kind, label, icon: Icon }) => {
          const sensors = result.sensors.filter(sensor => sensor.kind === kind || (kind === "heart_rate" && sensor.kind === "resting_heart_rate"));
          return <article className="health-test-card" key={kind}>
            <h2><Icon size={22} /> {label}</h2>
            {sensors.length ? sensors.map(sensor => <SensorReading key={`${sensor.kind}:${sensor.entity_id}`} sensor={sensor} />)
              : <p className="health-reading-note">Kein passender Sensor gefunden. Aktiviere ihn in der HA-App oder wähle ihn unten manuell aus.</p>}
          </article>;
        })}
      </div>
      <p className="health-reading-note">Angezeigt werden die zuletzt an Home Assistant übermittelten Werte. Die HA-Aktualisierung ist nicht zwingend der Messzeitpunkt. „Schritte heute“ bezieht sich auf den Tag des Quellwerts; bei ausbleibender Synchronisierung kann er vom Vortag stammen.</p>
    </>}

    <div className="health-test-help">
      <h2>Daten auf dem Handy freigeben</h2>
      <ol>
        <li>In Health Connect prüfen, ob Samsung Health Schritte, Herzfrequenz und Schlaf bereitstellt und Home Assistant diese lesen darf.</li>
        <li>In der HA-App unter <strong>Einstellungen → Companion App → Sensoren verwalten → Health Connect</strong> die gewünschten Sensoren einzeln aktivieren.</li>
        <li>Samsung Health synchronisieren, die HA-App öffnen und anschließend hier <strong>Daten abrufen</strong> wählen.</li>
      </ol>
      <p>Die Freigabe in Health Connect allein aktiviert die Sensoren in Home Assistant noch nicht.</p>
    </div>

    <details className="health-test-help">
      <summary>Umbenannte Sensoren oder mehrere Handys: Quellen auswählen</summary>
      <p>Trage bei Bedarf die Sensor-ID aus Home Assistant ein. Leere Felder verwenden die automatische Suche. Die Auswahl gilt nur für diese geöffnete Testseite.</p>
      <form onSubmit={event => { event.preventDefault(); setSelection({ ...fields }); void load({ ...fields }); }}>
        <div className="health-test-inputs">
          {([
            ["steps_entity", "Schritte: Sensor-ID"],
            ["pulse_entity", "Puls: Sensor-ID"],
            ["sleep_entity", "Schlafdauer: Sensor-ID"],
          ] as const).map(([key, label]) => <label key={key}>
            <span>{label}</span>
            <input value={fields[key] ?? ""} onChange={event => setFields({ ...fields, [key]: event.target.value })}
              placeholder="sensor.mein_handy_health_connect_…" pattern="sensor\.[a-z0-9_]{1,180}" maxLength={187} spellCheck={false} autoComplete="off" />
          </label>)}
        </div>
        <button className="button secondary" disabled={busy} type="submit">Auswahl abrufen</button>
      </form>
    </details>
  </section>;
}
