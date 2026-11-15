import { useState } from "react";
import { API_BASE_URL } from "./api/client";
import { readJsonResponse } from "./api/response";
import { confirmDatabaseReset } from "./databaseResetConfirmation";

export function DatabaseReset({ busy, onBusyChange }: { busy: boolean; onBusyChange: (busy: boolean) => void }) {
  const [error, setError] = useState<string | null>(null);

  async function reset() {
    if (busy || !confirmDatabaseReset((message) => window.confirm(message))) return;
    onBusyChange(true);
    setError(null);
    try {
      const base = API_BASE_URL.replace(/\/+$/, "");
      const path = !base || base === "." ? "database/reset" : `${base}/database/reset`;
      await readJsonResponse(await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmation: "ALLE DATEN LOESCHEN" }),
      }));
      window.location.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Datenbank konnte nicht gelöscht werden.");
      onBusyChange(false);
    }
  }

  return <div className="settings-import-form">
    <p>Entfernt alle Daten einschließlich aller Profile. Diese Aktion kann nicht rückgängig gemacht werden. Lade bei Bedarf vorher unter „Import und Export“ eine Sicherung herunter.</p>
    <button className="button danger full" disabled={busy} onClick={() => void reset()} type="button">Datenbank löschen</button>
    {error && <p role="alert">{error}</p>}
  </div>;
}
