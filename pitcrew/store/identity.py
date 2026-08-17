"""Canonical identity for cars and circuits.

**Nothing in this app had a stable identifier for a car or a track.** Every
identity site was a display string, or a slug composed from a display string,
or an integer out of a catalogue whose id space is not the game's. Three bugs
of one family came out of that inside a single day:

* **17 Aug 2026 - session 11.** A run on event 2 streamed `car_category='GR3'`
  on an event whose car is a Road Car. `list_evidence_laps` scoped on
  `event_id` alone with no car predicate, so its lap 4 burn of
  7.563377380371094 L became `assumptions.fuelPerLapL = 7.563` in the
  **approved** race plan. The plan was not merely influenced by the wrong
  car's session; that one lap *is* the figure.
* **A tyre-temperature call that never fired for a whole race**, because a
  scope key composed from display names named a circuit the `events` table
  does not contain.
* **`str.isalnum()` returns True for an accented character**, so the Huracan
  was slugged two ways by two rules and 300 grip observations were
  unreachable from the lookup that wanted them.

All three were invisible because both sides of each comparison were
internally consistent. The answer is not a better string rule - `store/tyres.py
::slugify` already is that, and this module imports it rather than writing a
fifth one. The answer is that identity is **a row with an integer key**, and a
slug is a *column on that row* that callers read rather than recompose.

The asymmetry between the two kinds of identity is the shape of this module:

| | cars | tracks |
|---|---|---|
| identity source | the game, on every frame | the app's catalogue, driver-chosen |
| auto-assignable | yes | **no** - no packet format carries a track id |
| verifiable after the fact | yes, against `sessions.car_id_observed` | only weakly, by lap length |

So **cars are observed and reconciled; tracks are constrained at selection.**
"""
from __future__ import annotations

import sqlite3

# **One slug rule, imported, never re-implemented.** `store/tyres.py::slugify`
# is the canonical one: NFKD-folded to ASCII, so "Huracan" is one key and not
# two. Adding a rule here would be the same bug in a new file.
from pitcrew.store.tyres import slugify

__all__ = [
    "CAR_STREAM_TOKENS",
    "IDENTITY_MISMATCH",
    "IDENTITY_NO_READING",
    "IDENTITY_OK",
    "IDENTITY_QUARANTINED",
    "IDENTITY_UNKNOWN_CAR",
    "NOT_LOADED_CAR_ID",
    "STATUS_CANONICAL",
    "STATUS_QUARANTINED",
    "car_slug",
    "circuit_slug",
    "expected_stream_token",
    "layout_slug",
    "reconcile_car_id",
    "seed_catalogue",
    "slugify",
    "unknown_car_name",
]


# --------------------------------------------------------------- vocabularies

# A canonical row is selectable. A quarantined one exists, is linked, holds
# its data - and is offered to nobody and pooled into no fit. That distinction
# is what reconciles the driver's two requirements: "no car without a distinct
# id may be SELECTED" against "a session must never be lost because the car
# was unknown". Selection is closed; observation is open.
STATUS_CANONICAL = "canonical"
STATUS_QUARANTINED = "quarantined"

# What a session's declared identity turned out to be, once the stream spoke.
IDENTITY_OK = "ok"
IDENTITY_MISMATCH = "car-mismatch"       # the wire said a different car
IDENTITY_UNKNOWN_CAR = "car-unknown"     # the wire said a car nothing knows
IDENTITY_NO_READING = "no-reading"       # the wire said nothing about the car
# Events use the same column for a different question: is the event itself
# resolvable to canonical rows at all.
IDENTITY_QUARANTINED = "quarantined"

# **`car_id = 0` is the "car has not loaded yet" sentinel, not a car.** It was
# measured on 16 Aug 2026 at 19:51:14 - the exact `started_at` of session 42,
# the same session that recorded `car_category = NULL` and
# `fuel_capacity_l = 0.0`. Reading it as an identity would invent a car
# numbered zero and then accuse every real session of being a different one.
NOT_LOADED_CAR_ID = 0

# The catalogue's class against the token GT7 puts on the wire. Used **only**
# by the v7 back-fill, which has no ids to work with: `car_id` was never
# recorded on any archived session, so the class is the only evidence there
# is. Live reconciliation uses the id and ignores this table entirely - a
# class is shared by dozens of cars and cannot tell two Gr.3 cars apart.
#
# `VGT` is deliberately absent rather than guessed. GT7 streams Vision GT cars
# under more than one token and nothing here has measured which; an absent
# entry means "no expectation", which withholds the accusation. Missing is
# null, never a default.
CAR_STREAM_TOKENS: dict[str, str] = {
    "Gr.1": "GR1",
    "Gr.2": "GR2",
    "Gr.3": "GR3",
    "Gr.4": "GR4",
    "Gr.B": "GRB",
    "Gr.X": "GRX",
    "Road Car": "GRN",
}


def expected_stream_token(category: str | None) -> str | None:
    """The token GT7 should stream for a car of this class, or None.

    None means "no expectation on file", which is not the same as "expect
    nothing" - a caller must withhold the mismatch rather than assert one.
    """
    if not category:
        return None
    return CAR_STREAM_TOKENS.get(category.strip())


def unknown_car_name(gt7_car_id: int) -> str:
    """The name a quarantined auto-created car row carries.

    Deliberately not a plausible car name. It has to read as "the app does not
    know what this is" everywhere it is displayed, because the one thing it
    must never do is get mistaken for an identification.
    """
    return f"Unknown car #{int(gt7_car_id)}"


# ------------------------------------------------------------------ the slugs
#
# Three thin wrappers over one rule, so that the *composition* is written down
# once as well. The circuit half joining track and layout with a space BEFORE
# slugging is part of the identity: it is what the existing `corner_models`,
# `track_clock`, `grip_observations` and `tyre_models` keys on disk already
# are, and stage 3 resolves those keys against `track_layouts.slug` by
# equality. Changing the composition here would orphan 1,459 rows.


def car_slug(name: str) -> str:
    return slugify(name)


def layout_slug(track: str, layout: str) -> str:
    return slugify(f"{track} {layout}")


def circuit_slug(track: str, layout: str | None) -> str:
    """The circuit key as the archive already spells it, layout or not."""
    return slugify(f"{track} {layout}" if layout else track)


# ----------------------------------------------------------------- the seeder


def seed_catalogue(conn: sqlite3.Connection, now: str) -> dict[str, int]:
    """Fill `tracks`, `track_layouts` and `cars` from the shipped catalogues.

    Idempotent by design: every insert is `INSERT OR IGNORE` against a unique
    natural key, so running it twice inserts nothing the second time and never
    touches a row that already exists. That matters more than it looks -
    `cars.gt7_car_id` is **learned from the stream**, and a re-seed that
    overwrote a row would throw away the only automatically-verifiable
    identity in the system.

    **No id is imported.** `data/car_id_map.json` looks like it carries the
    game's car ids and does not: the Shelby's live packet id is 3391, that
    file maps 473 to it, and its whole id space tops out at 712. Every car
    seeds with `gt7_car_id = NULL`, which is honest - unmeasured, not zero -
    and every one of the 608 is selectable from the moment it is seeded.

    Returns the counts inserted, for the migration to log.
    """
    from pitcrew.store import catalogs

    counts = {"tracks": 0, "track_layouts": 0, "cars": 0}

    # --- tracks and their layouts -------------------------------------------
    #
    # A layout is its own row and never a suffix on a track key. Three
    # reasons, in order of weight: a corner model belongs to a layout (Monza
    # Full Course and Monza No Chicane share nothing at the corner level); a
    # NULL layout is representable in the old shape and event 1 had one for
    # weeks, which is only made *unrepresentable* by promoting layout to a
    # mandatory column of its own row; and track-level facts - pit loss is a
    # track constant per CLAUDE.md 5.4 - are worth not duplicating per layout.
    track_ids: dict[str, int] = {}
    for record in catalogs.layout_records():
        name = record["track"]
        if name not in track_ids:
            cur = conn.execute(
                "INSERT OR IGNORE INTO tracks (name, kind, slug, created_at) "
                "VALUES (?,?,?,?)", (name, record.get("type"), slugify(name), now))
            counts["tracks"] += cur.rowcount or 0
            row = conn.execute(
                "SELECT id FROM tracks WHERE name = ?", (name,)).fetchone()
            track_ids[name] = int(row[0])

        layout = record["layout"]
        if not layout:
            continue
        variants = [(layout, 0)]
        if record["reversible"]:
            # GT7 offers a reversed configuration as its own entry in the
            # track list. It is a different corner sequence and therefore a
            # different circuit identity, not a flag on the forward one.
            variants.append((layout + catalogs.REVERSE_SUFFIX, 1))
        for spelling, reverse in variants:
            cur = conn.execute(
                "INSERT OR IGNORE INTO track_layouts "
                "(track_id, layout, reverse, length_m, rain, slug, status, "
                " created_at) VALUES (?,?,?,?,?,?,?,?)",
                (track_ids[name], spelling, reverse, record.get("lengthM"),
                 # Null, not 0. The catalogue not saying whether a circuit can
                 # rain is not the same claim as it being unable to.
                 None if record.get("rain") is None else int(record["rain"]),
                 layout_slug(name, spelling), STATUS_CANONICAL, now))
            counts["track_layouts"] += cur.rowcount or 0

    # --- cars ---------------------------------------------------------------
    for name, spec in catalogs.car_specs().items():
        cur = conn.execute(
            "INSERT OR IGNORE INTO cars "
            "(gt7_car_id, name, category, maker, year, drivetrain, pp_rating, "
            " slug, gt7_id_source, gt7_id_game_version, status, created_at) "
            "VALUES (NULL,?,?,?,?,?,?,?,NULL,NULL,?,?)",
            (name, spec.get("category"), spec.get("maker"), spec.get("year"),
             spec.get("drivetrain"), spec.get("pp_rating"), car_slug(name),
             STATUS_CANONICAL, now))
        counts["cars"] += cur.rowcount or 0

    return counts


# --------------------------------------------------------- live reconciliation


class Reconciliation:
    """What the wire said about the car, against what the event declared.

    A value object rather than a tuple because four of its five fields are
    easy to swap by accident and three of them decide whether a session's laps
    reach a race plan.
    """

    __slots__ = ("status", "car_ref_observed", "learn_gt7_id_for",
                 "create_quarantined_id", "note")

    def __init__(self, status: str, *, car_ref_observed: int | None = None,
                 learn_gt7_id_for: int | None = None,
                 create_quarantined_id: int | None = None,
                 note: str | None = None) -> None:
        self.status = status
        self.car_ref_observed = car_ref_observed
        # The `cars.id` whose `gt7_car_id` this run just taught us.
        self.learn_gt7_id_for = learn_gt7_id_for
        # The packet id to auto-create a quarantined row for.
        self.create_quarantined_id = create_quarantined_id
        self.note = note

    def __repr__(self) -> str:                      # pragma: no cover - debug
        return (f"Reconciliation({self.status!r}, "
                f"car_ref_observed={self.car_ref_observed!r}, "
                f"learn_gt7_id_for={self.learn_gt7_id_for!r}, "
                f"create_quarantined_id={self.create_quarantined_id!r})")


def reconcile_car_id(observed_id: int | None, *,
                     event_car: dict | None,
                     car_by_gt7_id: dict | None) -> Reconciliation:
    """Decide a session's identity status from one observed packet car id.

    Pure: the caller does the lookups and the writes. `event_car` is the
    `cars` row the event declares (or None if the event has no car_ref yet);
    `car_by_gt7_id` is the `cars` row that already owns `observed_id`, or None
    if no row does.

    The five outcomes, and why each is what it is:

    * **No reading.** `observed_id` is absent or the not-loaded sentinel 0.
      Nothing is claimed and nothing is accused. This is session 42's shape.
    * **The event declares no car.** Nothing to compare against; the reading
      is recorded and the status left alone.
    * **The event's car has no id yet.** *Learn it.* This is how 608
      catalogue cars acquire real ids, one evening at a time, and it is why
      `car_id_map.json` is never imported: an id that arrived on the wire is
      measured, an id out of a file is a guess that measured false.
    * **The id belongs to a different car.** `car-mismatch`. The session
      records in full - laps, frames, everything - and leaves the evidence
      set until the driver resolves it. **This is bug 1, made loud.**
    * **The id belongs to no car at all.** `car-unknown`, and a quarantined
      `cars` row is created for it so the session has a distinct id to hang
      off immediately. Not selectable, not pooled, not lost.
    """
    if observed_id is None or int(observed_id) == NOT_LOADED_CAR_ID:
        return Reconciliation(
            IDENTITY_NO_READING,
            note="GT7 reported no car id (0 = the car had not loaded)")

    observed_id = int(observed_id)

    if event_car is None:
        # An event with no canonical car cannot be reconciled against. The
        # reading is still worth recording, so the status stays unchanged
        # rather than becoming a mismatch nobody can act on.
        return Reconciliation(IDENTITY_OK,
                              note="event declares no canonical car")

    declared_id = event_car["gt7_car_id"]

    if declared_id is None and car_by_gt7_id is None:
        return Reconciliation(IDENTITY_OK,
                              car_ref_observed=int(event_car["id"]),
                              learn_gt7_id_for=int(event_car["id"]))

    if declared_id is not None and int(declared_id) == observed_id:
        return Reconciliation(IDENTITY_OK,
                              car_ref_observed=int(event_car["id"]))

    if car_by_gt7_id is not None:
        if int(car_by_gt7_id["id"]) == int(event_car["id"]):
            return Reconciliation(IDENTITY_OK,
                                  car_ref_observed=int(event_car["id"]))
        return Reconciliation(
            IDENTITY_MISMATCH,
            car_ref_observed=int(car_by_gt7_id["id"]),
            note=(f"the stream reported car id {observed_id} "
                  f"({car_by_gt7_id['name']}); this event declares "
                  f"{event_car['name']}"))

    # An id nothing on file owns, on an event whose car already has a
    # different id. The car cannot be identified and must not be guessed.
    return Reconciliation(
        IDENTITY_UNKNOWN_CAR,
        create_quarantined_id=observed_id,
        note=(f"the stream reported car id {observed_id}, which no car in the "
              f"catalogue claims; this event declares {event_car['name']}"))
