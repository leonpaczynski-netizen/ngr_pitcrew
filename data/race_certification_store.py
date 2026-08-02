"""Live Activation 3 — additive local store + export for race-day certification reports.

Certification evidence is a REPORT, not a schema change: this store persists reports as JSON files
in a dedicated folder beside the app config (never in the SQLite DB, never touching user runtime
data), and exports a human-readable Markdown and a machine-readable JSON on demand. Atomic writes;
no migration. Qt-free; the filesystem is the only I/O.
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional

from strategy.race_certification import RaceCertificationReport, report_from_payload


def _slug(v) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(v or "").strip()).strip("-")
    return s or "report"


def _atomic_write(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


class RaceCertificationStore:
    """Reads/writes race certification reports under ``<base_dir>/race_certifications``."""

    def __init__(self, base_dir: str):
        self._dir = os.path.join(str(base_dir or "."), "race_certifications")

    @property
    def directory(self) -> str:
        return self._dir

    def _ensure(self) -> None:
        os.makedirs(self._dir, exist_ok=True)

    def _json_path(self, report_id: str) -> str:
        return os.path.join(self._dir, f"{_slug(report_id)}.json")

    def _md_path(self, report_id: str) -> str:
        return os.path.join(self._dir, f"{_slug(report_id)}.md")

    def save(self, report_id: str, report: RaceCertificationReport) -> str:
        """Persist a report as JSON (the canonical record) + Markdown (the readable export). Returns
        the JSON path. Best-effort; raises only on a genuine filesystem error the caller should see."""
        self._ensure()
        jpath = self._json_path(report_id)
        _atomic_write(jpath, report.as_json())
        _atomic_write(self._md_path(report_id), report.as_markdown())
        return jpath

    def export_json(self, path: str, report: RaceCertificationReport) -> str:
        _atomic_write(path, report.as_json())
        return path

    def export_markdown(self, path: str, report: RaceCertificationReport) -> str:
        _atomic_write(path, report.as_markdown())
        return path

    def load(self, report_id: str) -> Optional[RaceCertificationReport]:
        """Reload a saved report (reconstructed from its JSON payload), or None if absent/corrupt."""
        jpath = self._json_path(report_id)
        try:
            with open(jpath, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            return report_from_payload(payload)
        except Exception:
            return None

    def list_reports(self) -> List[str]:
        """The report ids present in the store (sorted). Never raises."""
        try:
            return sorted(fn[:-5] for fn in os.listdir(self._dir) if fn.endswith(".json"))
        except Exception:
            return []
