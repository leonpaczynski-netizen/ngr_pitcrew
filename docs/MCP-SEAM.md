# Connecting the tuning brain to the app

The knowledge base used to reach Pit Crew's data by the driver copying a payload
out of the app and pasting it into a conversation. `EXPORT-CONTRACT.md` still
defines that payload and is unchanged. **What this replaces is the clipboard.**

## Running it

```bash
python -m pitcrew.mcp.server
```

It speaks stdio, so the client launches it rather than finding it listening.
`PITCREW_DB` points it at a different database; unset, it opens the app's own.

### Claude Code

Registered per project, in `~/.claude.json` under this project's entry - not
globally. It opens one app's database and has no business loading anywhere
else. **The interpreter is named absolutely**: an MCP client is not launched
from a shell, so `python` on PATH is whatever happens to resolve.

```json
"mcpServers": {
  "pitcrew": {
    "command": "C:\\Users\\<you>\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe",
    "args": ["-m", "pitcrew.mcp.server"],
    "cwd": "C:\\Projects\\VR_Dashboard",
    "env": {"PYTHONPATH": "C:\\Projects\\VR_Dashboard"}
  }
}
```

**The path was wrong here for as long as this file existed** - it said
`C:\Projects\Pit_Crew`, which is not where this project is, so anyone
following it registered a server that could not start (plan row 2.12).

## What it will and will not do

**Reads are open.** Events, setup sheets and their shift tables, slider ranges
with the game version they were read on, laps, the full export payload, the
strategy evidence with every figure's provenance, and the prompt log.

**Seven of the eighteen write, and this file used to say none of them did.**
"Writes propose, they never apply" was true when there were two of them and
has not been true for some time; `propose_setup_sheet`, the example it led
with, no longer exists at all - the setup sheet went with `CLAUDE.md` §1a.
Read `.claude/skills/ludo/references/mechanic.md` for the list that is kept
honest by a test; this is the shape of it.

| Tool | What actually happens |
|---|---|
| `propose_strategy` | **Writes.** Saved as an unapproved candidate through `store.save_strategy`. The name says proposal and the row is real; approval is a separate act, and nothing arms a plan that has not been through it. |
| `write_shift_points` | **Writes.** The shift table, per car and circuit - the one setup artefact that reaches the driver through the app, as a beep at 60 Hz. Refuses a fuel-saving rpm at or above its performance rpm, inside the write. |
| `write_strategy` | **Writes.** The race plan, stamped with the context it was approved for. |
| `write_race_knowledge` | **Writes.** The circuit's knowledge row: pit loss, burn, wear. |
| `write_qualifying_plan` | **Writes.** Through `store.save_qualifying_plan`. |
| `write_measurement` | **Writes.** A measurement row, journalled with `note_engineer_write`. |
| `write_verdict` | **Writes.** A verdict row, journalled the same way. |

Eleven read and write nothing: `list_events`, `slider_ranges`,
`event_export`, `laps`, `strategy_evidence`, `car_context`, `shift_points`,
`measurements`, `axis_status`, `prompt_log`, `engineer_writes`.

**`strategy_evidence` used to write too**, and said it did not: building the
evidence saves the measured track clock, because GT7's time-of-day is a name
rather than an hour. It passes `remember=False` now, which is what "read-only"
has to mean (plan row 2.10).

**No tool writes a setup sheet, and none will.** The app's `setup` block was
stale three sessions out of three, and on the third it would have produced a
completely coherent diagnosis of a car that was not on the circuit. Which
sheet is in the car is the one thing only the driver knows - and §1a has since
removed the app's copy altogether, so there is nothing here to write to.

## What it deliberately does not carry

No raw telemetry traces, no GPS arrays, no engine-rpm series. `CLAUDE.md` §8
puts those out of scope for the export and they are out of scope here for the
same reason: the aggregates are the evidence, and a context window spent on
600,000 samples is a context window not spent on what the driver felt.
