

def test_every_declared_opener_still_exists_in_its_module():
    """**A line that drifts from its module is a clip that stops matching.**

    `spoken_openers()` quotes lines the synthetic-state decomposition cannot
    reach - the temperature family, the run-in, the colour tier and the
    push-to-talk acknowledgement. Quoting them is the only way to get them
    rendered, and the cost of quoting is that an edit in `calls.py` can leave
    the manifest describing a line nobody says any more. Then the real line
    misses the pack and is live-synthesised, which is exactly the failure the
    pack exists to prevent - and it fails silently, as a pause before the
    engineer speaks.

    Measured on 22 Aug 2026 before the openers were declared: fourteen of the
    sixteen lines the engineer can say were missing from the pack.
    """
    from pathlib import Path

    from pitcrew.engineer.phrase_manifest import spoken_openers

    root = Path(__file__).resolve().parents[1]
    source = "".join(
        (root / name).read_text(encoding="utf-8")
        for name in ("race/calls.py", "race/colour.py",
                     "race/brief.py", "engineer/intents.py"))
    # **Whitespace-insensitive**, because a long line is written in the source
    # as adjacent string literals across two lines and would never match
    # literally. Comparing with all whitespace removed finds it wherever the
    # formatter chose to break it.
    # Adjacent string literals leave a `""` where they join once the
    # whitespace between them is gone; dropping it splices them back.
    flat = "".join(source.split()).replace('""', "")
    stray = [line for line in spoken_openers()
             if "".join(line.split()) not in flat]
    assert not stray, (
        "these lines are declared for rendering but no module says them any "
        f"more, so the real wording will fall through to synthesis: {stray}")
