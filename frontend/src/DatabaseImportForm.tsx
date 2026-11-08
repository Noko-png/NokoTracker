import { useEffect, useRef, useState, type FormEvent } from "react";
import { Upload } from "lucide-react";
import { previewDatabaseBackup, type DatabaseImportOptions, type DatabaseImportPreview } from "./api/client";

export function DatabaseImportForm({ file, busy, onFileChange, onSubmit }: {
  file: File | null;
  busy: boolean;
  onFileChange: (file: File | null) => void;
  onSubmit: (event: FormEvent, options: DatabaseImportOptions) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<DatabaseImportPreview | null>(null);
  const [previewFile, setPreviewFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<DatabaseImportOptions["mode"]>("selected");
  const [groups, setGroups] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setPreviewFile(null);
    setError("");
    setGroups([]);
    setMode("selected");
    setLoading(Boolean(file));
    if (!file && fileInput.current) fileInput.current.value = "";
    if (file) {
      previewDatabaseBackup(file).then(result => {
        if (cancelled) return;
        setPreview(result);
        setPreviewFile(file);
      }).catch(reason => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Datei konnte nicht geprueft werden.");
      }).finally(() => { if (!cancelled) setLoading(false); });
    }
    return () => { cancelled = true; };
  }, [file]);

  const ready = preview && previewFile === file && !loading && !busy;
  const hasSelection = mode === "full" || groups.length > 0;

  return <form className="settings-import-form compact" onSubmit={event => {
    if (!ready || !hasSelection) { event.preventDefault(); return; }
    onSubmit(event, { mode, groups });
  }}>
    <label className="file-field">
      <span>Datenbanksicherung hochladen</span>
      <input ref={fileInput} accept=".db,.sqlite,.sqlite3" disabled={busy} onChange={event => onFileChange(event.target.files?.[0] ?? null)} type="file" />
      <strong>{file?.name ?? "Keine Datei ausgewaehlt"}</strong>
    </label>
    {loading && <p role="status">Datei wird geprueft …</p>}
    {error && <p role="alert">{error}</p>}
    {preview && previewFile === file && <>
      <label className="field">
        <span>Importmodus</span>
        <select disabled={busy} value={mode} onChange={event => setMode(event.target.value as DatabaseImportOptions["mode"])}>
          <option value="selected">Ausgewaehlte Datenbereiche ersetzen</option>
          <option value="full">Gesamte Datenbank ersetzen</option>
        </select>
      </label>
      {mode === "selected" && <>
        <p className="database-import-hint">Nur angehakte Bereiche werden ersetzt. Benoetigte Lebensmittel, Rezepte und Einheiten werden bei Bedarf ergaenzt; nicht ausgewaehlte Stammdaten bleiben bestehen. Profile werden anhand ihres exakten Namens zugeordnet.</p>
        <fieldset className="database-import-selection" disabled={busy}>
          <legend>Datenbereiche zum Ersetzen</legend>
          {preview.groups.map(group => <label key={group.key}>
            <input type="checkbox" checked={groups.includes(group.key)} onChange={event => setGroups(current => event.target.checked ? [...current, group.key] : current.filter(key => key !== group.key))} />
            <span>{group.label}<small>{group.rows} Datensaetze in der Datei{group.rows === 0 ? " – leert diesen Bereich" : ""}</small></span>
          </label>)}
        </fieldset>
        {groups.includes("meals") && !groups.includes("inventory") && <p className="database-import-hint">Ohne Vorrat koennen importierte Bestandsabbuchungen nicht automatisch rueckgaengig gemacht werden.</p>}
      </>}
      {mode === "full" && <p className="database-import-hint">Alle Daten werden durch die Datei ersetzt. Vorhandene HA-Zuordnungen bleiben fuer gleichnamige Profile erhalten.</p>}
      {preview.warnings.map(warning => <p className="database-import-hint" key={warning}>{warning}</p>)}
    </>}
    <button className="button danger full" disabled={!ready || !hasSelection} type="submit">
      <Upload size={16} />
      {busy ? "Import laeuft …" : mode === "selected" ? "Ausgewaehlte Bereiche ersetzen" : "Gesamte Datenbank ersetzen"}
    </button>
    <p className="database-import-hint">Vor jedem Import wird automatisch eine Sicherung erstellt.</p>
  </form>;
}
