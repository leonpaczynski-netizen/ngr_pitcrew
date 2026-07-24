# Finding: a layout with no model silently loads a *different* layout's reference path

**Found:** 2026-07-23, while building the guided Track Model surface (stage 4b).
**Status:** ✅ **FIXED** 2026-07-23 (`c47b4c3`) — option 1, the recommendation below.
Kept as the record of what went wrong and why the fix is shaped the way it is.

## What happens

```python
>>> from data.reference_path_loader import reference_path_asset_summary as s
>>> s("watkins_glen_international", "watkins_glen_international__short_course")
{'available': True, 'source': 'calibration_reference_path',
 'message': 'Approved reference path available (200 stations).',
 'station_count': 200, 'lap_length_m': 5379.0}
```

There is no model for the **short course**. That is the **long course's** reference path
— 200 stations, 5379 m — returned as an approved asset for a different layout.

## Why

`data/reference_path_loader._ids_match` compares *significant* tokens, and
`_GENERIC_TOKENS` discards the very words that distinguish one layout from another:

```python
>>> _sig_tokens(_norm_id("watkins_glen_international__short_course"))
{'watkins', 'glen'}
>>> _sig_tokens(_norm_id("watkins_glen_international__long_course"))
{'watkins', 'glen'}
```

Identical, so the layouts are indistinguishable and the match succeeds.

## How far it reaches

Of the 121 layouts in the seed, **45 layout-id pairs collide by prefix alone** — every
`…_reverse` variant, plus cases like `autodrome_lago_maggiore__east` vs `…__east_end`.
Token-level collisions are broader still, since "course", "short", "long" and similar
are all treated as generic. Location ids do not collide (0 pairs), so this is
layout-level.

`resolve_track_readiness_from_disk` builds directly on this, so the layout is reported
`READY_APPROVED` with `confidence=high` and no blockers.

## Why it matters

Anything reading the reference path for an unmodelled layout gets another layout's
racing line and lap length: live progress resolution, station mapping, and the trusted
lap length. All of it silently, and reported as approved rather than as a fallback.

It also directly undermines the new Track Model surface: the guided flow would say
**"This track is modelled"** for a layout that has never been modelled, which is the
opposite of what that screen exists to tell the driver.

## Not worked around

The stage-4b tests use ids with no model on disk so they exercise the new code rather
than this behaviour. Nothing was added to mask it — a guard in the UI would hide a
wrong lap length rather than prevent it.

## Options

1. **Require an exact layout match** when a layout id is supplied, and keep the tolerant
   path only for the track-only lookup. Most correct; needs a check that nothing relies
   on the tolerance for display-name vs canonical-id inputs.
2. **Stop treating layout-distinguishing words as generic** (`short`, `long`, `course`,
   `reverse`, `east`, `end`…). Smaller change, but it is a denylist and the next
   distinguishing word will reintroduce the bug.
3. **Return the matched identity** in the summary so callers can reject a mismatch.
   Weakest — every caller then has to remember to check.

Option 1 is the recommendation. The regression test to write first is the reproduction
above: `short_course` must report unavailable while `long_course` reports available.

---

## What was done

Option 1, as recommended. `_ids_match` was doing two different jobs with one rule, so it
was split into the two it was actually doing:

* `_track_ids_match` — tolerant, unchanged. The tolerance is *required*: `ui/dashboard.py`
  and `ui/live_ui.py` both pass `track_hint = track_location_id or event.track`, so a
  display name has to resolve a canonical id.
* `_layout_ids_match` — normalised equality. An empty request stays a wildcard for the
  track-only lookup; an asset recording no layout can never satisfy a request for one.

Both call sites were updated, including `validate_reference_path_identity`, which gates
whether live pit confidence may be lifted and could previously verify an asset belonging
to a different layout.

**Strict turned out not to mean brittle.** `_norm_id` already absorbs case and
separators, so `"Watkins Glen International__Long Course"` still matches its canonical
id. Only a genuinely different layout fails.

### Verified against the reference paths on disk

| Layout | Available | Lap length | Approved |
|---|---|---:|---|
| `watkins_glen…__long_course` | yes | 5379 m | yes |
| `watkins_glen…__short_course` | **no** | — | **no** |
| `fuji…__full_course` | yes | 4441 m | yes |
| `fuji…__full_course_reverse` | **no** | — | **no** |
| `daytona…__road_course` | yes | 5420 m | yes |
| `daytona…__oval` | **no** | — | **no** |

Track-hint tolerance confirmed intact: `resolve_trusted_lap_length("Watkins Glen", …)`
still returns 5378.5 m.

27 tests written before the fix; 2,415 pass across the track and live-progress domains.

### Expect this to look like a regression

Layouts that reported `READY_APPROVED` off a neighbour's data now report
`MISSING_ASSET`. Tracks that appeared modelled will appear unmodelled — because they
always were. The app was answering with another layout's racing line, and a wrong lap
length silently corrupts fuel and stint maths.
