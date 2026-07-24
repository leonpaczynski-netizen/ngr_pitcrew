"""The programme map — where the driver is in the whole event programme (UAT-6).

"I feel like we are going in circles." The engineer nominates one weakest domain at a
time and, after each run, the next — correctly — but nothing showed how many runs an
area needs or how many remain. This turns the readiness the Command Centre already
produces into a map with per-area progress and the runs still to do.
"""

import pytest

from strategy.programme_map import (
    TARGET_ADEQUATE, TARGET_STRONG, ProgrammeMap, build_programme_map,
)


def _readiness(**levels):
    """Build a readiness list ([name, level, note]) from name->(level, exact) kwargs."""
    out = []
    for name, (level, exact) in levels.items():
        out.append([name, level, f"{exact} exact / 0 labelled sample(s)"])
    return out


# The state the user's screenshot showed: most areas at 2 exact, a couple ahead.
_UAT_STATE = _readiness(
    base_setup=("developing", 2), race_setup=("developing", 2),
    driver_coaching=("developing", 2), consistency=("strong", 5),
    tyre_evidence=("developing", 2), fuel_evidence=("developing", 2),
    race_pace=("adequate", 3), qualifying_setup=("developing", 2),
    strategy_evidence=("developing", 2),
)


class TestItShowsProgressNotJustALevel:
    def test_each_area_says_how_many_runs_it_has_and_needs(self):
        m = build_programme_map(_UAT_STATE)
        base = next(d for d in m.domains if d.key == "base_setup")
        assert base.done == 2 and base.target == TARGET_ADEQUATE
        assert base.runs_remaining == 1
        assert "1 more run" in base.progress_text

    def test_a_covered_area_reads_as_covered(self):
        m = build_programme_map(_UAT_STATE)
        pace = next(d for d in m.domains if d.key == "race_pace")
        assert pace.is_ready and pace.runs_remaining == 0
        assert "covered" in pace.progress_text

    def test_a_strong_area_is_flagged_beyond_the_target(self):
        m = build_programme_map(_UAT_STATE)
        cons = next(d for d in m.domains if d.key == "consistency")
        assert cons.level == "strong" and cons.done >= TARGET_STRONG
        assert "strong" in cons.progress_text

    def test_each_area_names_the_run_that_fills_it(self):
        m = build_programme_map(_UAT_STATE)
        names = {d.key: d.run_name for d in m.domains}
        assert names["driver_coaching"] == "coaching run"
        assert names["tyre_evidence"] == "tyre test"
        assert names["qualifying_setup"] == "qualifying simulation"


class TestTheOverallPicture:
    def test_it_counts_covered_areas_and_a_completion_figure(self):
        m = build_programme_map(_UAT_STATE)
        assert m.domains_total == 9
        assert m.domains_ready == 2                     # race_pace + consistency
        assert m.overall_pct == round(100 * 2 / 9)
        assert "2 of 9 areas covered" in m.headline

    def test_it_plans_the_next_runs_weakest_first(self):
        m = build_programme_map(
            _readiness(base_setup=("missing", 0), race_setup=("developing", 2),
                       race_pace=("adequate", 3)),
            next_count=3)
        # missing area comes before the developing one; the covered one is not listed.
        titles = [t for t, _ in m.next_runs]
        assert titles[0] == "Base setup"
        assert "Race pace" not in titles

    def test_a_finished_programme_says_so(self):
        m = build_programme_map(
            _readiness(base_setup=("adequate", 3), race_pace=("strong", 4)))
        assert m.domains_ready == m.domains_total
        assert "covered" in m.headline.lower()
        assert m.next_runs == ()


class TestTheCurrentObjectiveIsFlagged:
    def test_the_engineers_next_domain_is_marked(self):
        m = build_programme_map(_UAT_STATE, next_domain="setup_base")
        base = next(d for d in m.domains if d.key == "base_setup")
        assert base.is_next is True
        assert sum(1 for d in m.domains if d.is_next) == 1

    def test_no_next_domain_flags_nothing(self):
        m = build_programme_map(_UAT_STATE)
        assert not any(d.is_next for d in m.domains)


class TestCapAndOrdering:
    def test_partial_only_evidence_is_shown_as_capped(self):
        capped = [["tyre_evidence", "developing", "3 exact / 2 labelled sample(s)"]]
        m = build_programme_map(capped)
        d = m.domains[0]
        assert d.capped is True
        assert "exact car and track" not in d.progress_text  # only shown when done==0

    def test_areas_render_in_programme_order_not_alphabetical(self):
        m = build_programme_map(_UAT_STATE)
        keys = [d.key for d in m.domains]
        assert keys.index("base_setup") < keys.index("qualifying_setup")
        assert keys.index("base_setup") < keys.index("strategy_evidence")


class TestNeverRaises:
    def test_empty_readiness_is_an_empty_map(self):
        m = build_programme_map([])
        assert isinstance(m, ProgrammeMap) and not m.has_programme
        assert "No programme yet" in m.headline

    @pytest.mark.parametrize("junk", [None, "nope", [None, 7], [{}], [["only-name"]]])
    def test_junk_never_raises(self, junk):
        assert isinstance(build_programme_map(junk), ProgrammeMap)

    def test_a_mapping_row_shape_is_accepted_too(self):
        rows = [{"name": "base_setup", "level": "developing",
                 "note": "2 exact / 0 labelled sample(s)"}]
        m = build_programme_map(rows)
        assert m.domains and m.domains[0].done == 2
