"""1.6, the other half: a verdict per call, judged as the laps come in, persisted, shown; board positions per lap on file."""


def edit(path, pairs):
    t = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert t.count(a) == 1, (path, "not unique/missing:", a[:90])
        t = t.replace(a, b)
    open(path, "w", encoding="utf-8").write(t)


R = "C:/Projects/VR_Dashboard/"

edit(R + "pitcrew/race/call_outcome.py", [
    ('''@dataclass(frozen=True)
class Outcome:
    """What followed one call, and how that was established."""
    verdict: str
    detail: str

    @property
    def known(self) -> bool:
        return self.verdict != CANNOT_TELL
''', '''@dataclass(frozen=True)
class Outcome:
    """What followed one call, and how that was established.

    `settled` says whether this is the final word: a `CANNOT_TELL` because
    the laps that answer the call have not been driven yet is provisional
    and is asked again at the next crossing; one because nothing in the
    feed can ever answer this kind of call is final.
    """
    verdict: str
    detail: str
    settled: bool = True

    @property
    def known(self) -> bool:
        return self.verdict != CANNOT_TELL
'''),
    ('''        if not window:
            return Outcome(CANNOT_TELL,
                           "no lap on file at or after the call - the race "
                           "may have ended on it")
''', '''        if not window:
            return Outcome(CANNOT_TELL,
                           "no lap on file at or after the call - the race "
                           "may have ended on it", settled=False)
'''),
    ('''        if len(window) <= BOX_WINDOW_LAPS:
            return Outcome(CANNOT_TELL,
                           f"only {len(window)} lap(s) followed the call, so "
                           f"the window it named was never fully driven")
''', '''        if len(window) <= BOX_WINDOW_LAPS:
            return Outcome(CANNOT_TELL,
                           f"only {len(window)} lap(s) followed the call, so "
                           f"the window it named was never fully driven",
                           settled=False)
'''),
    ('''        window = _laps_after(lap_num, laps, 1)
        if not window:
            return Outcome(CANNOT_TELL, "no lap on file at or after the call")
''', '''        window = _laps_after(lap_num, laps, 1)
        if not window:
            return Outcome(CANNOT_TELL, "no lap on file at or after the call",
                           settled=False)
        if len(window) < 2:
            return Outcome(CANNOT_TELL, "the next lap has not been driven",
                           settled=False)
'''),
    ('''def summarise(calls, laps) -> dict:
''', '''def judge(filed, laps, *, final: bool = False) -> list:
    """`(key, Outcome)` for every filed call that can be settled now.

    `filed` is an iterable of `(key, call)`. A provisional `CANNOT_TELL` -
    the window not yet driven - is left for the next crossing, unless
    `final` (the flag), when it is written as it stands: a call made on the
    last lap is answered by the race ending, and that is recorded rather
    than left blank. **Written as the laps come in, not at the flag**, so
    the driver sees "ACTED - pitted on lap 12" on the Race screen two laps
    after the call, not after the export.
    """
    laps = list(laps)
    out = []
    for key, call in filed:
        outcome = outcome_for(call, laps)
        if outcome.settled or final:
            out.append((key, outcome))
    return out


def summarise(calls, laps) -> dict:
'''),
])

edit(R + "pitcrew/store/schema.py", [
    ('''    "rival_stops": (
        ("compound_reads", "INTEGER NOT NULL DEFAULT 0"),
    ),
''', '''    "rival_stops": (
        ("compound_reads", "INTEGER NOT NULL DEFAULT 0"),
    ),
    # **What became of the call** (7 Sep 2026, plan 1.6): `race/call_outcome`
    # judged against the laps that followed, written as they came in. NULL
    # is "not yet judged"; `cannot-tell` is a judgement that nothing in the
    # feed can answer this kind, and the detail says so.
    "race_revisions": (
        ("verdict", "TEXT"),
        ("verdict_detail", "TEXT"),
    ),
'''),
    ('''SCHEMA_VERSION = 16
''', '''SCHEMA_VERSION = 17
'''),
    ('''  because the 6 Sep 2026 Deep Forest race - seven laps held up behind P2 -
  cannot be replayed with its gaps: the wall read them on 154 frames and
  kept none.  A gap with no track position cannot be binned into sectors
  afterwards, and the position cannot be recovered - the frame is gone.
''', '''  because the 6 Sep 2026 Deep Forest race - seven laps held up behind P2 -
  cannot be replayed with its gaps: the wall read them on 154 frames and
  kept none.  A gap with no track position cannot be binned into sectors
  afterwards, and the position cannot be recovered - the frame is gone.

* **v17** adds `board_positions` - where every named car was on the
  leaderboard at each of our crossings - and two `ADDED_COLUMNS` on
  `race_revisions` for the verdict on each call.  The table is new, so no
  migration function; the columns are additive.
'''),
    ('''CREATE INDEX IF NOT EXISTS idx_gap_reads_session ON gap_reads(session_id, lap);
''', '''CREATE INDEX IF NOT EXISTS idx_gap_reads_session ON gap_reads(session_id, lap);

-- Board position per named driver at each of OUR crossings, as the wall read
-- it. A car off the board (below the top eight, or pitting) has no row for
-- that lap - absence, never a position of 0.
CREATE TABLE IF NOT EXISTS board_positions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    lap         INTEGER NOT NULL,        -- OUR lap just completed
    driver      TEXT    NOT NULL,
    position    INTEGER NOT NULL,
    recorded_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_board_positions_session
    ON board_positions(session_id, lap);
'''),
])

edit(R + "pitcrew/store/db.py", [
    ('''    def rename_driver(self, old: str, new: str) -> int:
''', '''    def record_board_positions(self, session_id: int | None, lap: int,
                               positions: dict) -> int:
        """File where every named car was on the board at this crossing."""
        if session_id is None or not positions:
            return 0
        rows = [(session_id, int(lap), str(driver), int(place), _now())
                for driver, place in positions.items()
                if driver is not None and place is not None]
        if not rows:
            return 0
        with self._write() as conn:
            conn.executemany(
                "INSERT INTO board_positions (session_id, lap, driver, "
                "position, recorded_at) VALUES (?, ?, ?, ?, ?)", rows)
        return len(rows)

    def board_positions(self, session_id: int) -> list[dict]:
        return [dict(r) for r in self._query(
            "SELECT lap, driver, position FROM board_positions "
            "WHERE session_id = ? ORDER BY lap, position, id", (session_id,))]

    def set_revision_verdict(self, revision_id: int, verdict: str,
                             detail: str) -> None:
        """What became of one filed call, judged against the laps after it."""
        with self._write() as conn:
            conn.execute(
                "UPDATE race_revisions SET verdict = ?, verdict_detail = ? "
                "WHERE id = ?", (verdict, detail, int(revision_id)))

    def rename_driver(self, old: str, new: str) -> int:
'''),
])

edit(R + "pitcrew/ui/race_screen.py", [
    ('''    def show_call(self, call) -> None:
        self.last_call.setText(call.call)
        self.last_call.setStyleSheet(
            f"color: {CONFIDENCE_INK.get(call.confidence, theme.STENCIL)};"
            f"background: transparent;")
        self.last_reason.setText(call.reason)
        self.log_empty.setVisible(False)
        self.log_layout.insertWidget(0, CallRow(call))
''', '''    def show_call(self, call):
        """Put the call on the log. Returns its row, so the verdict can be
        written onto it when the laps that answer it have been driven."""
        self.last_call.setText(call.call)
        self.last_call.setStyleSheet(
            f"color: {CONFIDENCE_INK.get(call.confidence, theme.STENCIL)};"
            f"background: transparent;")
        self.last_reason.setText(call.reason)
        self.log_empty.setVisible(False)
        row = CallRow(call)
        self.log_layout.insertWidget(0, row)
        return row
'''),
])

CT = R + "pitcrew/controller.py"
edit(CT, [
    ('''        self.race_run_id = self.store.start_race_run(
            event["id"], approved["id"] if approved else None, self.session_id)
''', '''        self.race_run_id = self.store.start_race_run(
            event["id"], approved["id"] if approved else None, self.session_id)
        # The calls filed this race and not yet judged: revision id -> (call,
        # the log row to write the verdict onto). Rule 11: this race's.
        self._filed_calls = {}
'''),
    ('''        if self.race_screen is not None:
            self.race_screen.show_call(call)
        if self.race_run_id is not None:
            payload = {"call": call.as_export(), "confidence": call.confidence,
                       "kind": call.kind}
            accepted = call.kind == STAY_OUT
            if accepted:
                payload["resolution"] = "driver stayed out"
                self._replans.note_driver_shape(
                    self.race.stops_planned(), lap=call.lap)
            self.store.append_revision(
                self.race_run_id, call.lap, call.call, payload,
                accepted=accepted)
''', '''        row = None
        if self.race_screen is not None:
            row = self.race_screen.show_call(call)
        if self.race_run_id is not None:
            payload = {"call": call.as_export(), "confidence": call.confidence,
                       "kind": call.kind}
            accepted = call.kind == STAY_OUT
            if accepted:
                payload["resolution"] = "driver stayed out"
                self._replans.note_driver_shape(
                    self.race.stops_planned(), lap=call.lap)
            revision_id = self.store.append_revision(
                self.race_run_id, call.lap, call.call, payload,
                accepted=accepted)
            # **Held for its verdict.** `race/call_outcome` has known how to
            # judge a box call against the laps that follow since 23 Aug;
            # `CallRow.set_outcome` has waited for a caller as long. Judged
            # at each crossing from here on - see `_judge_filed_calls`.
            filed = self.__dict__.setdefault("_filed_calls", {})
            filed[revision_id] = (call, row)
'''),
    ('''        try:
            lap_id = self.store.add_lap(self.session_id, lap, frames=frames)
''', '''        try:
            lap_id = self.store.add_lap(self.session_id, lap, frames=frames)
            self._judge_filed_calls()
'''),
    ('''        run_id, self.race_run_id = self.race_run_id, None
        try:
            self.store.finish_race_run(run_id)
''', '''        run_id, self.race_run_id = self.race_run_id, None
        # The flag settles every call still open: a box call made on the
        # last lap is answered by the race ending, and that is written down
        # rather than left blank.
        self._judge_filed_calls(final=True)
        try:
            self.store.finish_race_run(run_id)
'''),
    ('''    def _corner_windows(self):
''', '''    def _judge_filed_calls(self, *, final: bool = False) -> None:
        """Write a verdict onto every filed call the laps can now answer.

        The half of the ledger that was missing (plan 1.6, S10): what was
        said has been on file since Road Atlanta, what the driver then did
        never was. Judged against this session's stored laps - the lap just
        written included - and put on the row and the Race screen together.
        Never into the caller: a verdict that cannot be written is a log
        line, not a crossing lost.
        """
        filed = self.__dict__.get("_filed_calls")
        if not filed or self.session_id is None:
            return
        from types import SimpleNamespace

        from pitcrew.race.call_outcome import judge

        try:
            laps = [SimpleNamespace(**row)
                    for row in self.store.list_laps(self.session_id)]
            settled = judge(((rid, call) for rid, (call, _) in filed.items()),
                            laps, final=final)
            for rid, outcome in settled:
                call, row = filed.pop(rid)
                self.store.set_revision_verdict(rid, outcome.verdict,
                                                outcome.detail)
                if row is not None:
                    try:
                        row.set_outcome(outcome.verdict, outcome.detail)
                    except RuntimeError:
                        pass            # the row is gone with its screen
                log("race").info("call on lap %s judged %s: %s", call.lap,
                                 outcome.verdict, outcome.detail)
        except Exception:                                    # noqa: BLE001
            log("race").exception("the filed calls could not be judged")

    def _corner_windows(self):
'''),
    ('''                samples = wall.take_samples()
                try:
''', '''                samples = wall.take_samples()
                try:
                    self.store.record_board_positions(
                        self.session_id, getattr(lap, "lap_num", 0) or 0,
                        wall.positions())
                except Exception:
                    log("race").exception("the board positions could not "
                                          "be filed")
                try:
'''),
])

edit(R + "pitcrew/export/build.py", [
    ('''            if revision["plan"].get("resolution"):
                entry["resolution"] = revision["plan"]["resolution"]
            calls.append(entry)
    return calls
''', '''            if revision["plan"].get("resolution"):
                entry["resolution"] = revision["plan"]["resolution"]
            # **What the driver then did**, judged as the laps came in
            # (`race/call_outcome`, written by the controller). Absent where
            # the race was recorded before verdicts were kept.
            if revision.get("verdict"):
                entry["verdict"] = revision["verdict"]
                entry["verdictDetail"] = revision.get("verdict_detail")
            calls.append(entry)
    return calls
'''),
])
print("ok")
