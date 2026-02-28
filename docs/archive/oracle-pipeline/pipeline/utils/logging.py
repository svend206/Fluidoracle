"""
Structured logging — writes JSON lines to a run log file and pretty-prints to console.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class RunLogger:
    def __init__(self, vertical: str, phase: int, log_dir: Optional[Path] = None):
        self.vertical = vertical
        self.phase = phase

        if log_dir is None:
            base = Path(__file__).parent.parent.parent
            log_dir = base / "verticals" / vertical / f"phase{phase}"
        log_dir.mkdir(parents=True, exist_ok=True)

        self.log_path = log_dir / "run.log"
        self._fh = self.log_path.open("a")

    def _write(self, entry: dict) -> None:
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        entry["vertical"] = self.vertical
        entry["phase"] = self.phase
        self._fh.write(json.dumps(entry) + "\n")
        self._fh.flush()

    def info(self, action: str, **kwargs) -> None:
        entry = {"level": "info", "action": action, **kwargs}
        self._write(entry)
        print(f"[{self.vertical}/phase{self.phase}] {action}" +
              (f" — {kwargs}" if kwargs else ""), file=sys.stderr)

    def warn(self, action: str, **kwargs) -> None:
        entry = {"level": "warn", "action": action, **kwargs}
        self._write(entry)
        print(f"[WARN {self.vertical}/phase{self.phase}] {action}" +
              (f" — {kwargs}" if kwargs else ""), file=sys.stderr)

    def error(self, action: str, **kwargs) -> None:
        entry = {"level": "error", "action": action, **kwargs}
        self._write(entry)
        print(f"[ERROR {self.vertical}/phase{self.phase}] {action}" +
              (f" — {kwargs}" if kwargs else ""), file=sys.stderr)

    def fetch(self, url: str, method: str, status: Optional[int],
              items: int = 0, duration_ms: int = 0, error: Optional[str] = None) -> None:
        self._write({
            "action": "fetch",
            "url": url,
            "method": method,
            "http_status": status,
            "items_extracted": items,
            "duration_ms": duration_ms,
            "error": error,
        })

    def close(self) -> None:
        self._fh.close()
