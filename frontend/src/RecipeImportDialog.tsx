import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Upload, X } from "lucide-react";
import { importRecipes, previewRecipeImport, type RecipeImportPreview, type RecipeImportResult } from "./api/client";

export function RecipeImportDialog({ onClose, onImported }: {
  onClose: () => void;
  onImported: () => Promise<void>;
}) {
  const headingId = useId();
  const dialog = useRef<HTMLElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const busyRef = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [previewFile, setPreviewFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<RecipeImportPreview | null>(null);
  const [selection, setSelection] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RecipeImportResult | null>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!busyRef.current) onClose();
      } else if (event.key === "Tab") {
        const elements = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), [tabindex="0"]') ?? []);
        const first = elements[0];
        const last = elements[elements.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) {
          event.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previous?.isConnected) previous.focus();
    };
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setPreviewFile(null);
    setSelection([]);
    setError("");
    setLoading(Boolean(file));
    if (!file && fileInput.current) fileInput.current.value = "";
    if (file) {
      previewRecipeImport(file).then(value => {
        if (cancelled) return;
        setPreview(value);
        setPreviewFile(file);
        if (value.recipes.length === 1) setSelection([value.recipes[0].id]);
      }).catch(reason => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Datei konnte nicht geprueft werden.");
      }).finally(() => { if (!cancelled) setLoading(false); });
    }
    return () => { cancelled = true; };
  }, [file]);

  const ready = file && preview && previewFile === file && !loading && !busy && selection.length > 0;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      const imported = await importRecipes(file, selection);
      setFile(null);
      setResult(imported);
      await onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Rezepte konnten nicht importiert werden.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop recipe-import-backdrop" onClick={event => {
      if (event.target === event.currentTarget && !busyRef.current) onClose();
    }}>
      <section className="modal-panel recipe-import-dialog" role="dialog" aria-modal="true" aria-labelledby={headingId} tabIndex={-1} ref={dialog}>
        <div className="panel-header">
          <h2 id={headingId}>Rezepte importieren</h2>
          <button className="icon-button" aria-label="Rezeptimport schliessen" disabled={busy} onClick={onClose} type="button"><X size={20} /></button>
        </div>
        <p className="database-import-hint">Rezepte aus einer Rezeptdatei oder Datenbanksicherung hinzufuegen. Bestehende Rezepte bleiben erhalten. Fehlende Zutaten werden ergaenzt; vorhandene Lebensmittel werden anhand von Name und Marke zugeordnet.</p>
        <form className="settings-import-form" onSubmit={submit}>
          <label className="file-field">
            <span>Rezeptdatei oder Datenbanksicherung</span>
            <input ref={fileInput} accept=".db,.sqlite,.sqlite3" type="file" disabled={busy} onChange={event => {
              setResult(null);
              setFile(event.target.files?.[0] ?? null);
            }} />
            <strong>{file?.name ?? "Keine Datei ausgewaehlt"}</strong>
          </label>
          {loading && <p role="status">Datei wird geprueft …</p>}
          {preview && previewFile === file && <fieldset className="database-import-selection" disabled={busy}>
            <legend>Rezepte auswaehlen</legend>
            {preview.recipes.length === 0 && <p>Diese Datei enthaelt keine Rezepte.</p>}
            {preview.recipes.map(recipe => <label key={recipe.id}>
              <input type="checkbox" checked={selection.includes(recipe.id)} onChange={event => {
                const checked = event.target.checked;
                setSelection(current => checked ? [...current, recipe.id] : current.filter(id => id !== recipe.id));
              }} />
              <span>{recipe.name}</span>
            </label>)}
          </fieldset>}
          {preview?.warnings.map(warning => <p className="database-import-hint" key={warning}>{warning}</p>)}
          {error && <p className="recipe-transfer-error" role="alert">{error}</p>}
          {result && <div className="database-transfer-result" role="status">
            <strong>{result.imported_count} Rezept(e) hinzugefuegt.</strong>
            {result.warnings.map(warning => <span key={warning}>{warning}</span>)}
          </div>}
          <button className="button primary" type="submit" disabled={!ready}>
            <Upload size={16} /> {busy ? "Import laeuft …" : "Ausgewaehlte Rezepte hinzufuegen"}
          </button>
          <p className="database-import-hint">Vor dem Import wird automatisch eine Sicherung erstellt.</p>
        </form>
      </section>
    </div>
  );
}
