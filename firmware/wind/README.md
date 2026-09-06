# Wind sim firmware

The code that runs on the Redion Wind Sim board — an Arduino Uno behind a
CH340 on COM5, driving two fans through an Adafruit Motor Shield V2.

Written 6 Sep 2026 to replace SimHub's generated `DisplayClientV2.ino`.

## Why this is ours now

SimHub is uninstalled. It was never what *drove* the fans — `pitcrew/rig/wind.py`
has done that since 15 Aug — but it was the only thing that could compile a
sketch for this board, and the board needed a change.

Rebuilding SimHub's own sketch was the obvious route and turned out to be the
worse one. Of the forty-odd features in that 106 KB file **exactly one was
compiled in for this device** (`INCLUDE_SHAKEITADASHIELD`); everything else —
every display, LED strip, gauge and button — is `#define`d out. But four
headers are included unconditionally regardless, and SimHub keeps them inside
its own DLLs and extracts them at upload time. So rebuilding it meant fetching
a third party's generated code we cannot fully see, to compile forty features
we do not use, to change one number.

The one feature is about two hundred lines. It is now this file.

## What it does

Reads SimHub's ARQ framing off the serial port, and sets four PWM channels on
the shield. That is the whole job.

The protocol is **not** ours and is not changed here. `pitcrew/rig/arq.py` was
reverse-engineered off the wire over three weeks — including a CRC polynomial
that had to be discovered by asking the board, which rejected three obvious
candidates first. It is the more expensive half of the pair and it is already
correct, so this firmware is written to match *it*, byte for byte.

`pitcrew/tests/test_wind_firmware.py` holds the two halves together. The test
that matters is the checksum one: it reproduces the 256-entry table SimHub
actually shipped, from the bitwise routine in this sketch, entry by entry.

## The one change

The shield's PWM chop frequency, **1221 Hz → 1526 Hz**.

That is the fix for the fan dropouts — the fans die coming out of slow corners
under acceleration, which is when the rotor is still slow and the commanded
duty is high, which is when a brushless blower's controller draws its largest
current. A faster chop means less ripple current for it to deal with.

1526 Hz is not a preference, it is the ceiling:

    prescale = round(25e6 / (4096 × f)) − 1,  minimum 3   [PCA9685 datasheet]
    25e6 / (4096 × 4) = 1525.9 Hz

Worth recording, because it will come up again: **SimHub's settings field was
labelled "PWM Frequency of the board (1900hz max)" and defaulted to 1900 — a
value the chip cannot produce.** Asking for 1900 lands on prescale 3 and gives
1526. This rig was set to 1200, landing on prescale 4 and 1220.7 Hz.

There is no headroom left in this number. If the dropouts survive the change,
the frequency was not the cause — `WIND_RAMP_STEP` in the sketch is the next
hypothesis (inrush on a fast duty step), and it ships disabled on purpose so
that this change can be judged on its own.

Everything else is byte-identical to the SimHub build: the device name, the
unique id, the version letter `j`, the four channels, the feature letters, and
the 1000 ms deadman that means the fans cannot stick on if the PC side dies.

## Building and flashing

    scripts\wind-reflash.cmd

Five stages: free the port, take (or reuse) a verified flash backup, build and
upload, bench-test, and a one-command way back. It never writes to the board
before a backup exists and has been proved by a second read.

To put the SimHub firmware back:

    scripts\wind-reflash.cmd --restore

The toolchain is the one SimHub left behind:

    C:\Program Files (x86)\SimHub\_Addons\Arduino\ArduinoIDE\arduino-1.6.13\

`arduino-builder.exe` for the compile, `hardware\tools\avr\bin\avrdude.exe` for
the flash. If that folder is ever deleted, point `IDE_HOME` at the top of
`scripts/wind-reflash.sh` at any Arduino IDE 1.6–1.8 install; nothing else in
the build depends on SimHub. The sketch needs only `Wire` and the AVR core.

**The build path must be absolute.** arduino-builder 1.3.21 fails with
`can't make ... relative to .build\wind` otherwise, which reads like a
permissions problem and is not one.

Current size: 5,152 bytes of flash (15.7%), 583 bytes of RAM (28.5%).
