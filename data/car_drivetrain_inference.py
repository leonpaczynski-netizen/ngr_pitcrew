"""Deterministic drivetrain inference for GT7 cars — the GENERATOR for
``data/car_drivetrains.json``.

``car_specs.json`` carries no drivetrain for any of the 579 cars, so the whole
engineering layer (balance tendency, RR/MR rear-stability, camber/toe) ran blind.
This module encodes GT7 manufacturer/model/engine-layout knowledge as ordered rules
and produces a car -> drivetrain mapping. It is the SEED: the emitted JSON is the
correctable source of truth (edit an entry there, or add an override here and
regenerate). Codes: FF, FR, MR, RR, 4WD ("" = genuinely unknown → callers fall back
to today's neutral behaviour, never a wrong guess-driven one).

Regenerate:  python -m data.car_drivetrain_inference
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_SPECS = Path(__file__).resolve().parent / "car_specs.json"
_OUT = Path(__file__).resolve().parent / "car_drivetrains.json"

# --- Exact-name overrides (highest priority): the driver's garage + cars where a
#     pattern would misfire. These are hand-confirmed. ---
_EXPLICIT: dict[str, str] = {
    "Porsche 911 RSR (991) '17": "MR",   # engine ahead of rear axle — mid, not RR
    "Ford Mustang 2015 American Racer": "FR",
}

# --- Model-keyword rules, checked IN ORDER (specific before general); first hit wins.
#     Matched case-insensitively against the full car name. ---
_MODEL_RULES: list[tuple[str, str]] = [
    # --- Highest-priority specific models (must beat the generic rules below) ---
    # Toyota AE86 is FR, but its name contains "corolla" (an FF trigger) — win first.
    (r"\b(ae86|corolla levin|sprinter trueno|hachiroku)\b", "FR"),
    # Porsche LMP/LMDh prototypes are mid-engine — must beat the Porsche RR default.
    (r"\b(963|919|917|956|962|rs spyder|908|905|787b|jaguar xjr)\b", "MR"),
    # Open-wheel / formula cars are rear-mid; classify as MR for balance reasoning.
    (r"\b(super formula|red bull x|f3500|f1500|formula|f1500t)\b", "MR"),
    (r"\bruf\b", "RR"),               # RUF is Porsche 911-based → rear-engine
    (r"\bbac mono\b|\bmono '\d\b", "MR"),
    (r"\bchaparral\b", "MR"),
    (r"\b(genesis)\b", "FR"),         # Genesis (Hyundai luxury) is FR / rear-drive
    # Mid-engine road & race
    (r"\bmclaren\b", "MR"),
    (r"\b(cayman|boxster|718|914)\b", "MR"),
    (r"\b(918|carrera gt)\b", "MR"),
    (r"\bnsx\b", "MR"),
    (r"\bmr2\b|\bmr-s\b|\bsera\b", "MR"),
    (r"\bs660\b", "MR"),
    (r"\b(elise|exige|evora|europa|esprit|340r|3-eleven)\b", "MR"),
    (r"\bford gt\b|\bgt40\b|\bgt lm\b|\bgt race car\b", "MR"),
    (r"\bde tomaso\b|\bpantera\b", "MR"),
    (r"\b(miura|countach|diablo|murci|aventador|essenza|sesto|reventon|veneno|huayra|zonda)\b",
     "4WD"),  # modern Lambo/Pagani → AWD; Miura handled below
    (r"\bmiura\b", "MR"),
    (r"\b(458|488|f8|296|360|f430|430 scuderia|348|f355|\b355\b|\b328\b|\b308\b|512 bb|"
     r"testarossa|enzo|laferrari|\bf40\b|\bf50\b|dino|250 lm|365 gt4/bb)\b", "MR"),
    (r"\bsf90\b", "4WD"),
    (r"\b(gtc4|\bff\b|purosangue)\b", "4WD"),   # Ferrari AWD
    (r"corvette (c8|stingray '2|z06 '2|e-ray)", "MR"),
    (r"\bcorvette\b", "FR"),
    (r"\brx-vision\b", "FR"),
    # Rear-engine
    (r"911 turbo", "4WD"),
    (r"\b911\b|\b930\b|\b964\b|\b993\b|\b997\b|\b991\b|\b992\b|\b356\b", "RR"),
    (r"\b(beetle|käfer)\b.*'\d|beetle -1|1200\b", "RR"),
    # AWD / 4WD
    (r"\bgt-?r\b", "4WD"),
    (r"\b(impreza|wrx|\bsti\b|22b)\b", "4WD"),
    (r"lancer evo|evolution|\bevo\b", "4WD"),
    (r"\bquattro\b|\bs1 pikes\b", "4WD"),
    (r"\br8\b", "MR"),                 # Audi R8 mid-engine (AWD, but handles mid)
    (r"\b(golf r|focus rs|gr yaris|gr corolla|celica gt-four|gt-four|22b|lancer evo)\b", "4WD"),
    (r"\b(rs 5|rs5|rs 4|rs4|rs 6|rs6|rs 3|rs3|\bs3\b|\bs4\b|\bs6\b)\b", "4WD"),
    (r"\b(veyron|chiron|bugatti)\b", "4WD"),
    (r"\bgr\.b rally\b|rally car", "4WD"),
    # Front-drive
    (r"\b(civic|integra|cr-x|crx|cr-z|\bfit\b|\bjazz\b|prelude|\bfn2\b|\bep3\b)\b", "FF"),
    (r"\b(golf|gti|scirocco|\bpolo\b|corrado|\bup!\b|lupo|beetle '1|beetle '2)\b", "FF"),
    (r"\b(megane|clio|twingo|\br\.s\.\b)\b", "FF"),
    (r"\br5 turbo\b|renault 5 turbo|\bclio v6\b", "MR"),
    (r"\b(mini|cooper)\b", "FF"),
    (r"\b(swift|\bxc\b)\b", "FF"),
    (r"\b(demio|mazda2|mazda3|mazdaspeed3|axela|familia)\b", "FF"),
    (r"\b(fiesta|focus|escort '9)\b", "FF"),
    (r"\b(207|208|205|206|306|308|\brcz\b)\b", "FF"),
    (r"\b(ibiza|leon|\bibiza\b)\b", "FF"),
    (r"\b(corolla|yaris|vitz|prius|aqua|auris|\bist\b|\bbb\b|passo)\b", "FF"),
    (r"\b(elantra|veloster|\bi30\b|\bi20\b)\b", "FF"),
    # Front-engine RWD sports/muscle
    (r"\b(mustang|shelby|cobra|gt350|gt500|boss 429|mach 1)\b", "FR"),
    (r"\b(camaro|firebird|trans am)\b", "FR"),
    (r"\b(challenger|charger|viper|dodge)\b", "FR"),
    (r"\b(supra|2000gt|2000 gt|gr86|gt86|toyota 86|\bbrz\b)\b", "FR"),
    (r"\b(rx-7|rx-8|rx7|rx8|savanna|fd3s|fc3s|sa22c)\b", "FR"),
    (r"\b(mx-5|miata|roadster|eunos)\b", "FR"),
    (r"\b(silvia|180sx|200sx|240sx|\bs13\b|\bs14\b|\bs15\b|sileighty|180 sx)\b", "FR"),
    (r"\b(fairlady|300zx|350z|370z|240z|260z|280z|z32|z33|z34|nissan z)\b", "FR"),
    (r"\b(skyline)\b", "FR"),
    (r"\bs2000\b|\bs800\b|\bs2k\b", "FR"),
    (r"\b(4c)\b", "MR"),               # Alfa 4C mid-engine
    (r"\bvalkyrie\b", "MR"),
    # Manufacturer-default RWD sports marques
    (r"\b(bmw|\bm2\b|\bm3\b|\bm4\b|\bm5\b|\bm6\b|\bz3\b|\bz4\b|\bz8\b|1 series m|2002)\b", "FR"),
    (r"\b(mercedes|amg|sls|slk|\bsl \b|\bsl-|\bclk\b|\bc63\b|\be63\b|190 e)\b", "FR"),
    (r"\b(lexus|\blc\b|\blfa\b|\brc\b|\bis \b|\bsc \b|\bgs \b|soarer)\b", "FR"),
    (r"\b(jaguar|e-type|f-type|xk|\bxj\b|d-type|c-type|xkr|xjr)\b", "FR"),
    (r"\b(aston|db\d|vantage|vanquish|\bdbs\b|one-77|db11|db9|dbr)\b", "FR"),
    (r"\b(maserati|granturismo|\bmc12\b|ghibli|quattroporte)\b", "MR"),  # MC12 mid; others FR-ish
    (r"\b(tvr|morgan|caterham|\bseven\b|noble|ginetta)\b", "FR"),
]

# --- Manufacturer defaults (first token), applied when no model rule matched. ---
_MANUFACTURER_DEFAULT: dict[str, str] = {
    "Subaru": "4WD", "Audi": "4WD", "Lamborghini": "4WD", "Bugatti": "4WD",
    "Mitsubishi": "4WD",
    "Honda": "FF", "Volkswagen": "FF", "Renault": "FF", "Peugeot": "FF",
    "MINI": "FF", "Mini": "FF", "Suzuki": "FF", "Fiat": "FF", "Citroën": "FF",
    "Ford": "FR", "Chevrolet": "FR", "Dodge": "FR", "Mazda": "FR", "BMW": "FR",
    "Mercedes-Benz": "FR", "AMG": "FR", "Lexus": "FR", "Jaguar": "FR",
    "Aston": "FR", "Maserati": "FR", "Nissan": "FR", "Toyota": "FR",
    "Alfa": "FR", "McLaren": "MR", "Ferrari": "MR", "Porsche": "RR",
    "Shelby": "FR", "Pontiac": "FR", "Plymouth": "FR", "Cadillac": "FR",
}


def infer_drivetrain(name: str, category: str = "") -> str:
    """Best-effort drivetrain code for one car. '' when genuinely unclear."""
    if name in _EXPLICIT:
        return _EXPLICIT[name]
    low = " " + name.lower() + " "
    for pat, dt in _MODEL_RULES:
        if re.search(pat, low):
            return dt
    man = name.split()[0] if name.split() else ""
    if man in _MANUFACTURER_DEFAULT:
        return _MANUFACTURER_DEFAULT[man]
    # Weak category hint: Gr.1 prototypes are overwhelmingly mid-engine.
    if (category or "").strip() == "Gr.1":
        return "MR"
    return ""


def generate() -> dict:
    specs = json.loads(_SPECS.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for name, spec in specs.items():
        dt = infer_drivetrain(name, (spec or {}).get("category", ""))
        if dt:
            out[name] = dt
    _OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8")
    return out


if __name__ == "__main__":
    from collections import Counter
    m = generate()
    specs = json.loads(_SPECS.read_text(encoding="utf-8"))
    dist = Counter(m.values())
    unknown = [k for k in specs if k not in m]
    print(f"classified {len(m)}/{len(specs)}  dist={dict(dist)}  unknown={len(unknown)}")
    for u in unknown[:40]:
        print("  UNKNOWN:", u)
