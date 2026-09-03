# SimHub baseline — captured 15 Aug 2026

The rig as SimHub had it, kept because Pit Crew is taking the job over and
these three files are the only record of what "working" meant.

SimHub v9.11.13. Copied out of `C:\Program Files (x86)\SimHub`, which is the
reason they are here: **SimHub overwrites all three on update**, and one of
them cannot be regenerated at all.

## `DisplayClientV2.ino`

The firmware source for the **Sector 17 / Redion Wind Simulator** (WSP1/WSP2)
on COM5. Not a vendor file — SimHub generates it, compiles it, and flashes it,
so the device's entire configuration exists only as `#define`s inside this one
file. There is no copy on the device and no copy anywhere else on the machine
(a search of the whole user profile found zero other `.ino` files).

Lose it and the flashed configuration is gone.

**Update 4 Sep 2026:** the headers the `.ino` includes were not
unrecoverable after all - public copies of SimHub's generated sketch folder
exist, and the ones the wind layer depends on are in `sketch-src/` beside
this file, with a README on what each settles.

    #define VERSION 'j'
    #define DEVICE_NAME "Redion Wind Sim"
    #define DEVICE_UNIQUE_ID "c3bcb391-760c-4eee-89cb-232246fce7dc"
    #define ADAMOTORS_SHIELDSCOUNT 1     // Adafruit Motor Shield V2, I2C
    #define ADAMOTORS_FREQ 1200          // shield PWM frequency, 1900 max
    #define SHAKEITPWM_ENABLED_MOTORS 0      // direct-PWM path unused
    #define SHAKEITPWMFANS_ENABLED_MOTORS 0  // ditto

Two things in here are what Pit Crew's wind layer is built against:

* **The command dispatch** (`DisplayClientV2.ino`, in the serial loop) —
  `'V'` is `Command_Motors`, and `'V' 'S'` is followed by one raw byte per
  motor channel, in order, no delimiters. Four channels on this device even
  though only two fans are wired, so all four bytes must be sent.
* **The deadman**, in `SHShakeitBase.h`:

      #define SHShakeitBaseSafetyDelay 1000

  Over 1000 ms without a successful motors read and every channel is zeroed by
  the firmware itself. The fans cannot stick on if the PC side dies — which is
  the safety property the whole design leans on, and the reason Pit Crew must
  transmit at **≥1 Hz unconditionally**, even when the value has not changed.

Device handshake as logged by SimHub, for identification:

    { "DeviceName": "Redion Wind Sim", "MotorsCount": 4, "PortName": "COM5",
      "ExpandedFeatures": ["mcutype","keepalive","Gear","Motors"],
      "MotorsBoard": "Adafruit Motor Shield V2", "MCUModel": "ATmega328P",
      "USBDeviceName": "USB-SERIAL CH340" }

    COM5 · USB\VID_1A86&PID_7523 · boots at 19200, negotiates to 115200

## `ShakeITBassShakersSettingsV2.json`

The ButtKicker tuning. Active profile **"Porsche RSR 17"**, output device
`Speakers (ButtKicker PRO)` — a USB audio endpoint, not an analogue input.
Global gain 100, profile gain 49.83, `UseProfileGain: true`.

Six effects enabled of twenty-six. This is the target Pit Crew's haptics layer
has to reach, and it took ten dated revisions between 25 Jul and 11 Aug to
arrive at:

| Effect | Gain | Tone | Noise | Shaping |
|---|---|---|---|---|
| `WheelsSpinAndLockContainer` | 70.00 | 82 → 108 Hz | 9 | γ1.60 · min 28 · thr 14 · pre-emptive |
| `GearEffectContainer` | 39.87 | 48 Hz single | — | pulse 80 ms · RPM-modulated 50–90 % |
| `WheelsRumbleContainer` | 37.62 | 112 → 152 Hz | 12 | γ1.60 · min 28 · thr 8 · ramp-down 1 s |
| `TractionLossContainer` | 35.19 | 52 → 70 Hz | 6 | γ1.40 · min 12 · thr 9 |
| `WheelsImpactContainer` | 12.31 | 28 → 38 Hz | 3 | γ1.20 · min 20 · thr 55 |
| `RPMContainer` | 9.52 | 34 → 42 Hz | 3 | spline, peaks at 63 % |

**Trap:** the RPM effect's spline control points are stored **out of ascending
X order** — the last entry sorts fourth. SimHub sorts them on load. Reading the
file top-to-bottom gives the wrong curve. The correct order is
`5.21→0, 20.71→2.99, 42.84→14.13, 63.08→36.91, 77.40→48.56, 100→63.06`.

**Also worth knowing:** there are *two* `OutputManager` blocks. The global one
points at `Headphones (Realtek(R) Audio)` with a 200 Hz low-pass. Only
`IncludeOutputSettingsInProfile: true` makes the ButtKicker win.

## `WindSettings.json`

Wind tuning as of 15 Aug 16:30. Two fans on `ArduinoOutput` channels 0 and 1
(roles 2 and 3); every other fan backend disabled.

    Static:   Gain 32, EnableInRace FALSE
    Dynamic:  Gamma 1.0, GammaFactor 10.0, MinGain 29.76, MaxGain 100.0,
              MaximumSpeed 281.08, MaximumSpeedMode 1, DraftEffect 0.0

Two of those are easy to misread:

* **`EnableInRace: false`** means the 32 % static floor is suppressed while
  racing. During a race the dynamic curve is the only thing driving the fans,
  so any static tuning done at a standstill is not what gets felt on track.
* **`DraftEffect: 0.0`** with `IsDraftEffectEnabled: true` — the tow effect is
  switched on and weighted to nothing, i.e. inert.

The speed→fan formula itself is compiled into `SimHub.Plugins.dll` and is not
recoverable from these files. Pit Crew derives the curve empirically instead
and then takes its scale from `car_max_speed_raw`, which GT7 reports per car —
299 km/h for the RSR, against the 281.08 tuned by hand here.

---

These are reference material, not inputs. Nothing in `pitcrew/` reads them.
