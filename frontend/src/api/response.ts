export async function readJsonResponse<T>(response: Response): Promise<T> {
  if (response.ok && response.status === 204) return undefined as T;

  const contentType = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase() ?? "";
  const status = `${response.status} ${response.statusText}`.trim();
  if (contentType !== "application/json" && !contentType.endsWith("+json")) {
    if (contentType === "text/html") {
      throw new Error(`Die API hat HTML statt JSON geliefert (HTTP ${response.status}). Bitte das Add-on aktualisieren und ueber Home Assistant erneut oeffnen.`);
    }
    throw new Error(`Unerwartete API-Antwort: ${status}. Bitte das Add-on erneut oeffnen.`);
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`Die API-Antwort enthaelt kein gueltiges JSON (HTTP ${response.status}). Bitte das Add-on erneut oeffnen.`);
  }
  if (!response.ok) {
    const detail = payload !== null && typeof payload === "object" && "detail" in payload ? payload.detail : null;
    throw new Error(typeof detail === "string" ? detail : status);
  }
  return payload as T;
}
