"""Config Safety Guardrails sprint — config path resolution, safe IO, guardrail.

Pure-Python tests (no PyQt6) for ``config_paths`` plus source-scans proving the
app wiring uses it. The headless MainWindow smoke test lives in
``tests/test_config_safety_smoke.py``.

Every test here runs under pytest, so ``is_test_environment()`` is True and the
real-config guardrail is active — these tests exercise it without ever writing
the real ``config.json`` (the session-autouse ``_guard_real_config`` fixture in
conftest.py also proves that globally).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import config_paths as cp

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #
class TestResolveConfigPath:
    def test_default_is_config_json(self, monkeypatch):
        monkeypatch.delenv(cp.ENV_CONFIG_PATH, raising=False)
        assert cp.resolve_config_path() == cp.DEFAULT_CONFIG_FILENAME

    def test_env_overrides_default(self, monkeypatch):
        monkeypatch.setenv(cp.ENV_CONFIG_PATH, "/tmp/ngr_env_cfg.json")
        assert cp.resolve_config_path() == "/tmp/ngr_env_cfg.json"

    def test_explicit_beats_env(self, monkeypatch):
        monkeypatch.setenv(cp.ENV_CONFIG_PATH, "/tmp/ngr_env_cfg.json")
        assert cp.resolve_config_path("/tmp/explicit.json") == "/tmp/explicit.json"


# --------------------------------------------------------------------------- #
# Environment / path predicates
# --------------------------------------------------------------------------- #
class TestPredicates:
    def test_is_test_environment_true_under_pytest(self):
        assert cp.is_test_environment() is True

    def test_is_real_config_path(self):
        assert cp.is_real_config_path("config.json") is True
        assert cp.is_real_config_path(str(cp.REAL_CONFIG_PATH)) is True

    def test_temp_path_is_not_real(self, tmp_path):
        assert cp.is_real_config_path(str(tmp_path / "config.json")) is False
        assert cp.is_real_config_path("") is False
        assert cp.is_real_config_path(None) is False

    def test_real_access_blocked_under_tests(self):
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is True

    def test_temp_access_never_blocked(self, tmp_path):
        assert cp.real_config_access_blocked(str(tmp_path / "config.json")) is False

    def test_opt_out_disables_guard(self, monkeypatch):
        # The explicit escape hatch — predicate only; we never actually write.
        monkeypatch.setenv(cp.ENV_ALLOW_REAL_CONFIG, "1")
        assert cp.real_config_writes_allowed() is True
        assert cp.real_config_access_blocked(str(cp.REAL_CONFIG_PATH)) is False

    def test_opt_out_falsey_values_stay_blocked(self, monkeypatch):
        for val in ("0", "false", "no", ""):
            monkeypatch.setenv(cp.ENV_ALLOW_REAL_CONFIG, val)
            assert cp.real_config_writes_allowed() is False


# --------------------------------------------------------------------------- #
# load_config
# --------------------------------------------------------------------------- #
class TestLoadConfig:
    def test_missing_file_yields_defaults(self, tmp_path):
        cfg = cp.load_config(str(tmp_path / "nope.json"))
        assert cfg["strategy"]["degradation_consecutive_laps"] == 2

    def test_temp_file_merges_over_defaults(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"strategy": {"track": "Suzuka"}, "ui": {"refresh_ms": 250}}))
        cfg = cp.load_config(str(p))
        assert cfg["strategy"]["track"] == "Suzuka"
        assert cfg["ui"]["refresh_ms"] == 250
        # Untouched defaults still present after the merge.
        assert cfg["strategy"]["degradation_consecutive_laps"] == 2
        assert cfg["connection"]["port"] == 33741

    def test_corrupt_file_yields_defaults(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text("{ this is : not json ]")
        cfg = cp.load_config(str(p))
        assert cfg["strategy"]["degradation_consecutive_laps"] == 2

    def test_reading_real_config_under_tests_returns_defaults(self):
        # Must NOT read the user's file (no secret exposure); falls back to defaults.
        cfg = cp.load_config(str(cp.REAL_CONFIG_PATH))
        assert cfg == cp.DEFAULT_CONFIG
        # Identity: it's a fresh deep copy, not the shared module dict.
        assert cfg is not cp.DEFAULT_CONFIG

    def test_load_does_not_mutate_default_config(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"strategy": {"track": "Spa"}}))
        cp.load_config(str(p))
        assert cp.DEFAULT_CONFIG["strategy"]["track"] == ""


# --------------------------------------------------------------------------- #
# save_config
# --------------------------------------------------------------------------- #
class TestSaveConfig:
    def test_writes_to_temp_path(self, tmp_path):
        p = tmp_path / "config.json"
        cp.save_config(str(p), {"strategy": {"track": "Monza"}}, backup=False)
        assert json.loads(p.read_text())["strategy"]["track"] == "Monza"

    def test_refuses_real_config_under_tests(self):
        with pytest.raises(cp.ConfigSafetyError):
            cp.save_config(str(cp.REAL_CONFIG_PATH), {"x": 1})

    def test_atomic_leaves_no_temp_file(self, tmp_path):
        p = tmp_path / "config.json"
        cp.save_config(str(p), {"a": 1}, backup=False)
        assert not (tmp_path / "config.json.tmp").exists()
        assert json.loads(p.read_text()) == {"a": 1}

    def test_backup_created_when_target_exists(self, tmp_path):
        p = tmp_path / "config.json"
        cp.save_config(str(p), {"v": 1}, backup=False)     # initial
        cp.save_config(str(p), {"v": 2}, backup=True)      # overwrite w/ backup
        bak = tmp_path / "config.json.bak"
        assert bak.exists()
        assert json.loads(bak.read_text()) == {"v": 1}     # backup holds the PREVIOUS
        assert json.loads(p.read_text()) == {"v": 2}

    def test_no_backup_on_first_write(self, tmp_path):
        p = tmp_path / "config.json"
        cp.save_config(str(p), {"v": 1}, backup=True)
        assert not (tmp_path / "config.json.bak").exists()

    def test_non_serialisable_never_writes_partial(self, tmp_path):
        p = tmp_path / "config.json"
        cp.save_config(str(p), {"ok": 1}, backup=False)
        original = p.read_text()
        with pytest.raises(TypeError):
            cp.save_config(str(p), {"bad": {1, 2, 3}}, backup=False)  # set -> not JSON
        assert p.read_text() == original                  # untouched
        assert not (tmp_path / "config.json.tmp").exists()

    def test_non_dict_rejected(self, tmp_path):
        with pytest.raises(TypeError):
            cp.save_config(str(tmp_path / "config.json"), ["not", "a", "dict"])

    def test_write_default_config_seeds_from_defaults(self, tmp_path):
        p = tmp_path / "config.json"
        written = cp.write_default_config(str(p))
        assert written["strategy"]["degradation_consecutive_laps"] == 2
        on_disk = json.loads(p.read_text())
        assert on_disk["strategy"]["degradation_consecutive_laps"] == 2


# --------------------------------------------------------------------------- #
# DEFAULT_CONFIG invariants
# --------------------------------------------------------------------------- #
class TestDefaultConfig:
    def test_degradation_consecutive_laps_default_is_2(self):
        assert cp.DEFAULT_CONFIG["strategy"]["degradation_consecutive_laps"] == 2

    def test_main_reexports_same_default(self):
        import main
        assert main.DEFAULT_CONFIG is cp.DEFAULT_CONFIG
        assert main.load_config.__module__ == "config_paths"


# --------------------------------------------------------------------------- #
# Secrets hygiene + wiring source-scans
# --------------------------------------------------------------------------- #
class TestSecretsAndWiring:
    def test_no_real_api_key_in_tests_or_repo_sources(self):
        # Match a real key VALUE (long trailing token), not example/placeholder
        # text like "sk-ant-api…" in UI help. Pattern assembled so this test
        # file never contains the literal prefix itself.
        pattern = re.compile("sk-" + "ant-" + r"api\d+-[A-Za-z0-9_\-]{20,}")
        offenders = []
        for path in ROOT.rglob("*.py"):
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if pattern.search(text):
                offenders.append(str(path.relative_to(ROOT)))
        assert not offenders, f"Real Anthropic API key value found in: {offenders}"

    def test_gitignore_protects_config(self):
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        entries = {line.strip() for line in gi}
        assert "config.json" in entries
        assert "config.json.bak" in entries
        assert "config.json.tmp" in entries

    def test_config_json_not_tracked_by_git(self):
        import subprocess
        out = subprocess.run(
            ["git", "ls-files", "config.json"],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        assert out.stdout.strip() == "", "config.json must NOT be tracked by git"

    def test_main_uses_resolve_config_path(self):
        src = (ROOT / "main.py").read_text(encoding="utf-8")
        assert "resolve_config_path(" in src
        assert "from config_paths import" in src

    def test_persist_config_uses_guarded_saver(self):
        src = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
        m = re.search(r"\n    def _persist_config\(.*?(?=\n    def )", src, re.DOTALL)
        assert m, "_persist_config not found"
        body = m.group(0)
        assert "save_config" in body, "_persist_config must delegate to config_paths.save_config"
        assert "ConfigSafetyError" in body, "_persist_config must handle the guardrail error"
        # No raw file write left in the body.
        assert 'open(self._config_path' not in body
        assert "json.dump(" not in body
