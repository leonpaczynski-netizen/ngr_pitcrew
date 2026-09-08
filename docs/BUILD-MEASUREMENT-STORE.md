# Build the measurement and verdict store

*(Written 8 Sep 2026 by the race-engineering session that needed it. Paste the block
below into a fresh Claude Code session in `C:\Projects\VR_Dashboard`.)*

---

Build a measurement store and a verdict store in the Pit Crew database. This is app work.
Read `CLAUDE.md` first — it is the contract and it outranks this brief.

## The problem, concretely

The race engineer (the `ludo` skill) derives numbers from `lap_frames` every session and has
nowhere to put them, so it re-derives them from scratch next time and cannot answer two
questions that have now caused two wrong calls in one day:

1. **"Has this axis ever been tested on this car?"** Ride height had never been A/B'd on any
   car in the programme. Nobody knew, because there was nowhere that fact could live.
2. **"What instrument produced that refutation, and can it resolve the axis at all?"**
   `lsd_a` was recorded as "refuted as an exit lever" on the strength of rear wheel-speed
   split. The split then sat at a median of 0.0000 through a six-click `lsd_a` change while
   an on-power rotation index moved twice its noise floor. **A channel that cannot see the
   change never refuted the lever** — and the record could not say which channel had been used.

Real rows that were written into prose today and will otherwise be re-derived:

- on-power rotation index, Huracán/Daytona T5 exit: **0.00788** (rh 70, `lsd_a` 14, n=15) ·
  **0.00724** (rh 64, `lsd_a` 14, n=2) · **0.00554** (rh 64, `lsd_a` 8, n=3), **noise floor
  0.00104** from splitting one session's clean laps odd/even
- T1 opposite-lock rate: **8/31 laps** at rh 58/70 → **0/2** at rh 58/64
- dynamic rake vs fuel, Huracán: **+0.0060 mm/L**
- Shelby front slip minimum under braking: **0.781** Road Atlanta · **0.869** Red Bull Ring ·
  **0.663** Deep Forest
- short-shift trade, Huracán/Daytona: fuel **+3.458 L/1000 rpm**, lap **−6.767 s/1000 rpm**

## What to build

Two tables, plus the callers. Follow the existing house style in `pitcrew/store/schema.py`
and `pitcrew/store/db.py`.

**`measurement`** — one derived number with everything needed to trust or refuse it:
car, circuit, a config identifier, zone or scope, metric name, value, unit, sample count `n`,
`noise_floor`, how the floor was obtained, source class (`MEASURED` / `DERIVED` / `DOCTRINE` /
`ASSUMED` / `DRIVER REPORT`), the tool or function that produced it, session ids, date,
game version. **`noise_floor` is nullable and NULL means "not established" — never 0.0.**

**`verdict`** — what an axis is believed to do and on what evidence:
car, circuit, axis (a slider key), direction tested (`up` / `down` / `both`), verdict
(`confirmed` / `refuted` / `untested` / `unresolvable`), the instrument used, that instrument's
floor, the measurement rows it rests on, date, game version, and a free-text `why`.
**`untested` must be representable and must be the default answer to a query about an axis with
no rows** — that is the whole point of the table.

Both tables need a real caller. Add:
- a store API on `Store` (`record_measurement`, `record_verdict`, and query helpers),
- MCP tools beside the existing `write_shift_points` / `write_race_knowledge` in
  `pitcrew/mcp/server.py`, so the engineer can write and read them mid-session,
- a small CLI in `tools/` for reading them back.

## Hard constraints — each is a defect this project has already paid for

1. ⛔ **No setup values.** `brain/car-state/<car>-<circuit>.md` is the ONLY place a setup value
   may be written (`CLAUDE.md` §1a). A copy in a table is a second value, which is the exact
   defect removed on 5 Sep. Reference a config by hash or label; never store the sliders.
2. ⛔ **This codebase has built both ends and skipped the caller five times.** A table with no
   writer is worse than no table. The acceptance test below exists for this.
3. **Migrations are additive only.** `SCHEMA_VERSION` is 17. New tables go in the DDL as
   `CREATE TABLE IF NOT EXISTS`; new columns on existing tables go in `ADDED_COLUMNS` **and**
   in the DDL. A column added to the DDL without an `ADDED_COLUMNS` entry is invisible on every
   existing database — that has happened here before.
4. **Missing is NULL, never 0.** Absolute, every layer (`CLAUDE.md` rule 3). And no
   `max(x, 0.0)` on a measurement — return `None` and say why (rule 9).
5. ⛔ **Never smoke-test against the live database.** `PITCREW_DATA_DIR` does nothing;
   `Store()` always opens the real `data/pitcrew.db`. Use a temp path explicitly. Likewise,
   constructing `MainWindow` with the real config path overwrites the user's `config.json`.
6. **Do not touch `MEMORY.md`.** The markdown memory keeps the lessons and the prose; only the
   numbers move. The two stores are complements, not a migration.

## Acceptance

- `python -m pytest pitcrew/tests` green, exit 0. It should be — verified 6 Sep.
- A test that opens a **pre-migration copy** of the schema and confirms both tables and every
  added column appear, with existing rows intact.
- A test that writes a measurement with a NULL noise floor and confirms it reads back NULL.
- **A test that asserts the caller exists** — that the MCP tool and the store API are reachable
  and that a round trip through them lands a row. This is constraint 2 made executable.
- The real rows listed above back-filled, so the store is non-empty and immediately useful.
- A query that answers *"which axes on car X at circuit Y have never been tested?"* in one call.

## Out of scope

Migrating the markdown memory. Any UI. Any change to `lap_frames`, `laps` or the export
contract. Anything that reads or writes GT7 game state.

Report honestly at the end: what is built, what is tested, what is back-filled, and anything
you could not do.
