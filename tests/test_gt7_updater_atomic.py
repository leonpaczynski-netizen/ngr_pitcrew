"""Tests for the atomic JSON writer in data/gt7_updater.py.

The web-data updater runs on a background thread and rewrites shared data files
(car_specs.json / bop_data.json / …) that the running UI reads. Writes must be
atomic so an interrupted flush can never leave a truncated, unparseable file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from data.gt7_updater import _atomic_write_json


def test_writes_valid_json(tmp_path):
    p = tmp_path / "car_specs.json"
    obj = {"cars": {"Porsche": {"num_gears": 6}}, "n": 1}
    _atomic_write_json(p, obj)
    assert json.loads(p.read_text(encoding="utf-8")) == obj


def test_overwrite_keeps_bak_snapshot(tmp_path):
    p = tmp_path / "bop_data.json"
    _atomic_write_json(p, {"v": 1})
    _atomic_write_json(p, {"v": 2})
    assert json.loads(p.read_text(encoding="utf-8")) == {"v": 2}
    bak = p.with_name(p.name + ".bak")
    assert bak.exists()
    assert json.loads(bak.read_text(encoding="utf-8")) == {"v": 1}


def test_no_leftover_tmp(tmp_path):
    p = tmp_path / "gt7_extra.json"
    _atomic_write_json(p, {"a": [1, 2, 3]})
    assert not (tmp_path / (p.name + ".tmp")).exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_creates_parent_dirs(tmp_path):
    p = tmp_path / "nested" / "dir" / "car_id_map.json"
    _atomic_write_json(p, {"ok": True})
    assert p.exists()


def test_failed_replace_preserves_original_and_cleans_tmp(tmp_path, monkeypatch):
    """If the atomic swap fails mid-write, the prior file is intact (via .bak) and
    no partial .tmp is left behind — the corruption the change prevents."""
    p = tmp_path / "car_specs.json"
    _atomic_write_json(p, {"good": 1})
    original = p.read_text(encoding="utf-8")

    def _boom(src, dst):
        raise OSError("simulated crash during os.replace")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        _atomic_write_json(p, {"good": 2})

    # Original file untouched (never moved out from under readers).
    assert p.read_text(encoding="utf-8") == original
    # A recoverable snapshot exists and no partial temp remains.
    assert p.with_name(p.name + ".bak").exists()
    assert list(tmp_path.glob("*.tmp")) == []
