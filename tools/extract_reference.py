"""Lift the static GT7 reference data out of the retired HTML tool.

    python tools/extract_reference.py

`reference/gt7-race-engineering.html` was the front end of this programme until
the prompt builder moved into the app.  Four of its object literals are pure
GT7 reference data that the app had no equivalent of — the car table's
drivetrain and aspiration, the whole circuit table, the symptom vocabulary and
the slider-range library.  This lifts them into `data/`, once, reproducibly, so
that nobody ever hand-edits a JavaScript object literal again.

Re-run it if the HTML is ever revised.  It is idempotent and it never writes
anything derived from a database — everything it emits is shipped reference
data.

Two judgements are encoded here rather than in the output, so they can be
argued with:

* **Car names.** The app already had `data/car_specs.json`, keyed by the GT7
  name, and the range record and every event join on that exact string.  So
  the app's key wins and the HTML's fields are merged onto it; only cars with
  no counterpart at all are added under the HTML's own label.
* **Circuits.** GT7 sends no track id, and the HTML's short circuit names
  ("Fuji Speedway (Full)") are not the names the app's catalogue uses ("Fuji
  International Speedway").  The alias table below is the join, hand-written,
  because a fuzzy match that silently pairs Big Willow with Streets of Willow
  would put the wrong wear axle in a setup brief.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "reference" / "gt7-race-engineering.html"
DATA = ROOT / "data"

NOTE = ("Lifted from reference/gt7-race-engineering.html by "
        "tools/extract_reference.py. Static GT7 reference data: the app reads "
        "it and never writes it. Do not hand-edit — re-run the tool.")

# HTML category -> the app's category vocabulary.  "Road" is the HTML's bucket
# for everything that is not a race class; the app spells it "Road Car".
CATEGORIES = {
    "Road": "Road Car", "Gr.1": "Gr.1", "Gr.2": "Gr.2", "Gr.3": "Gr.3",
    "Gr.4": "Gr.4", "Gr.B": "Gr.B", "Gr.X": "Gr.X", "VGT": "VGT",
}

# The one HTML car whose label collides with an existing app car rather than
# being a car the app is missing.  Everything else that fails to match is
# genuinely absent from car_specs.json and gets added.
CAR_ALIASES = {"AMG GT3 '20": "AMG Mercedes-AMG GT3 '20"}

# circuit name in the HTML -> the names an event's "track" / "track – layout"
# may carry for the same circuit.  Reverse layouts are deliberately never
# aliased: the same corners in the other direction wear the other side of the
# car, so inheriting the wear axle would be wrong.
CIRCUIT_ALIASES = {
    "Nürburgring GP": ["Nürburgring – GP"],
    "Nürburgring Nordschleife": ["Nürburgring – Nordschleife",
                                 "Nürburgring – Nordschleife Tourist"],
    "Nürburgring 24h": ["Nürburgring – 24h"],
    "Nürburgring Endurance": ["Nürburgring – Endurance"],
    "Spa-Francorchamps": ["Circuit de Spa-Francorchamps"],
    "Monza (Full)": ["Autodromo Nazionale Monza"],
    "Monza (No Chicane)": ["Autodromo Nazionale Monza – No Chicane"],
    "Suzuka": ["Suzuka Circuit"],
    "Brands Hatch GP": ["Brands Hatch Grand Prix Circuit",
                        "Brands Hatch – Grand Prix Circuit"],
    "Brands Hatch Indy": ["Brands Hatch Indy Circuit",
                          "Brands Hatch – Indy Circuit"],
    "Interlagos": ["Autódromo de Interlagos",
                   "Autodromo Jose Carlos Pace"],
    "Red Bull Ring": ["Red Bull Ring"],
    "Autopolis (Full)": ["Autopolis International Racing Course"],
    "Fuji Speedway (Full)": ["Fuji International Speedway"],
    "Tsukuba": ["Tsukuba Circuit"],
    "Watkins Glen Long": ["Watkins Glen International – Long Course"],
    "Watkins Glen Short": ["Watkins Glen International – Short Course"],
    "Daytona Road": ["Daytona International Speedway – Road Course"],
    "Daytona Tri-Oval": ["Daytona International Speedway – Tri-Oval"],
    "WeatherTech Laguna Seca": ["WeatherTech Raceway Laguna Seca"],
    "Mount Panorama (Bathurst)": ["Mount Panorama Motor Racing Circuit"],
    "Barcelona-Catalunya GP":
        ["Circuit de Barcelona-Catalunya – Grand Prix Layout"],
    "Barcelona No Chicane":
        ["Circuit de Barcelona-Catalunya – Grand Prix Layout No Chicane"],
    "Circuit de la Sarthe (Le Mans)": ["24 Heures du Mans Racing Circuit"],
    "Sarthe No Chicane": ["24 Heures du Mans Racing Circuit – No Chicane"],
    "Willow Springs Big Willow":
        ["Willow Springs International Raceway – Big Willow"],
    "Michelin Raceway Road Atlanta": ["Michelin Raceway Road Atlanta"],
    "Goodwood Motor Circuit": ["Goodwood Motor Circuit"],
    "Circuit Gilles-Villeneuve": ["Circuit Gilles Villeneuve"],
    "Yas Marina": ["Yas Marina Circuit"],
    "Dragon Trail Seaside": ["Dragon Trail – Seaside"],
    "Dragon Trail Gardens": ["Dragon Trail – Gardens"],
    "Trial Mountain": ["Trial Mountain Circuit"],
    "Deep Forest": ["Deep Forest Raceway"],
    "Grand Valley Highway 1": ["Grand Valley – Highway 1", "Grand Valley"],
    "Grand Valley South": ["Grand Valley – South"],
    "Alsace Village": ["Alsace – Village"],
    "Broad Bean Raceway": ["Broad Bean Raceway"],
    "Kyoto Driving Park Yamagiwa": ["Kyoto Driving Park – Yamagiwa"],
    "Kyoto Driving Park Miyabi": ["Kyoto Driving Park – Miyabi"],
    "Kyoto Yamagiwa+Miyabi": ["Kyoto Driving Park – Yamagiwa + Miyabi"],
    "Tokyo Expressway East CW": ["Tokyo Expressway – East Clockwise"],
    "Tokyo Expressway Central CW": ["Tokyo Expressway – Central Clockwise"],
    "Tokyo Expressway South CW": ["Tokyo Expressway – South Clockwise"],
    "Special Stage Route X": ["Special Stage Route X"],
    "Blue Moon Bay Speedway": ["Blue Moon Bay Speedway"],
    "Blue Moon Bay Infield A": ["Blue Moon Bay Speedway – Infield A"],
    "Sardegna Road Track A": ["Sardegna – Road Track"],
    "Eiger Nordwand": ["Eiger Norwand", "Eiger Nordwand"],
    "High Speed Ring": ["High Speed Ring"],
    "Autodrome Lago Maggiore Full":
        ["Autodrome Lago Maggiore – Full Course"],
    "Lago Maggiore West End": ["Autodrome Lago Maggiore – West End"],
    "Circuit de Sainte-Croix A": ["Circuit de Sainte-Croix"],
    "Circuit de Sainte-Croix B": ["Circuit de Sainte-Croix – Layout B"],
    "Circuit de Sainte-Croix C": ["Circuit de Sainte-Croix – Layout C"],
}

CIRCUIT_KINDS = {"R": "real", "O": "original"}


# --------------------------------------------------------------- the source

def _jsonish(body: str) -> str:
    """Turn a JavaScript literal into JSON.

    The literals differ from JSON in exactly two ways — single-quoted strings
    and bare object keys — so this converts those and nothing else.  Pulling in
    a JavaScript parser to read five constants would be theatre, but a bare
    regex over the whole blob would happily rewrite the apostrophe in
    ``"Porsche 911 RSR (991) '17"``, so the quote conversion walks the text
    and keeps track of whether it is inside a string.
    """
    out: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char == '"':
            end = index + 1
            while end < len(body) and body[end] != '"':
                end += 2 if body[end] == "\\" else 1
            out.append(body[index:end + 1])
            index = end + 1
        elif char == "'":
            end = index + 1
            chunk: list[str] = []
            while end < len(body) and body[end] != "'":
                if body[end] == "\\":
                    chunk.append(body[end + 1])
                    end += 2
                    continue
                chunk.append(body[end])
                end += 1
            out.append(json.dumps("".join(chunk)))
            index = end + 1
        else:
            out.append(char)
            index += 1
    return re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":',
                  "".join(out))


def _span(source: str, name: str, opener: str, closer: str) -> str:
    start = source.index(f"{name}=")
    open_at = source.index(opener, start)
    depth = 0
    for index in range(open_at, len(source)):
        if source[index] == opener:
            depth += 1
        elif source[index] == closer:
            depth -= 1
            if depth == 0:
                return source[open_at:index + 1]
    raise ValueError(f"{name} literal is not terminated")


def _literal(source: str, name: str) -> list:
    """The JavaScript array literal assigned to `name`."""
    return json.loads(_jsonish(_span(source, name, "[", "]")))


def _object_literal(source: str, name: str) -> dict:
    """The JavaScript object literal assigned to `name`."""
    return json.loads(_jsonish(_span(source, name, "{", "}")))


def _normalise(text: str) -> str:
    """Compare names without punctuation, accents or curly-quote drift."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


# ----------------------------------------------------------------- the cars

def build_cars(source: str) -> dict:
    html_cars = _literal(source, "CARS")
    specs = json.loads((DATA / "car_specs.json").read_text(encoding="utf-8"))

    by_name = {_normalise(name): name for name in specs}
    merged: dict[str, dict] = {}
    added: list[str] = []

    for car in html_cars:
        year = car.get("y") or ""
        label = f"{car['m']} {car['n']}" + (f" '{year}" if year else "")
        label = CAR_ALIASES.get(label, label)

        candidates = [label, f"{car['n']}" + (f" '{year}" if year else "")]
        canonical = next((by_name[_normalise(c)] for c in candidates
                          if _normalise(c) in by_name), None)
        if canonical is None:
            canonical = label
            added.append(label)

        spec = specs.get(canonical, {})
        # The HTML's class wins wherever it has one.  car_specs.json came from
        # a scrape that only ever knew Gr.1-4 and "Road Car": it files every
        # Gr.B rally car under Gr.4 and every Gr.X and VGT under Road Car.
        # Checked by hand against the fourteen cars whose names say "Gr.B" in
        # full — the HTML is right about all of them.
        category = (CATEGORIES.get(car.get("cat") or "")
                    or spec.get("category"))

        entry = {
            "category": category or "Road Car",
            "maker": car.get("m"),
            "year": year or None,
            "drivetrain": car.get("dt") or None,
            "aspiration": spec.get("aspiration") or car.get("asp") or None,
            "power_hp": spec.get("power_hp", car.get("hp")),
            "weight_kg": spec.get("weight_kg", car.get("kg")),
            "pp_rating": spec.get("pp_rating", car.get("pp")),
        }
        for extra in ("torque_kgfm", "torque_rpm"):
            if spec.get(extra) is not None:
                entry[extra] = spec[extra]
        merged[canonical] = entry

    # Cars the app knew about and the HTML did not.  Kept, with drivetrain
    # null rather than guessed — a missing layout is a missing layout.
    for name, spec in specs.items():
        if name in merged:
            continue
        merged[name] = {
            "category": spec.get("category") or "Road Car",
            "maker": None, "year": None, "drivetrain": None,
            "aspiration": spec.get("aspiration"),
            "power_hp": spec.get("power_hp"),
            "weight_kg": spec.get("weight_kg"),
            "pp_rating": spec.get("pp_rating"),
            **{k: spec[k] for k in ("torque_kgfm", "torque_rpm")
               if spec.get(k) is not None},
        }

    print(f"cars: {len(merged)} total, {len(added)} new from the HTML")
    return {"note": NOTE, "cars": dict(sorted(merged.items()))}


# ------------------------------------------------------------- the circuits

def build_circuits(source: str) -> dict:
    circuits = []
    unaliased = []
    for track in _literal(source, "TRACKS"):
        name = track["n"]
        aliases = CIRCUIT_ALIASES.get(name)
        if aliases is None:
            unaliased.append(name)
            aliases = []
        circuits.append({
            "name": name,
            "lengthKm": track["km"],
            "corners": track["c"],
            "gr3ReferenceLap": track["lap"],
            "downforce": track["df"],
            "mechanicalGrip": track["mech"],
            "wearSeverity": track["wear"],
            "wearAxle": track["axle"],
            "brakingSeverity": track["brk"],
            "pitLossPctOfLap": track["pit"],
            "kind": CIRCUIT_KINDS.get(track.get("t"), None),
            # Names an event may carry for this circuit. The circuit's own
            # name is always one of them.
            "aliases": sorted({name, *aliases}),
        })
    if unaliased:
        print(f"circuits: {len(unaliased)} with no alias entry: {unaliased}")
    print(f"circuits: {len(circuits)}")
    return {"note": NOTE, "circuits": circuits}


# ------------------------------------------------------------- the symptoms

def build_symptoms(source: str) -> dict:
    grouped: dict[str, list[str]] = {}
    for group, symptom in _literal(source, "SYMS"):
        grouped.setdefault(group, []).append(symptom)
    total = sum(len(v) for v in grouped.values())
    print(f"symptoms: {total} in {len(grouped)} groups")
    return {
        "note": NOTE + (" This is a controlled vocabulary shared with the "
                        "knowledge base; it is expected to grow."),
        "groups": [{"group": g, "symptoms": s} for g, s in grouped.items()],
    }


# ---------------------------------------------------------------- the ranges

def build_ranges(source: str) -> tuple[dict, dict]:
    library = _object_literal(source, "RANGELIB")
    seeds = []
    for car, record in library.items():
        seeds.append({
            "car": car,
            "measuredDate": record.get("date"),
            # RANGELIB existed only for ranges read off a car's own settings
            # screen, so every entry in it is verified by construction.
            "verified": True,
            "r": {k: list(v) for k, v in (record.get("r") or {}).items()},
        })
    print(f"range seeds: {len(seeds)}")

    presets: dict[str, dict[str, list]] = {"race": {}, "road": {}}
    per_car: list[str] = []
    steps: dict[str, float] = {}
    labels: dict[str, str] = {}
    units: dict[str, str] = {}
    for _group, rows in _literal(source, "RNG"):
        for key, label, unit, is_per_car, race, road, step in rows:
            if is_per_car:
                per_car.append(key)
            steps[key] = step
            labels[key] = label
            units[key] = unit or ""
            if race[0] is not None:
                presets["race"][key] = list(race)
            if road[0] is not None:
                presets["road"][key] = list(road)

    return (
        {"note": NOTE, "records": seeds},
        {
            "note": NOTE + (" These are GT7 typical windows, NOT this car's "
                            "limits. Anything built on them is estimated and "
                            "must say so."),
            "perCar": per_car,
            # GT7's slider granularity, which is what turns a value into
            # "N clicks from minimum".
            "steps": steps,
            "labels": labels,
            "units": units,
            "presets": presets,
        },
    )


def main() -> int:
    if not SOURCE.exists():
        print(f"{SOURCE} is missing — check the artifact in first.")
        return 1
    source = SOURCE.read_text(encoding="utf-8")

    seeds, presets = build_ranges(source)
    outputs = {
        "gt7_cars.json": build_cars(source),
        "gt7_circuits.json": build_circuits(source),
        "gt7_symptoms.json": build_symptoms(source),
        "gt7_range_seed.json": seeds,
        "gt7_range_presets.json": presets,
    }
    for name, payload in outputs.items():
        path = DATA / name
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
