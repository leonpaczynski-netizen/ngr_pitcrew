# Track Library Schema Reference

> Version: 1.0.0 (Group 17U, 2026-06-26)

The Track Library is a structured, versioned registry of per-track and per-layout data that replaces ad hoc file discovery from the flat `data/track_seed_maps/` directory.

---

## Directory Structure

```
data/track_library/
  index.json                                     ← registry root
  tracks/
    <track_id>/
      track.json                                 ← track metadata
      layouts/
        <layout_id>/
          manifest.json                          ← layout manifest + availability
          semantic_model.json                    ← corners, sectors, complexes
          validation_rules.json                  ← acceptance thresholds
          source_manifest.json                   ← data provenance
          geometry.seed_map.json                 ← coordinate geometry (optional)
          accepted_models/                       ← accepted model snapshots
          calibration_runs/                      ← calibration run archives
```

**Layout directory naming:** uses `layout_id` directly (e.g., `daytona_international_speedway__road_course`). The layout_id already encodes the track prefix; there is no additional wrapping.

---

## Schema Versions

| File | Schema string |
|------|---------------|
| `index.json` | `track_library_index_v1` |
| `track.json` | `track_metadata_v1` |
| `manifest.json` | `track_layout_manifest_v1` |
| `semantic_model.json` | `track_semantic_model_v1` |
| `validation_rules.json` | `validation_rules_v1` |
| `source_manifest.json` | `source_manifest_v1` |
| `geometry.seed_map.json` | `seed_coordinate_map_v1` (from `data/track_seed_coordinate_map.py`) |

Every JSON file **must** declare `"schema": "<version_string>"`. Load functions in `data/track_library.py` validate the schema field and return `None` for mismatches.

---

## File Schemas

### `index.json` — `track_library_index_v1`

```json
{
  "schema": "track_library_index_v1",
  "library_version": "1.0.0",
  "tracks": ["daytona_international_speedway"],
  "created_at": "2026-06-26",
  "updated_at": "2026-06-26"
}
```

- `tracks`: list of `track_id` strings that have a `tracks/<track_id>/` subdirectory.

---

### `track.json` — `track_metadata_v1`

```json
{
  "schema": "track_metadata_v1",
  "track_id": "daytona_international_speedway",
  "display_name": "Daytona International Speedway",
  "country": "US",
  "gt7_track_code": "daytona",
  "layouts": ["daytona_international_speedway__road_course"]
}
```

- `gt7_track_code`: the code used in GT7 internal data (optional, used for BOP lookup).
- `layouts`: list of `layout_id` strings that have layout subdirectories.

---

### `manifest.json` — `track_layout_manifest_v1`

```json
{
  "schema": "track_layout_manifest_v1",
  "track_id": "daytona_international_speedway",
  "layout_id": "daytona_international_speedway__road_course",
  "display_name": "Daytona Road Course",
  "lap_length_m": 5729.0,
  "reverse_layout": false,
  "assets": {
    "semantic_model": "semantic_model.json",
    "seed_geometry": "geometry.seed_map.json",
    "validation_rules": "validation_rules.json",
    "source_manifest": "source_manifest.json"
  },
  "availability": {
    "metadata": true,
    "sectors": true,
    "corner_windows": true,
    "corner_complexes": true,
    "seed_geometry": false,
    "width_model": false,
    "accepted_model": false,
    "calibration_runs": false
  },
  "source": "estimated",
  "confidence": "low"
}
```

- `availability.seed_geometry`: **must be `false`** until `geometry.seed_map.json` is physically present.
- `source`: `"estimated"` / `"measured"` / `"official"`.
- `confidence`: `"low"` / `"medium"` / `"high"`.

---

### `semantic_model.json` — `track_semantic_model_v1`

```json
{
  "schema": "track_semantic_model_v1",
  "track_id": "...",
  "layout_id": "...",
  "corners": [
    {
      "corner_id": "T1",
      "display_name": "Turn 1",
      "apex_progress_pct": 8.2,
      "entry_progress_pct": 6.0,
      "exit_progress_pct": 11.0,
      "direction": "right",
      "source": "estimated",
      "confidence": "low"
    }
  ],
  "sectors": [
    {
      "sector_id": "S1",
      "display_name": "Sector 1",
      "start_progress_pct": 0.0,
      "end_progress_pct": 33.0
    }
  ],
  "complexes": [
    {
      "complex_id": "BusStop",
      "display_name": "Bus Stop Chicane",
      "coaching_name": "Bus Stop",
      "member_corner_ids": ["T1", "T2"]
    }
  ],
  "notes": ""
}
```

**Separation principle:** The semantic model (what the corners are, what the sectors mean) is always separate from the geometry (where they are in coordinate space). The geometry belongs in `geometry.seed_map.json`.

---

### `validation_rules.json` — `validation_rules_v1`

```json
{
  "schema": "validation_rules_v1",
  "track_id": "...",
  "layout_id": "...",
  "acceptance": {
    "max_lap_delta_pct": 5.0,
    "max_mean_geometry_error_m": 15.0,
    "max_corner_apex_delta_pct": 5.0,
    "require_seed_geometry": false,
    "require_corner_windows": true,
    "require_sectors": true
  },
  "warnings": {
    "lap_delta_pct": 2.0,
    "geometry_error_m": 5.0
  }
}
```

- `require_seed_geometry`: set to `false` until the geometry file exists. Setting to `true` makes acceptance impossible without a coordinate map.
- Thresholds override any hardcoded constants in the alignment engine when this file is present.

---

### `source_manifest.json` — `source_manifest_v1`

```json
{
  "schema": "source_manifest_v1",
  "track_id": "...",
  "layout_id": "...",
  "sources": [
    {
      "name": "Track layout knowledge / estimated from circuit maps",
      "url": "",
      "retrieved_at": "2026-06-26",
      "notes": "..."
    }
  ],
  "fields_estimated": ["corner_windows", "sector_boundaries", "lap_length_m"],
  "fields_verified": ["T1_apex_at_8.2pct"],
  "notes": "...",
  "last_reviewed_at": "2026-06-26"
}
```

---

### `geometry.seed_map.json` — `seed_coordinate_map_v1`

This file uses the same schema as the legacy `data/track_seed_maps/` files. It is created by `export_seed_coordinate_map_json()` from `data/track_seed_coordinate_map.py`.

```json
{
  "schema": "seed_coordinate_map_v1",
  "track_location_id": "...",
  "layout_id": "...",
  "source": "telemetry_capture",
  "confidence": "high",
  "lap_length_m": 5729.0,
  "start_finish_station_m": 0.0,
  "has_z_coordinates": false,
  "has_corner_markers": true,
  "has_sector_markers": true,
  "has_width_corridor": false,
  "notes": "",
  "stations": [
    {"station_m": 0.0, "progress_pct": 0.0, "x": 0.0, "y": 0.0, "z": 0.0}
  ]
}
```

**Important:** When this file is added to the library, also update `manifest.json → availability.seed_geometry` to `true`.

---

## Python API

All functions are in `data/track_library.py`. Every function accepts an optional `base_dir` parameter for testing with temporary directories.

```python
from data.track_library import (
    load_track_library_index,          # → TrackLibraryIndex | None
    load_track_metadata,               # (track_id) → TrackMetadata | None
    resolve_track_layout_manifest,     # (track_id, layout_id) → TrackLayoutManifest | None
    load_track_semantic_model,         # (track_id, layout_id) → TrackSemanticModel | None
    load_validation_rules,             # (track_id, layout_id) → ValidationRules | None
    load_source_manifest,              # (track_id, layout_id) → SourceManifest | None
    load_seed_coordinate_map_from_library,  # (track_id, layout_id) → SeedCoordinateMap | None
    resolve_seed_coordinate_map,       # (track_id, layout_id) → (SeedCoordinateMap|None, str)
    audit_track_library_layout,        # (track_id, layout_id) → TrackLibraryAuditResult
)
```

### `resolve_seed_coordinate_map()`

Library-first resolver:
1. Try `geometry.seed_map.json` in the library layout directory → returns `(map, "track_library")`
2. Fall back to `data/track_seed_maps/<track_id>__<layout_id>.seed_map.json` → `(map, "legacy_fallback")`
3. Neither found → `(None, "none")`

### `audit_track_library_layout()`

Returns a `TrackLibraryAuditResult` with:
- `library_available`: `True` if `index.json` loads
- `manifest_loaded`, `semantic_model_loaded`, `validation_rules_loaded`: per-asset flags
- `seed_geometry_in_library`: `True` only if `geometry.seed_map.json` exists and loads
- `seed_coordinate_source`: `"track_library"` / `"legacy_fallback"` / `"none"`
- `warnings`: list of string warnings (e.g., "track_id not in library index")

---

## Integration Points

| Integration | What changes |
|-------------|-------------|
| `data/track_intelligence.py` `audit_layout_seed()` | Calls `audit_track_library_layout()` + `resolve_seed_coordinate_map()` when IDs given; falls back gracefully. `SeedAuditResult.seed_source`, `.library_manifest_loaded`, `.validation_rules_loaded` populated. |
| `ui/track_model_alignment_vm.py` `format_alignment_summary()` | Returns `"seed_source"` key: `"Track library"` / `"Legacy fallback"` / `"Unavailable"` / `"—"`. |
| `ui/dashboard.py` `_tm_refresh_alignment_panel()` | Uses `resolve_seed_coordinate_map()` (library-first) instead of direct legacy call. Displays "Seed source" panel row. |

---

## Adding a New Track

1. Create `data/track_library/tracks/<track_id>/track.json` with `track_metadata_v1` schema.
2. Add `<track_id>` to `tracks` list in `index.json` and update `updated_at`.
3. Create layout directory: `tracks/<track_id>/layouts/<layout_id>/`.
4. Create `manifest.json` — set all `availability` flags to `false` initially.
5. Add `semantic_model.json` (corners/sectors from track knowledge) — set `sectors: true` and `corner_windows: true` in availability when added.
6. Add `validation_rules.json` with per-track thresholds.
7. Add `source_manifest.json` documenting data provenance.
8. When coordinate geometry is available: add `geometry.seed_map.json` and set `availability.seed_geometry: true`.

---

## Backward Compatibility

The legacy `data/track_seed_maps/` directory continues to work unchanged. `resolve_seed_coordinate_map()` falls back to it automatically. Existing code that calls `load_seed_coordinate_map()` directly from `data/track_seed_coordinate_map.py` continues to work without modification.

To migrate a legacy seed map to the library:
1. Move/copy the file to the appropriate `geometry.seed_map.json` location.
2. Set `availability.seed_geometry: true` in `manifest.json`.
3. The legacy file can remain in place; the library version takes priority.
