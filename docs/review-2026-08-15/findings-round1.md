# Round 1 findings — Pit Crew pre-UAT review

Compact form. Each entry gives the claim and where to look. The reviewers supplied
long evidence blocks; those are deliberately NOT reproduced here, because you are to
verify each claim from the source yourself rather than audit their prose.

Baseline: the full test suite passes (exit 0). Every claim below is something the
52 test files currently miss.

---

## AREA: strategy + race engine (pitcrew/strategy/*, pitcrew/race/*)

**S1 · P1 · race/calls.py:216 — `_fuel_instruction` fuels to the flag, not to the next stop.**
Fill computed as `laps_total - stint_ends_on_lap` regardless of whether another stop
follows. Multi-stop race: at stop 1 the driver is told to take fuel for the entire
remaining race. Claimed repro: 30 laps, stints 10/10/10, 3.4 L/lap → "Fuel to 71 litres"
where the next stint needs 37.4 L. `RaceState` (calls.py:76-94) has no next-stint-length
field; `_apply_stint` (coordinator.py:97-110) sets `next_compound` but not its lap count.
Plan already holds the right number at `stints[i]['fuel_l']` (read at controller.py:1634).

**S2 · P1 · race/calls.py:127 — overdue laps counted as fuel in hand.**
`_fuel_gap` = `onboard - state.laps_to_stop()`; `laps_to_stop` (calls.py:107-110) goes
negative past the planned box lap with no floor, so every overdue lap inflates the
reported surplus. `_box_now` fires once (kind lands in `state.said`), so the fuel call
then speaks from the inflated gap. Claimed repro: lap 12, box was lap 10, 8.0 L at
3.4 L/lap → "You can push. 4.4 laps of fuel in hand." at high confidence.
Also check `_past_half_stint` (calls.py:250-257) — trivially True for negative `to_stop`.

**S3 · P1 · race/coordinator.py:80 — timed race's MINUTES loaded into `laps_total`.**
`events.race_laps` holds minutes when `race_type='time'` (UI relabels the spin box at
event_screen.py:543, saves to `race_laps` at :1071; evidence.py:507-511 reads it as
`race_minutes` then converts). `arm` assigns `PlanContext.race_laps` → `state.laps_total`;
controller.start_race (1529-1531) builds it as `int(event['race_laps'] or 0)` without
consulting `race_type`. `_on_green` can't rescue it: GT7 sends `laps_in_race = -1` for
timed races, session_state clamps to 0 (session_state.py:261,281), so the falsy guard at
coordinator.py:138 never overwrites. Claimed repro: 45-min Monza → `laps_total = 45`,
"40 to go" when 19 remain, spurious FUEL_SHORT. **No test covers a timed race.**

**S4 · P1 · strategy/model.py:586 — a compound with no measured wear rate is costed at ZERO degradation, so the unmeasured tyre wins the plan.**
`compound_profiles` sets `wear_per_lap=None` for a compound run but never gauge-read
(evidence.py:186, wear.py:246-247). `_stint_seconds` guard is `if wear:` → None adds no
`pace_loss_s`. Unmeasured compound pays nothing while measured ones pay; `recommend`
ranks it first. Comment at model.py:200-207 claims inheritance of the reference rate —
allegedly only true for a compound with NO profile, not a partial one. Knock-on: the
`guessed` caveat (model.py:709-717) requires `profile.wear_per_lap` truthy so it never
fires, and `worst_fraction` (719-722) is None so the card shows the contradictory pair
"Limited by tyre" + "No tyre wear rate entered, so stint length is fuel-limited only."

**S5 · P1 · race/calls.py:142 — each call kind is said at most once per stint, so a worsening shortfall gets silence.**
`next_call` skips kinds in `state.said`; `_emit` appends on every call
(coordinator.py:179-183); `said` resets only at PIT_EXIT (`clear_stint`, calls.py:290-293).
Docstring promises re-issue "unless it has become more urgent" — nothing implements that.
Claimed repro: gap -3.8 warned at lap 5, then silence at -4.9, -5.9, -7.0.
Also `STATUS_EVERY_LAPS = 5` can only ever match once.

**S6 · P2 · race/replan.py:178 — mid-race re-plan of a timed race plans another FULL race.**
`_remaining_race` shortens `race_laps` but leaves `race_minutes` at the full limit, so
`is_timed` stays True and `clock_bound_stints` walks laps back up to the original limit.
Claimed repro: 10 laps left → `stint_laps=(14,11)` = 25 laps; if adopted,
`stint_ends_on_lap` = lap 29 of a 24-lap race → no box call ever again. Also reports
"0 seconds in it" because `current` is None and gain falls through at replan.py:153.

**S7 · P2 · strategy/model.py:364 — `assumptions.compoundDeltaSPerLap` exports 0.0 for a pace gap the app refused to measure.**
`mean_deficit` averages `pace_delta_s`, which is 0.0 when `pace_known` is False
(model.py:96-99). Same payload emits `paceDeltaSPerLap: null` per compound
(model.py:139-141) and a confident 0.0 in `assumptions`. `comparable_pace`
(evidence.py:300-340) rarely qualifies, so this is the normal case. Contrast
`crossover_lap` (model.py:1042-1048) which correctly refuses. Rule: CLAUDE.md §4.3.

**S8 · P2 · strategy/model.py:357 — export hard-codes `pitLossSource: "measured-this-track"` for a spin-box value.**
Source is `events.pit_loss_secs`, `QDoubleSpinBox`, schema default 20.0
(event_screen.py:572-574, schema.py:95). Nothing measures it. The Strategy screen's own
evidence row calls the same number DECLARED (evidence.py:571-572) — two paths asserting
different provenance for one fact. Rule: CLAUDE.md §4.5, §5.4.

**S9 · P2 · race/calls.py:235 — the fuel-saving call is a fixed "Map 3" whatever the shortfall.**
Same instruction for any gap beyond 0.5 laps. `FUEL_MAP_CONSUMPTION` (model.py:54-56)
puts map 3 at 0.85, so any shortfall >15% of remaining distance is answered with a map
that cannot recover it. Claimed: grep finds `FUEL_MAP_CONSUMPTION`/`FUEL_MAP_POWER` only
in the definition and test_strategy_model.py:254-263 — **no production code reads the table.**
Verify that grep yourself.

---

## AREA: engineer voice / PTT (pitcrew/engineer/*)

**E1 · P1 · controller.py:1648 — PTT answer posted via `QTimer.singleShot` from pynput's hook thread never fires.**
Claim: in PyQt6 the no-receiver overload creates its dispatch object on the *calling*
thread; the pynput daemon thread has no event loop, so the event is never dispatched.
Consequence: `_show_ptt_answer` never runs → `race_screen.show_exchange()` dead, and the
branch turning a spoken "accept"/"keep" into `_resolve_replan()` dead. Driver hears
"Copy, changing the plan" and the plan does not change; `_pending_replan` stays set so
`_check_replan` never offers again. Reviewer claims empirical verification on this
machine. **Re-verify that claim independently — it is the load-bearing one.**

**E2 · P1 · controller.py:242 — semantic gate selected from the configured backend, not the recogniser actually built.**
`recogniser=best_recogniser_for(settings.speech_backend)` falls back
(ptt.py:571-573: sapi → moonshine), but `matcher` is chosen from the *setting*
(`best_semantic_matcher() if speech_backend == SPEECH_MOONSHINE else None`). So when SAPI
fails, the app runs Moonshine free dictation with `matcher=None`; `gate.judge` then
short-circuits (`if distance is None: return Verdict(ACT, ...)`, gate.py:150-151),
bypassing the whole gate. Reviewer claims this is the live config on the owner's machine
(SAPI timed out after 5 s). `settings.py:119` defaults to SAPI and `speech_backend`
appears nowhere in `pitcrew/ui/`, so the default ships.

**E3 · P1 · engineer/intents.py:69 — `match_intent` does SUBSTRING matching, and `"p"` / `"no"` are in PHRASES.**
Docstring (intents.py:27-28) claims whole-word matching; code is `if phrase in text`.
`POSITION` includes `"p"` (line 33), `KEEP` includes `"no"` (line 42). Sorted longest-first,
so these two catch everything else. Claimed: `match_intent('the front is pushing on entry')`
→ `position`; `'i have no grip at the rear'` → `keep`; `'not yet'` → `keep`. UNKNOWN
becomes nearly unreachable so "Say again" is effectively dead. Also consumed at
controller.py:1653-1656 to decide whether a re-plan was declined. Existing test
`test_nonsense_is_unknown_rather_than_the_nearest_guess` allegedly passes by luck.

**E4 · P2 · engineer/ptt.py:98 — `begin`/`end` have no exception boundary although they are the outermost frame on pynput's hook thread.**
pynput converts an escaping exception into StopException: the listener thread stops
permanently, re-raised only in `join()`, which nothing calls. `MoonshineRecogniser.begin`
opens `sd.InputStream`, which raises `PortAudioError` with no input device / device
claimed / device disappeared — none detectable at construction. Result: button dead for
the rest of the race, and `show_capabilities` still reports `hook=has_listener` True.
Note the contrast: the audio callback *inside* begin IS guarded (ptt.py:354-360).

**E5 · P2 · engineer/ptt.py:110 — busy-lock early return skips `_recogniser.end()`, leaking the mic stream.**
`end()` returns on a held `_busy` *before* calling `_recogniser.end()`; `begin()` takes no
lock, so a press always opens the stream but the release can be discarded. Only
`MoonshineRecogniser.end()` stops the stream/transcriber (ptt.py:374-379), so nothing
closes them. Next press reassigns `self._stream`, orphaning the previous one, and the
block counters `gate.check_audio` uses are inflated by a second live stream.

**E6 · P2 · engineer/intents.py:120 — "No stop planned. Running to the flag." asserted when there is simply no plan.**
`lapsToStop` is None in two different states: last stint of a real plan, and no plan at
all. `_apply_stint` sets `stint_ends_on_lap=None` when `_stints` is empty
(coordinator.py:98-101); `_ptt_snapshot` returns `{}` when `self.race is None`
(controller.py:1621-1632). The snapshot cannot distinguish them. Note this is claimed to
be the only None branch in `answer()` that is not a refusal — check LAPS_LEFT/FUEL/BOX_FUEL.
`start_race` explicitly supports arming with no plan (controller.py:1568).

**E7 · P2 · engineer/ptt.py:81 — `set_listener` stops the old hook but never starts the new one.**
Rebinding the PTT key mid-session kills the button on both keys. `start()` only called
from start_race/start_practice (controller.py:1116, 1560). `save_settings` calls
`set_listener` on rebind (controller.py:626-629) then reports
`hook=self.ptt.has_listener` — True, since `has_listener` only tests `is not None`
(ptt.py:76-79). UI shows "keyboard hook loaded" in the non-warning colour.

**E8 · P2 · controller.py:850 — `probe_button` mutates QWidgets from pynput's hook thread.**
Lambdas call `settings_screen.note_ptt(...)` → `setText`/`setStyleSheet`
(settings_screen.py:472-476) on the hook thread. Same defect class the codebase already
fixed one method family away (see `_on_ptt_answer`'s own docstring). Also `_button_probe`
is only stopped by toggling LISTEN off or `shutdown()`, so a forgotten probe keeps
writing widgets throughout a race.

**E9 · P3 · engineer/ptt.py:387 — the gate's five rejection reasons never reach the driver.**
NO_SPEECH / TOO_SHORT / TOO_LONG / NOTHING_HEARD / REPEAT_LOOP are computed, stored in
`last_reason`, then `end()` returns `""` → UNKNOWN → "Say again." for all five.
Claimed: `last_reason` read nowhere outside ptt.py (race_screen.py:184 is an unrelated
same-named attribute). Contradicts gate.py's stated rationale (gate.py:48-56).

**E10 · P3 · engineer/ptt.py:39 — `MAX_CAPTURE_S` is not a cap; nothing stops listening.**
Documented as "how long the driver can hold the button before we stop listening anyway",
but no code truncates a capture. The limit is applied afterwards in `gate.check_audio`,
which returns TOO_LONG and discards the ENTIRE transcript rather than truncating. If the
button sticks the mic stays open indefinitely — nothing bounds the stream but key release.

---

## AREA: telemetry (pitcrew/telemetry/*)

**T1 · P1 · telemetry/session_state.py:319 — pit detection runs on packets where the car is not on track, fabricating a pit stop with measured litres and a tyre change.**
`update()` skips only `paused`/`loading`, never `car_on_track` (session_state.py:221).
`_check_lap` DOES guard on it (375-377) but `_update_pit`, `_refuelling`, `_tyres_swapped`
do not. Returning to the garage: tank refills → `_refuelling` opens a stop; all four tyre
temps step down together → exactly `_tyres_swapped`'s signature. Claimed repro emits
`PIT_ENTRY` then `PIT_EXIT {'fuel_added': 100.0, 'tyres_changed': True}`, and the next lap
is `is_pit_lap=True, fuel_added_l=100.0`. Downstream: db.py:478-495 persists it,
export/build.py:130,142 reads it back, runs.py:324-329 → `tyresChangedAtStop`. In a race
`RaceCoordinator.handle` (coordinator.py:120-126) advances the stint plan for a stop that
never happened. Contrast the offline twin `pit_detect.py:225`, which DOES require
`sample.on_track` and whose docstring says exactly why.
**Cross-check against the memory note that `is_pit_lap` was 0 on all 132 DB laps — these
may be the same bug from opposite ends, or two different ones. Say which.**

**T2 · P2 · telemetry/recorder.py:302 — frames the recorder drops are still charged to lap distance and `t_ms`.**
`record_frame` returns early for off-track/paused/loading WITHOUT updating
`_last_packet_id` (recorder.py:281-283), so the next recorded frame integrates
`speed_ms * step / SAMPLE_HZ` across the whole excursion at the resume speed. `elapsed`
(294-295) has the same problem via `packet_id - _lap_start_packet`. Claimed repro: 30 s
paused mid-lap → `lap_distance_m` 1600 m for 99 m actually covered, `t_ms` 31983 for 1983 ms
driven. Knock-on: corner windows are lap-distance keyed, `corner_model._sample_interval_ms`
computes 269 ms instead of 16.67, and a poisoned fastest lap becomes the corner-model
reference (build.py:213-218) and fails `stored.applies_to(lap_length)`
(resolve.py:35-41), renumbering every corner at that circuit.

**T3 · P2 · telemetry/listener.py:248 — `except OSError: break` kills the listener thread silently, and Windows raises it exactly in direct-PS5 mode.**
Non-timeout `recvfrom` failures break the loop; socket closes, thread exits, no flag set
(`_bind_error`/`_send_error` stay None), nothing logged. On Windows, ICMP port-unreachable
→ `ConnectionResetError` (WSAECONNRESET 10054) on the NEXT `recvfrom`, and that is an
OSError not a `socket.timeout`. Direct mode heartbeats the PS5 every second, which is
precisely how that is provoked when the console is asleep. `_report_health`
(controller.py:1370-1399) can then only print "No telemetry on 33740. Is GT7 running and
SimHub relaying?" — the wrong diagnosis. Claimed: `send_error` is read nowhere outside
listener.py. Directly contradicts listener.py's own docstring (19-21) and CLAUDE.md §7.

**T4 · P3 · telemetry/listener.py:81 — a duplicate `_send_heartbeat` is nested inside `probe_port` as dead code.**
Defined at function-body indent inside `probe_port`, takes `self`, references attributes
not in scope, never bound or called; verbatim copy of the real one at listener.py:275.
Rebuilt on every `probe_port` call. Harmless now; an edit applied to the wrong copy would
be silently inert.

**T5 · P3 · telemetry/selftest.py:71 — `FeedReport.rate_hz` divides by the module constant, not the window actually listened for.**
`check_feed(listen_s=X)` passes X to `_listen` for the real deadline, but `rate_hz` uses
`LISTEN_S = 4.0`. `PitCrewController.test_feed` (controller.py:747) passes it through, so
`listen_s=2.0` reports a healthy 60 Hz feed as "30 Hz" in the headline the driver reads as
proof the feed is healthy (selftest.py:204-209 → controller.py:797).
