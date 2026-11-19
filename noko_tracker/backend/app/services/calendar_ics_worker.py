"""Disposable ICS parser/recurrence worker, isolated from the live database."""
import json
import sys


def main():
    try:
        import resource
    except ImportError:  # Windows uses the parent's wall-clock timeout.
        pass
    else:
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
    from datetime import datetime
    from fastapi import HTTPException
    from .calendar_ics import _expand_records, _parse_calendar

    try:
        raw = sys.stdin.buffer.read(20_000_001)
        if len(raw) > 20_000_000:
            raise ValueError("Zu viele ICS-Daten.")
        data = json.loads(raw)
        if data["operation"] == "parse":
            result = _parse_calendar(data["content"], data["timezone"])
        elif data["operation"] == "expand":
            result = _expand_records(data["events"], datetime.fromisoformat(data["start"]), datetime.fromisoformat(data["end"]), data["timezone"])
        else:
            raise ValueError("Unbekannte ICS-Operation.")
        output = {"result": result}
    except HTTPException as exc:
        output = {"error": str(exc.detail)[:400]}
    except Exception:
        output = {"error": "ICS-Daten sind ungueltig oder zu komplex."}
    sys.stdout.buffer.write(json.dumps(output, default=lambda value: value.isoformat()).encode("utf-8"))


if __name__ == "__main__":
    main()
