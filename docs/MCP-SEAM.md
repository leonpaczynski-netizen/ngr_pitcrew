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

```json
{
  "mcpServers": {
    "pitcrew": {
      "command": "python",
      "args": ["-m", "pitcrew.mcp.server"],
      "cwd": "C:\Projects\VR_Dashboard"
    }
  }
}
```

## What it will and will not do

**Reads are open.** Events, setup sheets and their shift tables, slider ranges
with the game version they were read on, laps, the full export payload, the
strategy evidence with every figure's provenance, and the prompt log.

**Writes propose. They never apply.**

| Tool | What actually happens |
|---|---|
| `propose_setup_sheet` | Filed in the **prompt log** for review. The stored sheet is untouched; it is applied on the Event screen, exactly as a pasted reply is today. |
| `propose_strategy` | Saved as an **unapproved** candidate. Approval is a separate act in the app, and nothing arms a plan that has not been through it. |

The reason is `CLAUDE.md` §4.1 and one measured incident. The app's `setup`
block was stale three sessions out of three, and on the third it would have
produced a completely coherent diagnosis of a car that was not on the circuit.
**Which sheet was in the car is the one thing only the driver knows**, and a
tool that could write one would make being wrong about it unrecoverable.

## What it deliberately does not carry

No raw telemetry traces, no GPS arrays, no engine-rpm series. `CLAUDE.md` §8
puts those out of scope for the export and they are out of scope here for the
same reason: the aggregates are the evidence, and a context window spent on
600,000 samples is a context window not spent on what the driver felt.
