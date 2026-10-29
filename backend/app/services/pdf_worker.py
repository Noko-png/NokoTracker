"""Bounded PDF extraction in a disposable process, never in the API worker."""
import io
import sys


def main():
    try:
        import resource
    except ImportError:  # Local Windows development; the wall timeout still applies.
        pass
    else:
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    from pypdf import PdfReader

    data = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("PDF zu gross")
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted or len(reader.pages) > 30:
        raise ValueError("PDF verschluesselt oder zu viele Seiten")
    parts = []
    total = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        total += len(text)
        if total > 1_000_000:
            raise ValueError("Zu viel PDF-Text")
        parts.append(text)
    sys.stdout.buffer.write("\n".join(parts).encode("utf-8"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(1)
