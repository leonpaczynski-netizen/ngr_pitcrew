"""Phase 45-47 — deterministic golden: snapshot digest, shadow summary, voice queue."""
from strategy.engineering_context_snapshot import build_context_snapshot
from strategy.telemetry_replay import replay_telemetry
from strategy.shadow_advisory import run_shadow_replay
from strategy.voice_delivery import VoiceQueue


_CONTENT = dict(driver="Leon", car="Porsche", track="Fuji", layout_id="fc", discipline="race",
                compound="RH", tyre_multiplier="5", gt7_version="1.49", event_id="E1",
                event_name="Practice")
_PLAN = {"content_fingerprint": "pfp", "run_structure": {"minimum_clean_laps": 3, "warm_up_laps": 2}}


def test_snapshot_digest_stable_across_instances():
    assert build_context_snapshot(_CONTENT).semantic_digest \
        == build_context_snapshot(dict(_CONTENT)).semantic_digest


def test_event_edit_does_not_change_old_snapshot_digest():
    old = build_context_snapshot(_CONTENT).semantic_digest
    # a later edit produces a NEW snapshot; the old digest value is a pure function of old content.
    _new = build_context_snapshot(dict(_CONTENT, tyre_multiplier="8")).semantic_digest
    assert build_context_snapshot(_CONTENT).semantic_digest == old and _new != old


def test_shadow_summary_deterministic():
    frames = [{"dt": 0.2, "lap": 1, "run_active": True, "segment_type": "straight", "workload": "low",
               "telemetry_fresh": True, "clean_laps": 1}]
    r = replay_telemetry(frames)
    a = run_shadow_replay(r.to_dict(), context_fingerprint="cfp", run_plan=_PLAN).content_fingerprint
    b = run_shadow_replay(r.to_dict(), context_fingerprint="cfp", run_plan=_PLAN).content_fingerprint
    assert a == b


def test_voice_queue_deterministic_under_test_clock():
    q1 = VoiceQueue(); q2 = VoiceQueue()
    p = {"message": "T2 throttle", "priority": 5, "prompt_class": "informational",
         "suppression_key": "coach:T2", "cooldown_seconds": 30.0}
    q1.submit(p); q2.submit(dict(p))
    d1 = q1.poll(100.0, voice_enabled=True); d2 = q2.poll(100.0, voice_enabled=True)
    assert d1.to_dict() == d2.to_dict()


def test_replay_shuffle_would_change_order_but_content_stable_for_same_input():
    frames = [{"dt": 0.1, "lap": i, "segment_type": "straight"} for i in range(1, 5)]
    assert replay_telemetry(frames).content_fingerprint \
        == replay_telemetry(list(frames)).content_fingerprint
