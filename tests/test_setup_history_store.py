"""SetupHistoryStore — persisted applied-setup revisions (UAT-7).

"No way to load previous settings to activate that's the settings I'm running in GT7."
The authority kept only the current revision, so the Lineage tab was blank and nothing
could be loaded. This records each applied revision per scope+discipline.
"""

from services.setup_history_store import SetupHistoryStore, default_history_path
from services.setup_store import scope_key


SCOPE = scope_key("Porsche", "Watkins", "long")


def _store(tmp_path):
    return SetupHistoryStore(str(tmp_path / "revs.json"))


class TestRecordAndRead:
    def test_records_are_returned_oldest_first(self, tmp_path):
        s = _store(tmp_path)
        s.record(SCOPE, "race", revision=2, label="Setup 1 · rev 2", fields={"arb_front": 4})
        s.record(SCOPE, "race", revision=1, label="Setup 1 · rev 1", fields={"arb_front": 5})
        assert [r["revision"] for r in s.revisions(SCOPE, "race")] == [1, 2]

    def test_re_recording_a_revision_updates_in_place(self, tmp_path):
        s = _store(tmp_path)
        s.record(SCOPE, "race", revision=1, label="Setup 1 · rev 1", fields={"arb_front": 5})
        s.record(SCOPE, "race", revision=1, label="Setup 1 · rev 1", fields={"arb_front": 5})
        assert len(s.revisions(SCOPE, "race")) == 1     # re-confirm never grows the lineage

    def test_disciplines_are_separate(self, tmp_path):
        s = _store(tmp_path)
        s.record(SCOPE, "race", revision=1, label="R", fields={"arb_front": 5})
        s.record(SCOPE, "qualifying", revision=1, label="Q", fields={"arb_front": 6})
        assert len(s.revisions(SCOPE, "race")) == 1
        assert s.revisions(SCOPE, "qualifying")[0]["label"] == "Q"

    def test_snapshot_returns_a_revisions_fields(self, tmp_path):
        s = _store(tmp_path)
        s.record(SCOPE, "race", revision=3, label="v3", fields={"arb_front": 4, "arb_rear": 3})
        assert s.snapshot(SCOPE, "race", 3) == {"arb_front": 4, "arb_rear": 3}
        assert s.snapshot(SCOPE, "race", 99) is None

    def test_a_zero_or_negative_revision_is_not_recorded(self, tmp_path):
        s = _store(tmp_path)
        assert s.record(SCOPE, "race", revision=0, label="x", fields={}) is False
        assert s.revisions(SCOPE, "race") == []


class TestPersistence:
    def test_revisions_survive_a_reload(self, tmp_path):
        s = _store(tmp_path)
        s.record(SCOPE, "race", revision=1, label="v1", fields={"arb_front": 5})
        s.record(SCOPE, "race", revision=2, label="v2", fields={"arb_front": 4})
        again = _store(tmp_path)                          # the restart case
        assert [r["revision"] for r in again.revisions(SCOPE, "race")] == [1, 2]

    def test_a_missing_file_is_simply_empty(self, tmp_path):
        assert _store(tmp_path).revisions(SCOPE, "race") == []

    def test_a_corrupt_file_degrades_to_empty(self, tmp_path):
        p = tmp_path / "revs.json"
        p.write_text("{ not json", encoding="utf-8")
        assert SetupHistoryStore(str(p)).revisions(SCOPE, "race") == []

    def test_no_path_works_in_memory_and_never_raises(self):
        s = SetupHistoryStore()
        s.record(SCOPE, "race", revision=1, label="v1", fields={"arb_front": 5})
        assert [r["revision"] for r in s.revisions(SCOPE, "race")] == [1]

    def test_default_path_sits_beside_the_config(self):
        assert default_history_path("/x/y/config.json").endswith("setup_revisions.json")
        assert default_history_path("") == ""
