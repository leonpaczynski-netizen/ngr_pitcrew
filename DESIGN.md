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
with radial dials, and its opposite, the flat grey admin panel with a data
table.

**On the lime.** An earlier version of this file refused a lime accent
outright, as shorthand for the first of those. That was the wrong unit: the
cliché is the *glowing gauge* — a needle sweep, a rev bar, a green that means
"good" on a dashboard pretending to be a dashboard — not the hue. This app has
no gauge, no dial and no bar, and its green does not mean good. It means **the
driver typed this**, which is a register, and it is the green of the product's
own logo. A product sharing no colour with its own mark was the stranger
position, and the ink the driver reads most was the third most legible of the
four at 6.6:1. It is 12.4:1 now.

## The registers

This is the system. Everything else serves it.

| Register | Colour | Means | Where |
|---|---|---|---|
| Stencil | `#E8E4DC` warm white, mono | **Measured** — came off the telemetry stream | Lap times, deltas, fuel used |
| Crayon | `#A3E635` NGR lime | **Declared** — the driver entered it | Every editor, compound tags, wear gauge |
| Derived | `#B08BD8` purple | **Derived** — the app worked it out | Box-in call, modelled stint, assumed inputs, the S1/S2/S3 column heads |
| Chalk | `#7FC7D9` | Provisional annotation, hints, parse results | Status lines |
| Struck | `#807870` | Removed from the count, disabled, placeholder | Excluded laps, empty fields |

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

### The rack is the one place the timing convention outranks the registers

**Purple, green, yellow, white — the FIA convention, verbatim.** It is what
every F1 timing screen uses and what GT7's own HUD uses, which means the
driver already knows how to read it and it is not ours to reinterpret:

| Colour | Means | Here |
|---|---|---|
| Purple | fastest anyone has set in the session | the fastest lap and sector **on this rack** |
| Green | a personal best | the best of its own stint, where that is not the session's |
| Yellow | slower than your own best | everything else |
| White | no reference set yet | the first counted lap |

**Purple is a claim about the session, not about the archive.** It was
first wired to the fastest ever set here in this car, which is a different
claim and — on a car with nothing on file — no claim at all: the rack showed a
green in every stint and nothing at all saying which of them held the quickest
lap of the day. An all-time best is a track record, and timing screens do not
paint one purple. It is said in the tooltip instead, which is also where a
purple figure says whether it is the record too. Colour is never the only
channel, and the claim that has no colour is the one that gets words.

**It took three wrong attempts to get here, and all three are worth keeping.**

First the rank was two very dark *fills* behind the number, on the argument
that purple ink was spoken for by the DERIVED register — while
purple-for-derived was itself argued *from* timing-screen convention. Both
cannot stand. The cost was that every sector on the rack came out purple,
because every sector is the app's own cut of the lap, and the driver read
what was painted: *every sector looks like it's the best sector.*

Then it was rebuilt as purple / blue / white, from the driver's own offhand
description — his memory of GT7 rendering the personal-best green with a blue
cast. Close, and still not the convention. **A convention is looked up, not
recalled**; the entire value of using one is that he already knows it, and a
private variant is worth less than none.

Two collisions, both answered rather than dodged:

- **Green is not `CRAYON`.** It sits 59° of hue from the acid lime, but the
  stronger argument is that the rack's time columns contain no declared
  values at all — a lap time, a delta and three sectors are measured or
  computed, never typed. Everything the driver declares on this screen is a
  control to the right of the row. Green in a time column cannot read as "he
  typed this", because nothing in a time column ever is.
- **Yellow is 9° from `WARNING`**, and allowed, because the two never appear
  in the same role: `WARNING` is prose and never a value; timing yellow is a
  value and never prose.

**The yellow is the dimmest of the three, deliberately** — 6.9:1 against
green's 9.8:1 and purple's 7.3:1. The first attempt was a lemon at 13.9:1,
brighter than both marks: right hue, upside-down hierarchy. Yellow is the
*ordinary* state, and on a rack of twelve laps that is fifty figures
competing with the two that matter. A timing screen carries a handful of
rows; this carries a stint.

Rule 5 did not lapse — it moved off colour entirely. The sectors are the
app's own cut of the lap, and that is said **in words**, on the spec line
above the rack ("Sectors · thirds of the lap — not GT7's") and in each
head's tooltip. A sentence cannot be mistaken for a timing mark.

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
stencilled in whichever ink actually contrasts better against that band,
measured (`theme.band_ink`, WCAG relative luminance). The earlier version
thresholded NTSC brightness at 0.55 and got six of the eleven wrong —
Intermediate green took warm white at 2.53:1 — which left colour as the only
channel on exactly the bands where the code mattered most. The code is set at
19px DemiBold so it qualifies as large text, where the floor is 3:1 and all
eleven clear it; four of the racing colours cannot reach 4.5:1 against either
ink, and those colours are the sport's, not ours. An excluded lap's band is
desaturated toward grey — it keeps its identity and loses its voice.

**`STRUCK` means removed from the count, and nothing else.** It carried every
hint, unit, column header and footer note in the app at 2.93:1 — the ink for
things that do not count, doing duty as the instructional colour. Prose is
`STENCIL_DIM` (5.70:1). `STRUCK` is left to placeholders, disabled controls,
the empty sentinel and the strike line, which are inactive or absent and are
what WCAG exempts. A test asserts no screen paints prose with it.

## Lettering

> **Every label carries its own size in its style sheet, and for the life of
> the app none of them did.** `theme.apply` sets `QWidget { font-size: 15px }`;
> a style-sheet rule beats `setFont`; nothing in `StencilLabel`, `BodyLabel`
> or `Measured` restated it. Measured before the fix: `StencilLabel` at size
> 10, 15 and 20 all painted 111px wide and 15px tall. The scale below was
> described and not drawn — the 10px column heads, 11px plate captions, 12px
> hints and 13px stint lines were all one size, and the app had no type
> hierarchy at all below body.
>
> It surfaced as one clipped word. "WEAR AT END" needs 73px at the 10px it
> asks for and 111px at the 15px it was given, in a 92px column — so a defect
> present on every screen since the beginning was reported as a heading
> losing a letter. **Third instance of this exact cascade**, and they are one
> shape: `QWidget { color }` beat `QPalette.Text` and made every declared
> value render as measured; `QWidget { font-size }` beat `setFont` here.
> `tests/test_rack_columns.py` guards it in a way that needs no fonts — three
> sizes must not paint as one.



| Role | Face | Why |
|---|---|---|
| Labels, headings, buttons | **Bahnschrift Condensed**, caps, tracked +8-14% | Bahnschrift is DIN 1451 — the German industrial signage standard that technical plates and moulded sidewall codes are lettered in. The correct letter for this world, not the convenient one. |
| All measurement | **Cascadia Mono** (fallback Consolas) | It *is* measurement, not a costume for "technical". |
| Prose | Bahnschrift regular | |

**Mono is measurement, and for a long time it was every editor.** The theme put
Cascadia on `QLineEdit`, `QPlainTextEdit`, `QComboBox` and both spin boxes
without exception, which set the event name, the notes, the paste box and the
driver's own words — the field its own label calls the most valuable on the
screen — in a typewriter. The face is put back only for editors that hold a
figure now, keyed on a dynamic property `Field` sets from the editor's type, so
the decision is made once at the point where the kind is actually known.

Qt style sheets carry no letter-spacing or text-transform, so tracking and
capitalisation are set on `QFont` in `theme.stencil_font()`.

Scale runs larger than a desk app's default (title 30px, body 15px, data
15px, lap time 23px) because it is read from the driving position.

## Components

- **`Plate`** — a bolted panel whose stencilled label is struck through its own
  top edge. The drawn border starts 11px below the widget top so the label sits
  centred on the rule with its full cap height inside; straddling y=0 clips the
  letters. The title is 15px in `STENCIL` against 11px `STENCIL_DIM` captions
  inside it: it was 12px in the same colour as its own contents, which made a
  23-key form's only chunking device the least legible text on it.
- **`EmptyState`** — what a plate says when it has nothing in it. Names the
  absence, then what would fill it, inside the plate where the absence is.
  Detached rather than destroyed on rebuild, so a build that finds nothing can
  say so again.
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
  taller neighbour was collapsing to a sliver. Hints still do not wrap — a
  wrapped hint reports a one-line height and overruns the field below it — but
  they now **elide** rather than demand their full width forever, with the
  whole hint kept as a tooltip. Non-wrapping hints were setting an unbreakable
  minimum for their whole column, and with the panes hiding their horizontal
  bars that turned into content nothing could reach.
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

Layout note, learned four times: a `Field`'s hint does not wrap and a
`QComboBox` sizes to its widest item, so either one sets a wide minimum for its
whole pane and silently clips every label in the column. Hints elide, combos
holding sentences get `AdjustToMinimumContentsLengthWithIcon` with the popup
sized separately — and the panes show a horizontal bar **as needed** rather
than never, because hiding the bar never stopped the overflow, only the
reaching.

The fourth time was the one that mattered, and it was not a width. **Settings
had no scroll area at all** — the only screen without one, and the tallest, at
1,291 px against a display that gives 501 logical pixels. `Save settings` sat
below the fold with nothing to reach it, on the screen that carries the
recovery controls for a broken feed, which is where the driver goes *because*
something is already wrong. The guard test iterated `findChildren(QScrollArea)`,
so a screen with zero of them passed vacuously. Every screen now fits 501 px of
height, and a test asserts that against the smallest display in the rig rather
than against the presence of a widget.

Practice was once the exception here — its column heads sat outside the scroll
area, so a bar would have slid the rows out from under their own headings. They
ride in their own viewport slaved to the rows' bar now, so the exception is
gone and the rack scrolls sideways like everything else.

## What this world refuses

Sparklines and progress rings; radial gauges; card grids of icon-plus-heading;
kickers above headings; gradient text; glass; coloured left borders; unicode
glyphs or emoji standing in for icons (there are no icons at all — the band and
the strike carry the work); monospace anywhere it is not measurement.
