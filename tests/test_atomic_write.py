"""Tests for the shared atomic JSON writer (data/atomic_write.py).

Used by the track-model exporters (station map / accepted model) and mirrors the
guarantees already proven for the gt7_updater writer: valid output, a .bak
snapshot on overwrite, no leftover temp, and — critically — a failed swap leaves
the original intact rather than a truncated file the UI would read as valid.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from data.atomic_write import atomic_write_json


def test_writes_valid_json_and_returns_path(tmp_path):
    p = tmp_path / "accepted_model.json"
    obj = {"schema": "v1", "corners": [1, 2, 3]}
    ret = atomic_write_json(p, obj)
    assert ret == p
    assert json.loads(p.read_text(encoding="utf-8")) == obj


def test_overwrite_snapshots_bak(tmp_path):
    p = tmp_path / "station_map.json"
    atomic_write_json(p, {"v": 1})
    atomic_write_json(p, {"v": 2})
    assert json.loads(p.read_text(encoding="utf-8")) == {"v": 2}
    assert json.loads((tmp_path / "station_map.json.bak").read_text(encoding="utf-8")) == {"v": 1}


def test_no_leftover_tmp(tmp_path):
    atomic_write_json(tmp_path / "m.json", {"a": 1})
    assert list(tmp_path.glob("*.tmp")) == []


def test_failed_replace_preserves_original(tmp_path, monkeypatch):
    p = tmp_path / "accepted_model.json"
    atomic_write_json(p, {"good": 1})
    original = p.read_text(encoding="utf-8")

    monkeypatch.setattr(os, "replace",
                        lambda *_a, **_k: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        atomic_write_json(p, {"good": 2})

    assert p.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("*.tmp")) == []


def test_ensure_ascii_default_preserves_prior_exporter_output(tmp_path):
    # The track exporters historically used json.dump default (ensure_ascii=True).
    p = tmp_path / "n.json"
    atomic_write_json(p, {"name": "Nürburgring"})
    assert "\\u00fc" in p.read_text(encoding="utf-8")
