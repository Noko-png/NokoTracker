const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]"]);

export function resolveApiBaseUrl(value: string | undefined): string {
  if (value === undefined) return "http://127.0.0.1:8000";

  if (!value.startsWith("//") && /^[a-zA-Z0-9_./~-]*$/.test(value)) {
    return value;
  }

  if (/^https?:\/\//i.test(value) && !/[\\?#\s\x00-\x1F\x7F]/.test(value)) {
    const url = new URL(value);
    if (
      !url.username && !url.password &&
      (url.protocol === "https:" || LOOPBACK_HOSTS.has(url.hostname))
    ) {
      return url.href;
    }
  }

  throw new Error("VITE_API_BASE_URL muss relativ sein oder HTTPS verwenden. HTTP ist nur auf Loopback erlaubt.");
}
