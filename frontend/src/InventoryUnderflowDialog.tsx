import { useEffect, useId, useRef, useState } from "react";
import type { InventoryItem } from "./api/client";

export function InventoryUnderflowDialog({ item, error, onCancel, onConfirm }: {
  item: Pick<InventoryItem, "name" | "storage_location">;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => Promise<boolean>;
}) {
  const headingId = useId();
  const reasonId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, []);

  async function confirmRemoval() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      if (await onConfirm()) onCancel();
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <dialog
      aria-describedby={reasonId}
      aria-labelledby={headingId}
      aria-modal="true"
      className="modal-panel inventory-underflow-dialog"
      onCancel={(event) => {
        event.preventDefault();
        if (!inFlight.current) onCancel();
      }}
      ref={dialogRef}
      role="alertdialog"
    >
      <h2 id={headingId}>Bestand löschen?</h2>
      <p id={reasonId}>
        Die Menge von <strong>{item.name}</strong>{item.storage_location && ` (${item.storage_location})`} würde unter 0 fallen.
      </p>
      {error && <p className="notice error" role="alert">{error}</p>}
      <div className="form-actions">
        <button className="button secondary" disabled={busy} onClick={onCancel} type="button">
          Abbrechen
        </button>
        <button className="button danger" disabled={busy} onClick={confirmRemoval} type="button">
          {busy ? "Wird gelöscht …" : "Bestand löschen"}
        </button>
      </div>
    </dialog>
  );
}
