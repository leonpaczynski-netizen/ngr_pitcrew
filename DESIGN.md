# Design — Marked Set

<!-- impeccable:design-schema 1 -->

Recorded from the built world (`pitcrew/ui/`), not from intention.
Platform: PyQt6 desktop. There is no CSS, no viewport, and no responsive
breakpoint system — layout adapts through Qt layouts and stretch factors.

## Thesis

A set of tyres arrives blank and black, and the crew marks it in registers
that are never confused: **moulded stencil** is manufacturer fact,
the **coloured band** is classification read at a glance, and **grease pencil**
is the crew's own hand. Pit Crew carries provenance the same way, so measured,
derived and declared never look alike.

It refuses the category's two defaults: the glowing-gauge telemetry dashboard
with radial dials and a lime accent, and its opposite, the flat grey admin
panel with a data table.

## The registers

This is the system. Everything else serves it.

| Register | Colour | Means | Where |
|---|---|---|---|
| Stencil | `#E8E4DC` warm white, mono | **Measured** — came off the telemetry stream | Lap times, deltas, fuel used |
| Crayon | `#FF6B1A` tyre-marker orange | **Declared** — the driver entered it | Every editor, compound tags, wear gauge |
| Derived | `#B08BD8` timing-screen purple | **Derived** — the app worked it out | Box-in call, modelled stint, assumed inputs |
| Chalk | `#7FC7D9` | Provisional annotation, hints, parse results | Status lines |
| Struck | `#6B6459` | Removed from the count, disabled, placeholder | Excluded laps, empty fields |

**There were three registers and there should always have been four.** Measured
had an ink and declared had an ink, so everything the app *computed* borrowed
one — and borrowed badly. Assumed strategy inputs took struck, colliding with
disabled and excluded; `"Box in 3"`, the highest-consequence number this
product emits, took crayon, the ink that means the driver typed it himself.
Purple is not a fourth colour picked to be different: on a timing screen it is
already the sport's mark for a figure the system worked out rather than one
somebody set.

**The registers are asserted against rendered pixels, not against the
stylesheet.** For the whole life of the app before this, `QWidget { color }`
matched every editor subclass and beat `QPalette.Text`, so every value the
driver typed rendered in the ink for one that came off the stream — declared
and measured were pixel-identical everywhere, four docstrings said otherwise,
and every test passed. `tests/test_registers.py` paints a widget and reads the
colour back, because a cascade bug cannot be caught by reading the cascade.

**Placeholders are struck, never crayon.** Qt has no `::placeholder` selector,
so `theme.apply()` sets `QPalette.PlaceholderText` and the stylesheet
deliberately sets no `color` on editors. A stylesheet colour would beat the
palette role and make an empty field render as a value the driver declared.

**Shipped reference data is prose, not a register.** GT7's own car and circuit
tables, and the knowledge base's Quick Reference, were neither measured here
nor declared here. Setting them in stencil white would make them look like
they came off the stream. They are set as `BodyLabel` at `STENCIL_DIM` — a
sentence, not a value. The registers apply to values; nothing else is
admitted to them.

## Ground and material

Warm carbon, not blue-black — rubber under work lamps is brown-black. The
scene chose this: the app sits on the upper monitor at the rig, read with the
VR headset just pushed up.

| Token | Value | Use |
|---|---|---|
| `RUBBER` | `#14120F` | Page ground |
| `RUBBER_DEEP` | `#0C0B09` | Wells: editors, the rack, the nav rail |
| `SHOULDER` | `#1E1B17` | Plate faces, matte |
| `SHOULDER_HI` | `#282420` | Hover |
| `TREAD` | `#38332B` | Moulded groove: borders, rules |
| `TREAD_LIGHT` | `#4A443A` | Secondary button edge |

No gradients, no glass, no blur, no rounded corners, no drop shadows. Depth
comes from value steps between grounds and a 1px groove.

## Compound bands

Real racing colours, and already the product's data (`RH`/`RM`/`RS`/`IM`/`HW`
plus the Sports bronze and Comfort cool-grey families). A band runs the full
row height down the left edge of a lap, so tagging a session paints the rack
and the stint structure becomes visible without reading a number.

**Colour is never the only channel.** Every band carries its two-letter code,
stencilled in ink chosen by the band's own luminance (`theme.band_ink`). An
excluded lap's band is desaturated toward grey — it keeps its identity and
loses its voice.

## Lettering

| Role | Face | Why |
|---|---|---|
| Labels, headings, buttons | **Bahnschrift Condensed**, caps, tracked +8-14% | Bahnschrift is DIN 1451 — the German industrial signage standard that technical plates and moulded sidewall codes are lettered in. The correct letter for this world, not the convenient one. |
| All measurement | **Cascadia Mono** (fallback Consolas) | It *is* measurement, not a costume for "technical". |
| Prose | Bahnschrift regular | |

Qt style sheets carry no letter-spacing or text-transform, so tracking and
capitalisation are set on `QFont` in `theme.stencil_font()`.

Scale runs larger than a desk app's default (title 30px, body 15px, data
15px, lap time 23px) because it is read from the driving position.

## Components

- **`Plate`** — a bolted panel whose stencilled label is struck through its own
  top edge. The drawn border starts 9px below the widget top so the label sits
  centred on the rule with its full cap height inside; straddling y=0 clips the
  letters.
- **`CompoundBand`** — the painted ring. Setting a code wipes the new colour
  down over the old in 180ms `OutCubic`. This is the one authored motion in the
  build; there are no other transitions.
- **`StrikeRow`** — a rack row that draws a real line through itself when
  excluded. The strike stops before the controls: a line through a combo box
  reads as "disabled", and an excluded lap can still be re-counted and still
  needs its compound.
- **`SpecLine`** — session totals as one stencilled spec run, labels small and
  inline. Deliberately not a row of stat cards: the big-number-and-label grid
  is the template every dashboard ships.
- **`Field`** — stencilled label, crayon editor. Spinner arrows are removed and
  a 34px minimum height is pinned, because a field sharing a grid row with a
  taller neighbour was collapsing to a sliver. Hints do not wrap — a wrapped
  hint reports a one-line height and overruns the field below it.
- **`MarkButton`** — lettered on a plate. Primary is crayon-filled; the run
  ends on one. `set_primary()` re-applies the fill, so a row of buttons
  standing for a choice can show which one is selected — Qt's `setDown` does
  not survive the next repaint, and a selection nobody can see is no
  selection.

## The rail

Eight screens, grouped by the job they belong to rather than listed. Two loops
run through this app and they are not the same work — **Prepare** and **Learn**
make the car faster; **Race day** is used under pressure — and flat, they read
as eight peers in an order that put Engineer, the last step of the first loop,
after Race. Each item carries a one-line state the store already knows
(`11 laps`, `no plan`, `measured`), so the rail says where the work stands
rather than only where it goes.

## Screens

**Event** (`event_screen.py`) — two columns. Left is the event as raced;
right is the sheet in the car: a paste box that populates the form, with the
full 23-key form staying visible as the editor. Every value on this screen is
declared, so the screen carries no stencil white at all — which is what makes
stencil mean something on Practice. A setting nobody entered renders its dash
struck rather than crayon: absent is not declared, and the spin box's *line
edit* has to be told so, because it keeps its own resolved palette once the
spin box's has been set.

**Car** (`car_screen.py`) — the range rack. Its subject is not the numbers but
the difference between numbers read off the car's own settings screen and a
typical window standing in for them, because that difference decides whether a
returned sheet can be entered without clamping. Measured is crayon; the
checkbox that claims it fills with crayon too.

**Practice** (`practice_screen.py`) — the rack. One row per lap, band on the
left. He is in a headset while driving and cannot see this at all, so nothing
is designed to be read at speed; it is the surface he returns to between
stints to mark up, strike out, and export.

**Race Engineer** (`engineer_screen.py`) — split along the line the whole
feature is built on: left is perception, all of it crayon because he declared
it; right is the assembled prompt, presented as a block rather than a form
because it is the thing being sent, not something to fill in. A plate above the
form says what the app is filling in, so the division is visible before
anything is generated.

**Reference** (`reference_screen.py`) — the knowledge base's own tables,
verbatim and read-only. No controls, because there is nothing here to act on.

Layout note, learned twice: a `Field`'s hint does not wrap and a `QComboBox`
sizes to its widest item, so a long hint or a sentence-length option sets a
wide minimum for its whole pane and silently clips every label in the column.
Hints stay short, and combos holding sentences get
`AdjustToMinimumContentsLengthWithIcon` with the popup sized separately.

## What this world refuses

Sparklines and progress rings; radial gauges; card grids of icon-plus-heading;
kickers above headings; gradient text; glass; coloured left borders; unicode
glyphs or emoji standing in for icons (there are no icons at all — the band and
the strike carry the work); monospace anywhere it is not measurement.
