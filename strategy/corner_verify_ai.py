"""AI-assisted corner position verification for track modelling."""
from __future__ import annotations

import json as _json
from typing import Optional


def verify_corners_with_ai(
    peaks: list[tuple[float, float, bool]],
    seed_windows: list[tuple[str, float, float]],
    speed_profile: list[tuple[float, float]],
    api_key: str,
    track_name: str = "",
) -> tuple[Optional[dict[str, dict]], str]:
    """Send curvature peaks and seed windows to Claude for corner assignment.

    Args:
        peaks: list of (progress_pct 0-100, curvature rad/m, is_seeded bool)
        seed_windows: list of (corner_id, start_pct, end_pct)
        speed_profile: list of (progress_pct, speed_kph) — up to 200 points
        api_key: Anthropic API key
        track_name: optional track name for prompt context

    Returns:
        (result_dict, "") on success, or (None, reason_string) on any failure.
        Caller should retain greedy assignments when None is returned.
    """
    print(f"[CornerVerify] Sending {len(peaks)} peaks, {len(seed_windows)} seed windows, {len(speed_profile)} speed pts")

    try:
        from strategy._ai_client import call_api
    except ImportError:
        reason = "No API key configured"
        print(f"[CornerVerify] Failed: {reason}")
        return (None, reason)

    if not peaks or not seed_windows or not api_key:
        reason = "No API key configured"
        print(f"[CornerVerify] Failed: {reason}")
        return (None, reason)

    # Build compact payload
    peaks_text = "\n".join(
        f"  progress={p:.1f}% curvature={c:.4f}{'(seeded)' if s else ''}"
        for p, c, s in peaks
    )
    windows_text = "\n".join(
        f"  {cid}: {start:.1f}%–{end:.1f}%"
        for cid, start, end in seed_windows
    )
    # Sample speed profile at every 10th point to keep tokens low
    sampled_speed = speed_profile[::10] if len(speed_profile) > 20 else speed_profile
    speed_text = ", ".join(f"{p:.0f}%:{s:.0f}kph" for p, s in sampled_speed)

    track_ctx = f" for {track_name}" if track_name else ""
    prompt = (
        f"You are a motorsport track analyst. Assign curvature peaks to corner IDs{track_ctx}.\n\n"
        f"SEED CORNER WINDOWS (expected position ranges for each corner):\n{windows_text}\n\n"
        f"DETECTED CURVATURE PEAKS (found in telemetry):\n{peaks_text}\n\n"
        f"SPEED PROFILE (progress%:speed):\n{speed_text}\n\n"
        f"For each corner ID, assign the best matching peak. "
        f"If no peak falls in a window, use the closest peak outside it. "
        f"Respond ONLY with valid JSON: "
        f'{{"T1":{{"progress_pct":34.2,"confidence":0.91}},"T2":...}}'
        f"\nInclude every corner ID from the seed windows. No other text."
    )

    try:
        response = call_api(
            prompt=prompt,
            api_key=api_key,
            max_tokens=512,
            feature="AI Corner Verify",
            track=track_name,
        )
    except Exception as exc:
        reason = f"Network error: {str(exc)}"
        print(f"[CornerVerify] Failed: {reason}")
        return (None, reason)

    try:
        # Strip markdown code fences if present
        text = response.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = _json.loads(text.strip())
        # Validate structure
        validated = {}
        for cid, val in result.items():
            if isinstance(val, dict) and "progress_pct" in val:
                validated[cid] = {
                    "progress_pct": float(val["progress_pct"]),
                    "confidence": float(val.get("confidence", 0.5)),
                }
        if not validated:
            reason = "AI response parse error"
            print(f"[CornerVerify] Failed: {reason}")
            return (None, reason)
        result_dict = validated
        print(f"[CornerVerify] Result: {result_dict}")
        return (result_dict, "")
    except Exception:
        reason = "AI response parse error"
        print(f"[CornerVerify] Failed: {reason}")
        return (None, reason)
