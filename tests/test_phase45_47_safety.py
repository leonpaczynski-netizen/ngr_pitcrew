"""Phase 45-47 — safety: pure/offline modules, TTS-free strategy, no-AI, DB v27, Apply gate."""
import ast

import strategy.engineering_context_snapshot as m_snap
import strategy.historical_context_resolution as m_hcr
import strategy.telemetry_replay as m_replay
import strategy.prompt_timing as m_timing
import strategy.shadow_advisory as m_shadow
import strategy.voice_delivery as m_voice

PURE = [m_snap, m_hcr, m_replay, m_timing, m_shadow, m_voice]

# strategy modules (incl. voice_delivery) must be free of Qt/DB/network/AI AND of TTS/Windows libs.
FORBIDDEN_IMPORTS = {"PyQt6", "PyQt5", "sqlite3", "requests", "urllib", "openai", "anthropic", "httpx",
                     "socket", "pyttsx3", "win32com", "comtypes", "gtts", "boto3", "azure"}
FORBIDDEN_TOKENS = ("datetime.now(", "time.time(", "time.monotonic(", "random.random(",
                    "random.choice(", "os.environ[", "api_key", "openai", "anthropic", "pyttsx3",
                    "win32com", "SAPI.SpVoice")


def test_strategy_modules_no_forbidden_imports():
    for mod in PURE:
        tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    assert n.name.split(".")[0] not in FORBIDDEN_IMPORTS, (mod.__file__, n.name)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in FORBIDDEN_IMPORTS, mod.__file__


def test_strategy_modules_no_forbidden_tokens():
    for mod in PURE:
        src = open(mod.__file__, encoding="utf-8").read()
        for tok in FORBIDDEN_TOKENS:
            assert tok not in src, (mod.__file__, tok)


def test_windows_port_imports_tts_lazily_only():
    # the Windows adapter may reference win32com but must NOT import it at module top-level.
    import ast as _ast
    src = open("voice/advisory_voice_port.py", encoding="utf-8").read()
    tree = _ast.parse(src)
    for node in tree.body:  # top-level statements only
        if isinstance(node, (_ast.Import, _ast.ImportFrom)):
            names = ([n.name for n in node.names] if isinstance(node, _ast.Import)
                     else [node.module or ""])
            for nm in names:
                assert "win32com" not in nm and "pyttsx3" not in nm, nm


def test_builders_never_raise_on_garbage():
    from strategy.engineering_context_snapshot import build_context_snapshot
    from strategy.historical_context_resolution import resolve_historical_context
    from strategy.telemetry_replay import replay_telemetry
    from strategy.prompt_timing import assess_prompt_timing
    from strategy.shadow_advisory import run_shadow_replay
    from strategy.voice_delivery import VoiceQueue
    for bad in (None, {}, [], "x", 5):
        build_context_snapshot(bad)
        resolve_historical_context(bad)
        replay_telemetry(bad)
        assess_prompt_timing(bad, 1.0)
        run_shadow_replay(bad)
        VoiceQueue().submit(bad)
        VoiceQueue().poll(0.0, voice_enabled=True)


def test_versions_v27():
    from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION
    assert DB_VERSION == 28 and RULE_ENGINE_VERSION == "46.0"


def test_snapshot_capture_is_explicit_write_only():
    import inspect
    from data.session_db import SessionDB
    # read/refresh reports never CALL the snapshot writer.
    for name in ("build_assisted_runtime_report", "build_material_context_trust_report",
                 "build_live_shadow_validation_report"):
        src = inspect.getsource(getattr(SessionDB, name))
        assert "self.capture_context_snapshot(" not in src, name
    # the writer exists and holds the only INSERT into the snapshot table.
    writer = inspect.getsource(SessionDB.capture_context_snapshot).lower()
    assert "insert or ignore into engineering_context_snapshots" in writer


def test_no_ai_no_cloud_tts_in_voice_modules():
    # tokens that would only appear in real cloud/AI usage (not in docstring prose).
    for path in ("strategy/voice_delivery.py", "voice/voice_controller.py",
                 "voice/advisory_voice_port.py"):
        src = open(path, encoding="utf-8").read().lower()
        for bad in ("openai", "anthropic", "api_key", "gtts", "boto3", "http://", "https://",
                    "requests.", "urllib"):
            assert bad not in src, (path, bad)
