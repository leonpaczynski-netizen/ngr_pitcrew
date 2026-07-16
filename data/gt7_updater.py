"""Auto-update GT7 car list, track list, and BOP data from dg-edge.com.

Sources (all server-rendered HTML — no browser engine needed):
  Cars  — https://www.dg-edge.com/database/cars          (paginated, /page-N)
  Tracks— https://www.dg-edge.com/database/tracks        (index + detail pages)
  BOP   — https://www.dg-edge.com/database/bop           (per-class tables)

Requires: pip install requests beautifulsoup4
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Optional

try:
    import requests as _req
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    from bs4 import BeautifulSoup as _BS
    _BS4_OK = True
except ImportError:
    _BS4_OK = False

_SCRAPE_OK = _REQUESTS_OK and _BS4_OK


def _atomic_write_json(path, obj) -> None:
    """Write ``obj`` as pretty JSON to ``path`` atomically.

    The scraper runs on a background thread and writes several shared data files
    (car_specs.json / bop_data.json / …) that the running UI reads. A plain
    ``write_text`` that is interrupted mid-flush (app close, crash, disk full)
    leaves a truncated, unparseable file. Writing to a temp sibling then
    ``os.replace`` makes the swap atomic on the same filesystem, and a ``.bak``
    snapshot of the prior good file is kept — mirroring config_paths.save_config.
    """
    import os
    import shutil
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, indent=2, ensure_ascii=False)
    # Snapshot the prior good file first (copy, not move) so the target is never
    # momentarily absent, mirroring config_paths.save_config.
    if p.exists():
        try:
            shutil.copy2(p, p.with_name(p.name + ".bak"))
        except Exception:
            pass
    tmp = p.with_name(p.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.5",
}

_BASE          = "https://www.dg-edge.com"
_CARS_BASE     = f"{_BASE}/database/cars"
_TRACKS_BASE   = f"{_BASE}/database/tracks"
_BOP_BASE      = f"{_BASE}/database/bop"
_BOP_CLASSES   = ["GR.1", "GR.2", "GR.3", "GR.4"]
_BOP_FALLBACKS = ["1.67", "1.66", "1.65", "1.62", "1.61"]

# Maps dg-edge car-type badge text → our category key
_CAT_MAP = {
    "GR.1":          "Gr.1",
    "GR.2":          "Gr.2",
    "GR.3":          "Gr.3",
    "GR.4":          "Gr.4",
    "GR.B":          "Gr.4",   # Group B cars sit in Gr.4 bucket for now
    "Sport":         "Road Car",
    "Super Formula": "Gr.1",
    "N":             "Road Car",
}

# Badge values that are category labels, not car/track data — filter these out
_CATEGORY_BADGES: frozenset[str] = frozenset(_CAT_MAP.keys())


# ---------------------------------------------------------------------------
# Shared HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 8) -> Optional[str]:
    if not _REQUESTS_OK:
        return None
    try:
        r = _req.get(url, headers=_HEADERS, timeout=timeout)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Car scraper — dg-edge.com/database/cars  (paginated /page-N)
#
# Card HTML structure per car:
#   <div class="card">
#     <a class="card-img-top car-img">
#       <div class="badge car-type">GR.3</div>   ← category
#     </a>
#     <div class="card-body">
#       <h6>Manufacturer</h6>
#       <h4>Model name</h4>
#       [PP rating, power HP, weight kg, aspiration also in card text]
#     </div>
#   </div>
# ---------------------------------------------------------------------------

def _scrape_cars_page(page: int) -> list[dict]:
    """Return list of car dicts for one page. Empty list = no more pages."""
    url  = f"{_CARS_BASE}/page-{page}"
    html = _get(url)
    if not html or not _BS4_OK:
        return []
    soup = _BS(html, "html.parser")

    results: list[dict] = []
    for card in soup.find_all(class_="card"):
        badge = card.find(class_="car-type")
        body  = card.find(class_="card-body")
        if not body:
            continue
        h6 = body.find("h6")
        h4 = body.find("h4")
        if not h6 or not h4:
            continue
        make  = h6.get_text(strip=True)
        model = h4.get_text(strip=True)
        if not make or not model:
            continue

        # dg-edge h4 often includes the make already — avoid "Toyota Toyota Supra"
        if model.lower().startswith(make.lower()):
            full_name = model
        else:
            full_name = f"{make} {model}"

        raw_cat  = badge.get_text(strip=True) if badge else ""
        category = _CAT_MAP.get(raw_cat, "Road Car")

        # Find the detail page link (wraps the card image)
        detail_href: str | None = None
        link = card.find("a", href=re.compile(r"/database/cars/"))
        if link:
            detail_href = link.get("href")

        # Extract the numeric ID from detail_href for car_id_map
        # e.g. "/database/cars/toyota-ts050-hybrid-16/1430" → "1430"
        car_num_id: str | None = None
        if detail_href:
            id_m = re.search(r"/(\d+)$", detail_href)
            if id_m:
                car_num_id = id_m.group(1)

        # Extract quick specs directly from the card text (no detail page needed)
        card_text = card.get_text(separator=" ")
        pp_m     = re.search(r"\bPP\s+([\d.]+)", card_text)
        power_m  = re.search(r"(\d+)\s*(?:HP|BHP|hp|bhp)\b", card_text)
        weight_m = re.search(r"\b(\d{2,4})\s*kg\b", card_text, re.I)
        asp_m    = re.search(r"\b(NA|TC|SC|EV)\b", card_text)

        results.append({
            "full_name":   full_name,
            "make":        make,
            "category":    category,
            "detail_href": detail_href,
            "car_num_id":  car_num_id,
            "pp_rating":   float(pp_m.group(1))  if pp_m     else 0.0,
            "power_hp":    int(power_m.group(1))  if power_m  else 0,
            "weight_kg":   int(weight_m.group(1)) if weight_m else 0,
            "aspiration":  asp_m.group(1)         if asp_m    else "",
        })

    return results


def _scrape_car_specs(detail_href: str) -> dict:
    """Fetch a car detail page and extract all available spec fields."""
    html = _get(f"{_BASE}{detail_href}")
    if not html or not _BS4_OK:
        return {}
    soup = _BS(html, "html.parser")
    specs: dict = {}

    # dg-edge detail pages list specs in a <table> or <dl>/<dt>/<dd> pairs.
    text_blocks = soup.get_text(separator="\n")
    for line in text_blocks.splitlines():
        line = line.strip()
        low  = line.lower()
        if not line:
            continue

        if low.startswith("drivetrain") or low.startswith("drive"):
            val = line.split(":", 1)[-1].strip()
            if val and val != line:
                specs["drivetrain_raw"] = val

        elif low.startswith("gears") or low.startswith("transmission"):
            val = line.split(":", 1)[-1].strip()
            m = re.search(r"\d+", val)
            if m:
                specs["num_gears"] = int(m.group())

        elif "displacement" in low or "engine size" in low:
            m = re.search(r"(\d[\d,]+)\s*cc", line, re.I)
            if m:
                specs["displacement_cc"] = int(m.group(1).replace(",", ""))

        elif low.startswith("max. power") or low.startswith("max power") or low.startswith("power"):
            # Power HP/BHP value
            m_hp = re.search(r"(\d+)\s*(?:hp|bhp|ps|kw)", line, re.I)
            if m_hp:
                hp = int(m_hp.group(1))
                if "kw" in low:
                    hp = int(hp * 1.341)
                specs["power_hp"] = hp
            # RPM at peak power: "506 BHP / 4,600 rpm"
            m_rpm = re.search(r"(\d[\d,]+)\s*rpm", line, re.I)
            if m_rpm:
                specs["power_rpm"] = int(m_rpm.group(1).replace(",", ""))

        elif "torque" in low:
            # "86.8 kgfm / 3,000 rpm" or "860 Nm / 3000 rpm"
            m_kgfm = re.search(r"([\d.]+)\s*kgfm", line, re.I)
            if m_kgfm:
                specs["torque_kgfm"] = float(m_kgfm.group(1))
            else:
                # Convert Nm → kgfm if Nm is present (1 kgfm = 9.80665 Nm)
                m_nm = re.search(r"(\d+)\s*nm", line, re.I)
                if m_nm:
                    specs["torque_kgfm"] = round(int(m_nm.group(1)) / 9.80665, 1)
            m_rpm = re.search(r"(\d[\d,]+)\s*rpm", line, re.I)
            if m_rpm:
                specs["torque_rpm"] = int(m_rpm.group(1).replace(",", ""))

        elif low.startswith("weight") or low.startswith("kerb"):
            m = re.search(r"(\d+)\s*(?:kg|lb)", line, re.I)
            if m:
                kg = int(m.group(1))
                if "lb" in low:
                    kg = int(kg * 0.4536)
                specs["weight_kg"] = kg

        elif low.startswith("length"):
            m = re.search(r"(\d[\d,]+)\s*mm", line, re.I)
            if m:
                specs["length_mm"] = int(m.group(1).replace(",", ""))

        elif low.startswith("width"):
            m = re.search(r"(\d[\d,]+)\s*mm", line, re.I)
            if m:
                specs["width_mm"] = int(m.group(1).replace(",", ""))

        elif low.startswith("height"):
            m = re.search(r"(\d[\d,]+)\s*mm", line, re.I)
            if m:
                specs["height_mm"] = int(m.group(1).replace(",", ""))

    # Map drivetrain raw text to our standard codes
    if "drivetrain_raw" in specs:
        raw = specs.pop("drivetrain_raw").upper()
        for code in ("AWD", "4WD", "FR", "MR", "RR", "FF"):
            if code in raw:
                specs["drivetrain"] = code if code != "4WD" else "AWD"
                break

    return specs


def update_cars(
    extra_path: str = "data/gt7_extra.json",
    specs_path: str = "data/car_specs.json",
    id_map_path: str = "data/car_id_map.json",
    known_cars: Optional[set[str]] = None,
    progress_cb=None,
) -> tuple[bool, str]:
    """Scrape all car pages, add new cars to gt7_extra.json, save specs and car_id_map."""
    if not _SCRAPE_OK:
        return False, "Missing dependencies — run: pip install requests beautifulsoup4"

    all_scraped: list[dict] = []
    for pg in range(1, 30):
        page_cars = _scrape_cars_page(pg)
        if not page_cars:
            break
        all_scraped.extend(page_cars)

    if not all_scraped:
        return False, f"Could not load car data from {_CARS_BASE}"

    # Load existing extra + specs + id_map files
    p = Path(extra_path)
    extra: dict = {}
    if p.exists():
        try:
            extra = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    extra.setdefault("cars", {k: [] for k in ["Gr.1", "Gr.2", "Gr.3", "Gr.4", "Road Car", "Other"]})

    sp = Path(specs_path)
    car_specs: dict = {}
    if sp.exists():
        try:
            car_specs = json.loads(sp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    ip = Path(id_map_path)
    car_id_map: dict = {}
    if ip.exists():
        try:
            car_id_map = json.loads(ip.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    existing_lower: set[str] = set(known_cars or [])
    for cat_list in extra["cars"].values():
        for name in cat_list:
            existing_lower.add(name.lower())

    added = 0
    specs_updated = 0
    for idx, car in enumerate(all_scraped):
        full_name   = car["full_name"]
        category    = car["category"]
        detail_href = car["detail_href"]
        car_num_id  = car["car_num_id"]

        # Build car_id_map entry from dg-edge numeric ID
        if car_num_id:
            car_id_map[car_num_id] = full_name

        is_new = full_name.lower() not in existing_lower
        if is_new:
            extra["cars"].setdefault(category, [])
            extra["cars"][category].append(full_name)
            existing_lower.add(full_name.lower())
            added += 1

        # Always update quick specs from list page (PP, power, weight, aspiration, category)
        existing_spec = car_specs.get(full_name, {})
        quick = {k: v for k, v in {
            "category":   category,
            "pp_rating":  car["pp_rating"],
            "power_hp":   car["power_hp"],
            "weight_kg":  car["weight_kg"],
            "aspiration": car["aspiration"],
        }.items() if v}  # skip zero/empty values
        existing_spec.update(quick)
        car_specs[full_name] = existing_spec

        # Fetch detail page for richer specs (only when missing detail fields)
        needs_detail = is_new or not existing_spec.get("num_gears")
        if detail_href and needs_detail:
            if progress_cb and idx % 10 == 0:
                progress_cb(f"Fetching car specs ({idx + 1}/{len(all_scraped)})…")
            detail = _scrape_car_specs(detail_href)
            if detail:
                existing_spec.update(detail)
                car_specs[full_name] = existing_spec
                specs_updated += 1

    _atomic_write_json(p, extra)
    _atomic_write_json(sp, car_specs)
    _atomic_write_json(ip, car_id_map)
    return True, (
        f"Cars: {len(all_scraped)} on site, {added} new names added, "
        f"{specs_updated} detail spec records updated, "
        f"{len(car_id_map)} car ID mappings saved"
    )


# ---------------------------------------------------------------------------
# Track scraper — dg-edge.com/database/tracks
#
# Index page: <h5> for each venue, <a href="/database/tracks/{slug}/{id}">
# Detail page: first <select> contains layout options, e.g.:
#   "Alsace - Village"  →  normalise to "Alsace – Village"
#   "Alsace - Village Reverse" → "Alsace – Village (Reverse)"
# ---------------------------------------------------------------------------

def _normalise_track(name: str) -> str:
    """Convert dg-edge track name to our GT7 naming convention."""
    # Replace ASCII hyphen-dash separator " - " with em-dash " – "
    name = re.sub(r"\s+-\s+", " – ", name)
    # "X Reverse" at end → "X (Reverse)"
    name = re.sub(r"\s+Reverse$", " (Reverse)", name)
    return name.strip()


def _ascii_key(s: str) -> str:
    """Lower-case, strip accents, collapse spaces — for fuzzy dedup."""
    nfkd = unicodedata.normalize("NFKD", s)
    return re.sub(r"\s+", " ", "".join(c for c in nfkd if not unicodedata.combining(c))).lower().strip()


def _scrape_track_layouts(track_url: str) -> list[str]:
    """Fetch a track detail page and return normalised layout names."""
    html = _get(f"{_BASE}{track_url}")
    if not html or not _BS4_OK:
        return []
    soup = _BS(html, "html.parser")
    # First <select> has layout options; skip "All variants" sentinel
    sel = soup.find("select")
    if not sel:
        return []
    layouts: list[str] = []
    for opt in sel.find_all("option"):
        text = opt.get_text(strip=True)
        if not text or text.lower().startswith("all"):
            continue
        layouts.append(_normalise_track(text))
    return layouts


def update_tracks(
    extra_path: str = "data/gt7_extra.json",
    known_tracks: Optional[set[str]] = None,
    progress_cb=None,
) -> tuple[bool, str]:
    """Scrape all track layouts from dg-edge and add new ones to gt7_extra.json."""
    if not _SCRAPE_OK:
        return False, "Missing dependencies — run: pip install requests beautifulsoup4"

    html = _get(_TRACKS_BASE)
    if not html:
        return False, f"Could not reach {_TRACKS_BASE}"

    soup = _BS(html, "html.parser")
    track_links = [
        a["href"] for a in soup.find_all("a", href=True)
        if re.match(r"/database/tracks/[^/]+/\d+$", a["href"])
    ]
    seen_links: set[str] = set()
    unique_links = [x for x in track_links if not (x in seen_links or seen_links.add(x))]

    if not unique_links:
        return False, "No track links found on index page"

    p = Path(extra_path)
    extra: dict = {}
    if p.exists():
        try:
            extra = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    extra.setdefault("tracks", [])

    # Drop any bogus entries that are car-category badge strings
    extra["tracks"] = [
        t for t in extra["tracks"]
        if t not in _CATEGORY_BADGES and len(t) > 5
    ]

    existing_keys: set[str] = set()
    if known_tracks:
        for t in known_tracks:
            existing_keys.add(_ascii_key(t))
    for t in extra["tracks"]:
        existing_keys.add(_ascii_key(t))

    all_found = 0
    added     = 0
    for idx, link in enumerate(unique_links):
        if progress_cb and idx % 5 == 0:
            progress_cb(f"Fetching track layouts ({idx + 1}/{len(unique_links)})…")
        layouts = _scrape_track_layouts(link)
        for layout in layouts:
            # Skip anything that matches a category badge (scraper artifact)
            if layout in _CATEGORY_BADGES or len(layout) <= 3:
                continue
            all_found += 1
            if _ascii_key(layout) not in existing_keys:
                extra["tracks"].append(layout)
                existing_keys.add(_ascii_key(layout))
                added += 1

    _atomic_write_json(p, extra)
    return True, (
        f"Tracks: {len(unique_links)} circuits, {all_found} layouts found, "
        f"{added} new added to gt7_extra.json"
    )


# ---------------------------------------------------------------------------
# BOP scraper — dg-edge.com/database/bop
#
# Per-class page table (2 header rows, then data):
#   col 0: rank/icon   col 1: car name   col 6: current HP   col 12: current KG
# ---------------------------------------------------------------------------

def _latest_bop_version() -> str:
    html = _get(_BOP_BASE)
    if html:
        versions: set[str] = set()
        for m in re.finditer(r"/database/bop/[^\"/]+/(\d+\.\d+)", html):
            versions.add(m.group(1))
        if versions:
            return max(versions, key=lambda v: tuple(int(x) for x in v.split(".")))
    return _BOP_FALLBACKS[0]


def _scrape_bop_class(cls: str, latest: str) -> Optional[dict[str, dict]]:
    _NAME_COL, _POWER_COL, _WEIGHT_COL = 1, 6, 12
    tried: set[str] = set()
    for ver in [latest] + _BOP_FALLBACKS:
        if ver in tried:
            continue
        tried.add(ver)
        html = _get(f"{_BOP_BASE}/{cls}/{ver}")
        if not html or not _BS4_OK:
            continue
        soup  = _BS(html, "html.parser")
        table = soup.find("table")
        if not table:
            continue
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue
        result: dict[str, dict] = {}
        for row in rows[2:]:    # skip both header rows
            cells = row.find_all(["td", "th"])
            if len(cells) <= _WEIGHT_COL:
                continue
            name = cells[_NAME_COL].get_text(separator=" ", strip=True)
            name = re.sub(r" {2,}", " ", name).strip()
            if not name or len(name) < 3:
                continue
            try:
                power  = int(re.sub(r"[^\d]", "", cells[_POWER_COL].get_text()))
                weight = int(re.sub(r"[^\d]", "", cells[_WEIGHT_COL].get_text()))
                if power > 0 and weight > 0:
                    result[name] = {"weight_kg": weight, "power_hp": power}
            except (ValueError, IndexError):
                continue
        if result:
            return result
    return None


def update_bop(bop_path: str = "data/bop_data.json") -> tuple[bool, str]:
    if not _SCRAPE_OK:
        return False, "Missing dependencies — run: pip install requests beautifulsoup4"

    version       = _latest_bop_version()
    cars_by_class: dict[str, dict] = {}
    failed: list[str] = []

    for cls in _BOP_CLASSES:
        data = _scrape_bop_class(cls, version)
        if data:
            cars_by_class[cls] = data
        else:
            failed.append(cls)

    if not cars_by_class:
        return False, f"BOP scrape failed — no class data from {_BOP_BASE}"

    p = Path(bop_path)
    try:
        existing = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except json.JSONDecodeError:
        existing = {}

    existing.update({
        "last_updated": time.strftime("%Y-%m-%d"),
        "bop_version":  version,
        "note": "Auto-updated from dg-edge.com. Click 'Reload BOP' in Car Setup to apply.",
        "cars": cars_by_class,
    })
    _atomic_write_json(p, existing)

    total = sum(len(v) for v in cars_by_class.values())
    msg   = f"BOP v{version}: {total} cars across {len(cars_by_class)} class(es)"
    if failed:
        msg += f"  (no data for: {', '.join(failed)})"
    return True, msg


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------

def update_all(
    bop_path:    str = "data/bop_data.json",
    extra_path:  str = "data/gt7_extra.json",
    specs_path:  str = "data/car_specs.json",
    id_map_path: str = "data/car_id_map.json",
    progress_cb=None,
) -> tuple[bool, str]:
    """Run all three scrapers. Returns (any_success, multi-line summary)."""
    # Load the current hardcoded GT7 lists for dedup comparison
    try:
        from ui.gt7_data import GT7_CARS, GT7_TRACKS
        known_cars   = {c.lower() for c in GT7_CARS}
        known_tracks = set(GT7_TRACKS)
    except Exception:
        known_cars   = set()
        known_tracks = set()

    lines:  list[str] = []
    any_ok: bool      = False

    if progress_cb:
        progress_cb("Fetching BOP data from dg-edge.com...")
    ok, msg = update_bop(bop_path)
    lines.append(f"{'OK' if ok else 'FAIL'} BOP: {msg}")
    any_ok = any_ok or ok

    if progress_cb:
        progress_cb("Fetching car list and specs from dg-edge.com...")
    ok, msg = update_cars(
        extra_path,
        specs_path=specs_path,
        id_map_path=id_map_path,
        known_cars=known_cars,
        progress_cb=progress_cb,
    )
    lines.append(f"{'OK' if ok else 'FAIL'} Cars: {msg}")
    any_ok = any_ok or ok

    if progress_cb:
        progress_cb("Fetching track layouts from dg-edge.com...")
    ok, msg = update_tracks(extra_path, known_tracks=known_tracks, progress_cb=progress_cb)
    lines.append(f"{'OK' if ok else 'FAIL'} Tracks: {msg}")
    any_ok = any_ok or ok

    return any_ok, "\n".join(lines)
