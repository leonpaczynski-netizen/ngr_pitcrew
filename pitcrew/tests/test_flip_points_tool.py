"""`tools/flip_points.py` - plan row 5.1's flip search, for one event, as Ludo runs it."""
from __future__ import annotations

from dataclasses import dataclass, field

from pitcrew.strategy.flip import Decision, Flip, FlipReport
from tools import flip_points as tool

TWO = Decision(stops=2, compounds=("RH", "RH", "RH"))


@dataclass
class _Inputs:
    fuel_per_lap_l: float | None = 7.0
    lap_time_ms: int = 100_000
    is_timed: bool = False
    fuel_sd_l: float | None = 0.1
    wear_per_lap: float | None = 0.05
    compound_profiles: dict = field(default_factory=dict)


def test_a_supplied_figure_replaces_practice_and_says_so():
    got, said = tool.overridden(_Inputs(), burn=6.5, lap_ms=101_000, wear_scale=1.2)
    assert got.fuel_per_lap_l == 6.5 and got.lap_time_ms == 101_000
    assert abs(got.wear_per_lap - 0.06) < 1e-9
    assert said[0] == "burn 6.500 L/lap supplied (practice 7.0)"
    assert said[1] == "lap 101.000 s supplied (practice 100.000)"
    assert "0.0500 -> 0.0600 a lap" in said[2]


def _down(at, becomes):
    return Flip("fuel_per_lap_l", "down", 7.0, at=at, searched_to=4.2, becomes=becomes)


def test_the_playbook_line_names_the_refusal_that_applied(monkeypatch):
    monkeypatch.setattr(tool.flip, "playbook_hint", lambda inputs, report: None)
    words = tool.playbook_words
    assert "no runnable plan" in words(_Inputs(), FlipReport(
        base=Decision(stops=None, impossible="nothing fits")))
    assert "no stop to drop" in words(_Inputs(), FlipReport(base=Decision(stops=0)))
    timed = FlipReport(base=TWO, joint=[(95_000.0, [_down(6.2, Decision(stops=1))])])
    assert "timed race" in words(_Inputs(is_timed=True), timed)
    assert "not searched" in words(_Inputs(), FlipReport(base=TWO))
    assert "changes the plan" in words(_Inputs(), FlipReport(base=TWO, flips=[_down(None, None)]))
    tyres = FlipReport(base=TWO, flips=[_down(6.5, Decision(stops=2, compounds=("RH", "RM", "RM")))])
    assert "does not drop a stop" in words(_Inputs(), tyres)
    # An upward flip listed first is not the lower-burn one.
    up = Flip("fuel_per_lap_l", "up", 7.0, at=9.0, searched_to=9.8, becomes=Decision(stops=3))
    assert "changes the plan" in words(_Inputs(), FlipReport(base=TWO, flips=[up, _down(None, None)]))


def test_the_burn_flip_save_is_given_only_where_it_drops_a_stop():
    drops = FlipReport(base=TWO, flips=[_down(6.4, Decision(stops=1))])
    (line,) = tool.burn_flip_save_lines(_Inputs(), drops)
    assert "0.60 L a lap" in line and "unpriced" in line
    tyres = FlipReport(base=TWO, flips=[_down(6.4, Decision(stops=2, compounds=("RH", "RM", "RM")))])
    assert tool.burn_flip_save_lines(_Inputs(), tyres) == []
    timed = FlipReport(base=TWO, flips=[_down(6.4, Decision(stops=1))],
                       joint=[(95_000.0, [_down(6.0, Decision(stops=1))])])
    assert tool.burn_flip_save_lines(_Inputs(is_timed=True), timed) == []


def test_the_report_searches_only_the_inputs_asked_for(monkeypatch):
    asked = {}

    def flip_points(inputs, names=None):
        asked["names"] = names
        return FlipReport(base=Decision(stops=1, compounds=("RM", "RM")),
                          flips=[_down(6.0, Decision(stops=0))])

    monkeypatch.setattr(tool.flip, "flip_points", flip_points)
    monkeypatch.setattr(tool.flip, "flip_on_saving", lambda *a, **k: None)
    monkeypatch.setattr(tool.flip, "playbook_hint", lambda *a: None)
    lines = tool.report(_Inputs(), names=["pit_loss_s"])
    assert asked["names"] == ("pit_loss_s",)
    assert lines[0].startswith("Plan's choice: 1 stop")
    assert any("sigma away on lap-to-lap burn scatter" in line for line in lines)
    supplied = tool.report(_Inputs(), burn_supplied=True)
    assert not any("sigma" in line and "away" in line for line in supplied)


def test_an_impossible_plan_is_said_once(monkeypatch):
    monkeypatch.setattr(tool.flip, "flip_points", lambda inputs, **k: FlipReport(
        base=Decision(stops=None, impossible="no compound lasts")))
    assert tool.report(_Inputs()) == ["No plan to flip: no compound lasts"]


def test_a_missing_archive_is_refused_not_created(tmp_path, monkeypatch, capsys):
    import sys

    path = tmp_path / "typo.db"
    monkeypatch.setattr(sys, "argv", ["flip_points.py", "11", "--db", str(path)])
    assert tool.main() == 1
    assert not path.exists() and "No archive" in capsys.readouterr().out


def test_a_zero_save_cost_is_a_price():
    from pitcrew.strategy.flip import SavingFlip

    said = SavingFlip(5.0, 0.2, 25, Decision(stops=0), 0.0, 15.0).words()
    assert "at 0.00 s a litre" in said
