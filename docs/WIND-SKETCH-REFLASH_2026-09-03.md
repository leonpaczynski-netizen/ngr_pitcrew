# Reflashing the wind simulator sketch

Written 3 Sep 2026. For the Sector 17 / Redion Wind Sim on COM5: Arduino Uno
(ATmega328P), CH340 bridge, Adafruit Motor Shield V2, two fans. SimHub
v9.11.13 generated the sketch that is on it now.

## Why, in two paragraphs

The sketch drives the fans through the motor shield's brushed-motor H-bridge,
chopping their supply at 1200 Hz (`ADAMOTORS_FREQ 1200`, vendor cap 1900).
A brushless fan has its own controller inside, and chopping its supply at
that rate browns the controller out in bands of duty rather than in
proportion to load. That fits every answer you gave on 29 Aug: both fans stop
together, they come back on their own, no setting change helped in a
consistent direction, and it happened under SimHub too. SimHub ships a second
fan path, the **ShakeIt PWM Fans** module, which puts a 25 kHz control signal
on pins 9 and 10 and leaves the fan's supply alone. It is disabled in the
current sketch. This document turns it on.

This is separate from the serial-link fault fixed on 3 Sep (60 Hz to 20 Hz).
Nothing on the PC can see a fan, so the only evidence for this fault is what
you feel. The reflash changes what you feel and nothing in the log.

> **What the photos of 3 Sep 2026 showed, and what it does to this plan.**
> The box holds a clone Uno R3 under an Adafruit Motor Shield v2.3 ("1.2A
> per motor, 3A max"). The two fan cables leave the box through their own
> grommets and each carries **two conductors**, so these are two-wire fans:
> the 25 kHz PWM-fan reflash in sections 3 and 4 **does not apply as
> written** - there is no control wire to drive. The supply is a generic
> wall adaptor, model 1230, **12 V 3 A**, into a panel-mount jack wired to
> the shield's motor power terminal. Three amps is the shield's own total
> limit and is marginal for two blowers at full duty; a supply in
> current-limit "hiccup" mode stops both fans together and lets them restart
> a moment later, is worst at high duty, and reads as weaker fans. That is
> every symptom reported. **First hardware move: a 12 V supply rated 5 A or
> more, same barrel.** Second, if drops persist: section 0's two-wire
> branch, raising the shield frequency to 1900 Hz in the setup tool. The
> VIN jumper's position could not be made out in the photos.

> ### 6 Sep 2026 — the driver's pattern sharpens this, and corrects one line
>
> *"Coming from a fast straight to a tight turn that leads to quick
> acceleration out of the corner — coming out of the corner is where the fans
> seem to die and have to reboot."*
>
> **That is not "worst at high duty", and the difference matters.** On the
> straight the duty is at its highest and the fans survive it; they drop on
> the way back up. The supply hypothesis survives this — it is strengthened by
> it — but the mechanism is re-acceleration, not steady load:
>
> - A blower draws its largest current when the **rotor is slow and the duty
>   is high**, because back-EMF is low. At speed on a straight the same duty
>   draws considerably less.
> - Out of a slow corner the rotors have spun down and the duty is climbing,
>   which is the highest-current condition of the whole lap.
> - And it is not brief. Measured off `logs/pitcrew-wind-frames.log`,
>   72,437 frames on 5 Sep: the app ramps duty at **+1 per 50 ms frame**
>   (median +1, p99 +1, i.e. ~20 units/s). Corner duty ~82 to straight duty
>   ~185 is therefore a **~5 second sustained high-current window**. A 3 A
>   supply has ample time to reach current limit and hiccup.
>
> **The serial link is ruled out for this symptom**, on the same log: 4
> non-acked frames in 72,437 over two hours, and all three driver-faults sit
> at high *steady* duty on a straight (184 at 160 km/h) or at 0 km/h. **None
> is at a corner exit.** The app is also not slamming the fans — a +1 step per
> frame is gentle, so there is no commanded transient to blame.
>
> **This makes it a STARTING problem in `wind_sweep.py`'s sense**, and that
> tool was built for exactly this discrimination: a duty that misbehaves on
> the way up but not on the way down is a starting problem; one that
> misbehaves in both directions is a running problem, and they want opposite
> fixes. So the order of work is unchanged but now carries a prediction that
> can fail:
>
> 1. `python tools/wind_sweep.py sweep --channels 0,1 --step 8` — **expect the
>    marks to cluster on the way UP and not on the way down.** If they appear
>    in both directions, this refinement is wrong and it is a running fault.
> 2. The 12 V 5 A supply. If it is supply current limit on re-acceleration,
>    this removes it.
> 3. Only then the 1900 Hz shield frequency.

> ### 6 Sep 2026 — do this with `scripts/wind-reflash.sh`
>
> **The branch that applies to this rig is the two-wire one in section 0:**
> raise the shield frequency from 1200 to 1900. Sections 3 and 4 — the 25 kHz
> PWM-fan conversion — need a blue control wire the fans do not have.
>
> **And the rollback in section 2 had never been run.** There was no `.hex` in
> `reference/simhub-baseline/` at all, so until today nothing could be put
> back. The script takes one first, and reads the board **twice** and compares,
> because a backup nobody has checked is a file rather than a rollback.
>
> From PowerShell or cmd:
>
> ```
> scripts\wind-reflash.cmd            backup, then the reflash, guided
> scripts\wind-reflash.cmd --restore  put the original image back
> ```
>
> **Not `bash scripts/wind-reflash.sh` from PowerShell.** Windows ships its
> own `bash.exe` in System32 that shims to WSL, and with no distro installed
> it fails with `execvpe(/bin/bash) failed: No such file or directory` — which
> reads like the script is missing and is nothing of the kind. The `.cmd`
> finds Git's bash. From a Git Bash window the `.sh` is fine directly.
>
> It refuses to go on if the two reads differ, if the image is under 1 kB, or
> if avrdude is not where SimHub puts it — and it writes nothing to the board
> in any of those cases.

## 0. Two things to check before touching anything

Both decide whether this procedure applies at all.

1. **How many wires come out of each fan?**
   - **Four** (usually red, black, yellow, blue): the blue wire is a PWM
     input. This procedure applies as written.
   - **Three** (no blue): no PWM input. Stop here. The fan can only be
     driven by chopping its supply, which is what is wrong now. Cheapest
     experiment instead: re-run the SimHub setup tool and raise
     `ADAMOTORS_FREQ` from 1200 to its maximum of 1900. Anything better
     needs a MOSFET module and is a different job.
   - **Two**: same as three.
2. **Where is the shield's VIN jumper, and what does the PSU label say?**
   Note both. If the jumper is fitted, motor current has been sharing the
   Uno's supply rail; after this procedure the fans take their power straight
   from the PSU and the jumper should come out. Write the PSU's volts and amps
   down; it is the one number about this rig nobody has recorded.

## 1. Close everything that holds COM5

Pit Crew reconnects to the port on a timer, and SimHub enumerates it. Either
one will make the upload fail with "access denied" or "not in sync".

- Quit Pit Crew (the tray icon, not just the window).
- Quit SimHub, or in SimHub go to Arduino and untick the wind device's
  output until this is done.
- Confirm nothing has it:

```bash
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'pitcrew|SimHub' } | Select-Object ProcessId, Name"
```

Empty output is the answer you want.

## 2. Back up what is on the board

SimHub bundles Arduino 1.6.13, and that carries avrdude 6.3, so nothing needs
installing. Opening the port resets the board, which is fine here.

```bash
"C:\Program Files (x86)\SimHub\_Addons\Arduino\ArduinoIDE\arduino-1.6.13\hardware\tools\avr\bin\avrdude.exe" -C "C:\Program Files (x86)\SimHub\_Addons\Arduino\ArduinoIDE\arduino-1.6.13\hardware\tools\avr\etc\avrdude.conf" -c arduino -p m328p -P COM5 -b 115200 -U flash:r:C:\Projects\VR_Dashboard\reference\simhub-baseline\redion-flash-backup-20260903.hex:i
```

- Success ends with `avrdude done. Thank you.` and a file of a few tens of
  kilobytes. A file under 1 kB or a run that ends in `not in sync` did not
  work: try `-b 57600`, which is the older Uno bootloader rate.
- Keep the file. It is the one-command rollback in section 7.
- The sketch source is already saved at
  `reference/simhub-baseline/DisplayClientV2.ino`. Its config values are
  below, in case the setup tool has to be filled in from scratch.

## 3. Regenerate the sketch in SimHub

SimHub does not edit the sketch in place. It regenerates the whole thing from
the setup tool's answers, compiles it with the bundled IDE, and uploads it
through its own uploader. So the change is made in the setup tool, not in a
text editor.

1. Start SimHub. Left menu, **Arduino**. Open **Arduino setup tool**
   (on the "My hardware" tab).
2. Choose **Single Arduino**.
3. Set the board type to **Uno** and the port to **COM5**.
4. Go through the feature pages. Everything stays off except the ShakeIt
   pages, which change like this:

   | Page | Setting | Now | Set to |
   |---|---|---|---|
   | SHAKEIT Adafruit Motorshield V2 | Number of shields connected | 1 | **0** |
   | SHAKEIT PWM FANS Outputs | ShakeIT direct PWM fans enabled (25 kHz) | 0 | **2** |
   | | PWM Output 1 pin | 9 | 9 |
   | | PWM Output 1 min / max | 0 / 255 | 0 / 255 |
   | | PWM Output 1 optional relay pin | 4 | **-1** |
   | | PWM Output 2 pin | 10 | 10 |
   | | PWM Output 2 min / max | 0 / 255 | 0 / 255 |
   | | PWM Output 2 optional relay pin | 5 | **-1** |

   Leave the relay pins at -1 unless you have wired relays. The tool's own
   note says pins 9 and 10 are the only 25 kHz outputs on an Uno; do not use
   11.
5. The device name will be asked for or preserved. Keep **Redion Wind Sim**.
   The unique id is SimHub's and it may issue a new one; that is fine, Pit
   Crew does not read it.
6. **Upload to Arduino**. Watch for the compile then the upload. The upload
   resets the board; the fans should not spin during it (measured on this
   rig 15 Aug: they did not).
7. When it finishes, SimHub's Arduino page should show the device connected
   with **2 motors** (it said 4 before). If it says 0, the shield count did
   not take; go back to step 4.

Then quit SimHub again, or leave its output for this device unticked. Two
programmes must not both talk to the board.

## 4. Rewire the fans

The fans stop being motor-shield loads and become PWM-controlled fans on
their own supply.

1. Power off the PSU.
2. Disconnect both fans from the shield's M1 and M2 terminals.
3. Fan power: **red to PSU +, black to PSU −**, for both fans, directly. The
   shield's motor power terminals are fine as the tap point if that is where
   the PSU lands, because that ground is the Arduino's ground. What matters
   is that fan − and the Uno's GND are the same net.
4. Fan control: the **blue** wire of the fan you want as **channel 0**
   (left, as Pit Crew currently maps it) goes to **pin 9**; the other fan's
   blue wire to **pin 10**. On the Motor Shield V2 the easiest place to reach
   those is the two 3-pin servo headers on the shield's edge: check the
   silkscreen, but on that shield **Servo 2 is pin 9 and Servo 1 is pin 10**,
   with the signal pin nearest the board edge. Only the signal pin is used;
   do not connect the fan's red wire to the header's 5 V pin.
5. The yellow wire (tachometer) stays unconnected.
6. Pull the shield's VIN jumper if it was fitted (section 0).
7. Power the PSU on. With nothing talking to the board a 4-wire fan may idle
   at its minimum speed; the Intel spec allows that at 0% PWM. If that turns
   out to be audible and unwanted, the relay pin option in section 3 exists
   for it.

## 5. Pit Crew needs no change for the narrower board

The old sketch declared four motors and the new one declares two. That
turned out not to matter, and it was measured rather than assumed: on 3 Sep
2026 the four-motor board acknowledged 26,875 eight-wide frames in a row
with the fans running normally. The firmware's packet layer buffers a frame
to its declared length, checks it, acknowledges it, and discards whatever
the command did not read. A frame wider than the board is harmless. Pit
Crew keeps sending four bytes, and the two-motor sketch reads the first two.

Still run this once against the new sketch, with Pit Crew closed:

```bash
python tools/wind_bench.py handshake
```

  On the old sketch it prints `firmware j`, `count 4`, `board Adafruit
  Motor Shield V2`, and `accepts [1..8]` (every width is acknowledged; that
  line is a measurement, not a count). After the reflash the board line is
  the confirmation: it should name SimHub's PWM fans module instead, and
  the count should read 2. In the app log the same appears as
  `COM5 declares 2 channels on '<new board name>'; sending 4 as on file`.

- Then re-measure the three things the old path measured, in this order,
  with Pit Crew closed:

```bash
python tools/wind_bench.py channel 0 --duty 120 --seconds 3
```

  Which fan moved? That decides `CHANNEL_LEFT`. Swap the blue wires if it
  is the wrong one.

```bash
python tools/wind_bench.py ramp --channel 0 --step 15 --dwell 1.5
```

  The lowest duty that turns the fan. `MIN_MOVING_DUTY` was 3 on the
  H-bridge path and will be different on a PWM input.

```bash
python tools/wind_sweep.py --channels 0,1 --step 8 --dwell 3
```

  The band finder, up and then down. On the old path this never found a
  band on the bench; the question is whether it finds one now, and whether
  your Monza T1 replay still drops.

## 6. What "it worked" looks like

- Bench: `wind_sweep` completes both directions with no stall at any duty,
  and `wind_bench stress --duty 255 --seconds 180` completes, which it never
  has.
- On track: a session with no felt drop, while `logs/pitcrew.log` shows
  hard link losses at the post-20 Hz rate. If the fans still drop and the
  log is clean, the sketch was not the fault either, and the next suspect
  is the PSU under load, which section 0's label reading is the start of.
- The app's log lines cannot confirm this either way. Only you can.

## 7. Rollback

Either of these puts the old behaviour back.

- **Exact image**, no SimHub needed:

```bash
"C:\Program Files (x86)\SimHub\_Addons\Arduino\ArduinoIDE\arduino-1.6.13\hardware\tools\avr\bin\avrdude.exe" -C "C:\Program Files (x86)\SimHub\_Addons\Arduino\ArduinoIDE\arduino-1.6.13\hardware\tools\avr\etc\avrdude.conf" -c arduino -p m328p -P COM5 -b 115200 -D -U flash:w:C:\Projects\VR_Dashboard\reference\simhub-baseline\redion-flash-backup-20260903.hex:i
```

- **Through the setup tool**: shield count back to 1, PWM fans back to 0,
  shield frequency 1200, upload, and put the fans back on M1 and M2.
- Pit Crew needs nothing in either case: it asks the board its count on
  every connect.

## Reference: the old sketch's values

From `reference/simhub-baseline/DisplayClientV2.ino`, 15 Aug 2026.

    VERSION 'j'
    DEVICE_NAME "Redion Wind Sim"
    DEVICE_UNIQUE_ID "c3bcb391-760c-4eee-89cb-232246fce7dc"
    ADAMOTORS_SHIELDSCOUNT 1
    ADAMOTORS_FREQ 1200
    SHAKEITPWM_ENABLED_MOTORS 0
    SHAKEITPWMFANS_ENABLED_MOTORS 0
    serial 19200 at boot, DVB-S2 CRC-8, 1000 ms motors deadman

The deadman is in the shared ShakeIt base and applies to the PWM fans module
as well, so the 1 s safety property Pit Crew relies on survives the reflash.
