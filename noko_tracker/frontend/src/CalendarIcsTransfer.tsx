import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { exportCalendarIcs, importCalendarIcs } from "./api/client";
import type { CalendarEvent, CalendarGroup, CalendarIcsImportResult } from "./api/client";

export function CalendarIcsTransfer({ groups, sources, onDeleteSource, userId, timezone, onTimezoneChange, start, end, onImported }: {
  groups: CalendarGroup[];
  sources: CalendarEvent[];
  onDeleteSource: (event: CalendarEvent) => void;
  userId: number;
  timezone: string;
  onTimezoneChange: (value: string) => void;
  start: string;
  end: string;
  onImported: () => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [groupId, setGroupId] = useState("");
  const [zoneDraft, setZoneDraft] = useState(timezone);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<CalendarIcsImportResult | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const value = await importCalendarIcs(file, zoneDraft, userId, groupId ? Number(groupId) : null);
      onTimezoneChange(zoneDraft);
      setResult(value);
      setFile(null);
      if (input.current) input.current.value = "";
      await onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "ICS-Datei konnte nicht importiert werden.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  async function download() {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      const blob = await exportCalendarIcs(start, end, timezone);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `nokotracker-kalender-${start.slice(0, 10)}.ics`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Kalender konnte nicht exportiert werden.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  return <details className="calendar-ics-transfer">
    <summary>ICS importieren / exportieren</summary>
    <form className="form-grid" onSubmit={submit}>
      <label><span>ICS-Datei</span><input ref={input} accept=".ics,text/calendar" type="file" disabled={busy} required
        onChange={event => { setFile(event.target.files?.[0] ?? null); setResult(null); setError(""); }} /></label>
      <label><span>Zielgruppe</span><select value={groupId} disabled={busy} onChange={event => setGroupId(event.target.value)}>
        <option value="">Keine Gruppe</option>
        {groups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}
      </select></label>
      <label><span>Kalender-Zeitzone</span><input value={zoneDraft} disabled={busy} required list="calendar-ics-timezones"
        onChange={event => setZoneDraft(event.target.value)} /></label>
      <datalist id="calendar-ics-timezones"><option value="Europe/Berlin" /><option value="UTC" /></datalist>
      <p className="full-width">Termine und Serien bleiben mit ihren ICS-Regeln erhalten. Änderungen werden durch erneuten Import derselben UID übernommen. Unveränderte Termine werden übersprungen. Die Zeitzone gilt für die Anzeige und Termine ohne eigene Zeitzone.</p>
      <button className="button primary" disabled={busy || !file} type="submit">{busy ? "Wird verarbeitet…" : "ICS importieren"}</button>
      <button className="button secondary" disabled={busy} onClick={() => void download()} type="button">Zeitraum als .ics exportieren</button>
      <p className="full-width">Der Export enthält alle Kalendergruppen des angezeigten Zeitraums als Einzeltermine, einschließlich Serienvorkommen. Aufgaben werden nicht exportiert.</p>
      {error && <div className="notice error full-width" role="alert">{error}</div>}
      {result && <div className="calendar-ics-result full-width" role="status">
        {result.imported_count} importiert, {result.updated_count} aktualisiert, {result.skipped_count} unverändert.
        {result.warnings.length > 0 && <ul>{result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
      </div>}
    </form>
    {sources.length > 0 && <details className="calendar-ics-sources">
      <summary>Importierte ICS-Termine verwalten ({sources.length})</summary>
      <ul>{sources.map(source => <li key={source.id}>
        <span>{source.title}{source.ics_is_series ? " (Serie)" : ""}</span>{" "}
        <button className="button secondary" disabled={busy} type="button" onClick={() => onDeleteSource(source)}>
          {source.ics_is_series ? "ICS-Serie löschen" : "ICS-Termin löschen"}
        </button>
      </li>)}</ul>
    </details>}
  </details>;
}
