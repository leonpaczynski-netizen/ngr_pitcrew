/*
  Redion Wind Sim - Pit Crew firmware
  ==================================================================

  Two fans on an Adafruit Motor Shield V2, on an Arduino Uno behind a CH340,
  on COM5. This replaces the SimHub-generated `DisplayClientV2.ino`.

  **Why this exists.** SimHub is gone from the machine, and with it the only
  button that could compile a sketch for this board. Its Arduino toolchain
  survived the uninstall, so the compiler was never the problem - the problem
  was that its 106 KB generated sketch pulls in headers SimHub keeps inside
  its own DLLs. Of the forty-odd features in that file exactly one was
  compiled in for this device. So the honest move is to write the one feature
  out, in a file we own, and stop depending on a tool that is not installed.

  **The protocol is not ours, and is not changed here.** `pitcrew/rig/arq.py`
  drives this board and was reverse-engineered off the wire over three weeks;
  it is the more expensive half of the pair and it is already correct. So
  this firmware is written to match *it*, byte for byte, rather than the
  other way round. Every reply below is the one the old firmware sent, in the
  same order, with the same markers - `arq.py`'s own docstrings record what
  was measured coming back, and those recordings are the acceptance test.

  Nothing about the wire format is an improvement. One thing is:

  **The PWM frequency, which is the fault this was built to fix.** The fans
  die coming out of slow corners under hard acceleration - the moment the
  rotor is still slow and the commanded duty is high, which is when a
  brushless blower's own controller draws its largest current. The shield was
  chopping at ~1221 Hz. Raising the chop frequency lowers the ripple current
  the blower's controller sees. See `WIND_PWM_HZ` below for what is actually
  reachable, which is not what SimHub's settings field claimed.

  Register discipline, since this file makes claims: everything in the
  protocol section is MEASURED - either read out of the recovered SimHub
  headers in `reference/simhub-baseline/sketch-src/`, or off the wire and
  recorded in `arq.py`. The frequency reasoning is DERIVED and says so.
*/

#include <Arduino.h>
#include <Wire.h>

// ---------------------------------------------------------------- identity
//
// Unchanged from the SimHub build, deliberately. The unique id is how the
// host recognises this board; inventing a new one would make it a new device
// to anything that has seen it before.

#define FIRMWARE_VERSION   'j'
#define DEVICE_NAME        "Redion Wind Sim"
#define DEVICE_UNIQUE_ID   "c3bcb391-760c-4eee-89cb-232246fce7dc"
#define MOTOR_BOARD_NAME   "Adafruit Motor Shield V2"

// Four, though only two fans are wired. The host reads exactly this many
// bytes per motors frame with no delimiters, so the count is part of the
// wire format and may not be trimmed to the hardware.
#define CHANNELS           4

// **The boot rate, and the only rate.** The old firmware could negotiate up
// to 115200 on command '8'. Pit Crew never asks: a motors frame is twelve
// bytes at 20 Hz, which is 1% of even 19200, so the negotiation was a step
// that could fail in exchange for nothing.
#define BOOT_BAUD          19200

// **The deadman.** More than this long without a *complete* motors frame and
// every channel is zeroed by this firmware itself. It is the reason the fans
// cannot stick on if the PC side dies, is killed, or hangs - which no host
// atexit handler can promise. `SHShakeitBaseSafetyDelay`, unchanged.
#define SAFETY_DELAY_MS    1000

// ------------------------------------------------------ which board drives
//
// **Two backends, and the reason the second exists.**
//
// The shield path chops the fans' SUPPLY through an H-bridge, and the
// PCA9685 that times it cannot go above 1526 Hz. A 2-wire brushless blower
// carries its own commutation controller, and that controller runs off a
// small internal capacitor. At 1526 Hz the off-phase is up to 650 us, and a
// fan drawing ~1.5 A empties a ~100 uF internal cap in far less than that -
// so the controller browns out and restarts, in bands of duty rather than in
// proportion to load. That is the fault the driver has reported since
// August, and it is why no setting change ever helped in a consistent
// direction.
//
// At 20 kHz the same arithmetic gives an off-phase of 50 us and a droop
// under a volt. **The frequency is the fix, and the shield could never
// reach it** - which is why the drive moved off the shield entirely rather
// than being tuned.
#define DRIVE_BTS7960
//#define DRIVE_ADAFRUIT_SHIELD

#if defined(DRIVE_BTS7960) == defined(DRIVE_ADAFRUIT_SHIELD)
#error "Select exactly one drive backend."
#endif

#ifdef DRIVE_ADAFRUIT_SHIELD
// -------------------------------------------------------------- the shield
//
// Adafruit Motor Shield V2 = a PCA9685 16-channel PWM driver at 0x60 feeding
// two TB6612 H-bridges. Driven here over I2C directly rather than through
// Adafruit's library, because the library is not on this machine and the
// part of it this board uses is the twenty lines below.

#define SHIELD_I2C_ADDR    0x60

#define PCA9685_MODE1      0x00
#define PCA9685_PRESCALE   0xFE
#define PCA9685_LED0_ON_L  0x06

#define PCA9685_MODE1_SLEEP    0x10
#define PCA9685_MODE1_RESTART  0x80
#define PCA9685_MODE1_AI       0x20   // register auto-increment

// The PCA9685's internal oscillator, per the datasheet.
#define PCA9685_OSC_HZ     25000000.0f

// **The datasheet's prescale floor, and why the old setting could not do
// what its own label said.**
//
//     prescale = round(25e6 / (4096 * f)) - 1,  and prescale >= 3
//
// so the highest frequency this part can produce is 25e6/(4096*4) = 1525.9
// Hz. SimHub's field was labelled "PWM Frequency of the board (1900hz max)"
// and defaulted to 1900 - a value the chip cannot reach. Asking for 1900
// lands on prescale 3 and yields 1526 Hz; asking for 1200 lands on prescale
// 4 and yields 1220.7 Hz, which is what this rig has actually been running.
//
// So the change made here is 1221 -> 1526 Hz, a 25% rise, and it is the
// whole of what the part allows. **DERIVED, not measured:** that more chop
// frequency means less ripple current at the blower is standard switching
// practice and follows from the fault's timing, but nothing on this rig has
// measured the blower's current. If the dropouts survive this, the frequency
// was not the cause and `WIND_RAMP_STEP` below is the next thing to try -
// not a second guess at this number, because there is no headroom left in it.
#define PCA9685_PRESCALE_MIN  3
#define WIND_PWM_HZ           1526

#endif  // DRIVE_ADAFRUIT_SHIELD

// **The slew limit, deliberately off.**
//
// If raising the frequency does not fix it, the next hypothesis is inrush:
// the host commands a large duty step on corner exit while the rotor is
// still slow, and the blower's controller faults rather than serve it. A cap
// on how far the duty may RISE per frame would soften exactly that, and only
// that - falls stay instant, because a fan that will not slow down is its
// own problem.
//
// It is 0 (disabled) because this build changes the frequency, and changing
// two things at once means learning nothing from either. Set it to about 24
// - roughly 10% of range per 50 ms frame, so a standstill-to-full step takes
// half a second - only after the frequency alone has been given a session
// and judged.
#define WIND_RAMP_STEP        0

// Adafruit's motor-to-PCA9685 channel map, from `getMotor(1..4)`. Each motor
// takes three channels: one chopped for speed, two static for direction.
// Fans are wired to motors 1 and 2 (host channels 0 and 1).
static const uint8_t MOTOR_PWM[CHANNELS] = { 8, 13, 2, 7 };
static const uint8_t MOTOR_IN2[CHANNELS] = { 9, 12, 3, 6 };
static const uint8_t MOTOR_IN1[CHANNELS] = { 10, 11, 4, 5 };

static uint8_t motorValue[CHANNELS];        // what each channel is set to now
static unsigned long lastMotorsRead = 0;    // 0 = nothing to time out yet

// ------------------------------------------------------------- PCA9685 I/O
#ifdef DRIVE_ADAFRUIT_SHIELD

static void pcaWrite(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(SHIELD_I2C_ADDR);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

static uint8_t pcaRead(uint8_t reg) {
  Wire.beginTransmission(SHIELD_I2C_ADDR);
  Wire.write(reg);
  Wire.endTransmission();
  Wire.requestFrom((uint8_t)SHIELD_I2C_ADDR, (uint8_t)1);
  return Wire.available() ? Wire.read() : 0;
}

// One channel's on/off phase. 4096 in either field is the part's "full on" /
// "full off" bit rather than a count, which is why the direction pins below
// use it instead of a 0% or 100% duty.
static void pcaSetPWM(uint8_t channel, uint16_t on, uint16_t off) {
  Wire.beginTransmission(SHIELD_I2C_ADDR);
  Wire.write((uint8_t)(PCA9685_LED0_ON_L + 4 * channel));
  Wire.write((uint8_t)(on & 0xFF));
  Wire.write((uint8_t)(on >> 8));
  Wire.write((uint8_t)(off & 0xFF));
  Wire.write((uint8_t)(off >> 8));
  Wire.endTransmission();
}

static void pcaFullOn(uint8_t channel)  { pcaSetPWM(channel, 4096, 0); }
static void pcaFullOff(uint8_t channel) { pcaSetPWM(channel, 0, 4096); }

// `value` is 0..4095 of a 4096-count period.
static void pcaDuty(uint8_t channel, uint16_t value) {
  if (value == 0)         pcaFullOff(channel);
  else if (value >= 4095) pcaFullOn(channel);
  else                    pcaSetPWM(channel, 0, value);
}

// Returns the prescale actually written, so the caller can report the
// frequency the part is really running rather than the one it asked for.
static uint8_t pcaSetFrequency(uint16_t hz) {
  float prescaleval = PCA9685_OSC_HZ / (4096.0f * (float)hz) - 1.0f;
  int rounded = (int)floor(prescaleval + 0.5f);
  if (rounded < PCA9685_PRESCALE_MIN) rounded = PCA9685_PRESCALE_MIN;
  if (rounded > 255) rounded = 255;
  uint8_t prescale = (uint8_t)rounded;

  // The prescale register is writable only while the oscillator is asleep,
  // so: sleep, write, wake, then restart the PWM channels that were running.
  uint8_t oldmode = pcaRead(PCA9685_MODE1);
  pcaWrite(PCA9685_MODE1, (uint8_t)((oldmode & 0x7F) | PCA9685_MODE1_SLEEP));
  pcaWrite(PCA9685_PRESCALE, prescale);
  pcaWrite(PCA9685_MODE1, oldmode);
  delay(5);
  pcaWrite(PCA9685_MODE1,
           (uint8_t)(oldmode | PCA9685_MODE1_RESTART | PCA9685_MODE1_AI));
  return prescale;
}

// **Zero is a coast, not a brake.** Both direction pins low leaves the
// bridge open and the fan free-wheels down, which is what the old firmware
// did (`run(RELEASE)`) and what the driver has felt for a year. Shorting the
// windings to stop it faster would be a change nobody asked for.
static void setMotorOutput(uint8_t idx, uint8_t value) {
  motorValue[idx] = value;
  if (value == 0) {
    pcaFullOff(MOTOR_IN1[idx]);
    pcaFullOff(MOTOR_IN2[idx]);
  } else {
    pcaFullOff(MOTOR_IN2[idx]);
    pcaFullOn(MOTOR_IN1[idx]);
    // 255 -> 4080, matching Adafruit's `setSpeed`: 99.6% duty, not 100%.
    pcaDuty(MOTOR_PWM[idx], (uint16_t)value * 16);
  }
}

// **No I2C timeout is set, and it is not an oversight.** `Wire.setWireTimeout`
// would stop a hung bus wedging this loop - and because the PCA9685 has its
// own oscillator, a hang leaves the fans STUCK AT LAST DUTY rather than
// stopping them, which the deadman cannot help with because the deadman's own
// writes would hang too. It is the right guard and it does not exist here:
// the bundled core is Arduino 1.6.13 from 2016 and the call was added around
// 2020. Reaching it means a newer AVR core, not a change to this file.
// Checked 6 Sep 2026 - `setWireTimeout` appears nowhere in this core's Wire.h.
static void shieldBegin() {
  Wire.begin();
  pcaWrite(PCA9685_MODE1, 0x00);        // reset
  pcaSetFrequency(WIND_PWM_HZ);
  for (uint8_t i = 0; i < CHANNELS; i++) {
    motorValue[i] = 0;
    setMotorOutput(i, 0);
  }
}

#else   // ============================================ DRIVE_BTS7960

// **Timer1 hardware PWM straight out of the ATmega, into two BTS7960
// half-bridge modules.** No I2C, no PCA9685, no shield - and therefore no
// 1526 Hz ceiling.
//
// 20 kHz, exactly: fast PWM with ICR1 as TOP and no prescaler gives
// 16 MHz / (ICR1 + 1), so ICR1 = 799. That is 13x the shield's best and
// above most people's hearing. The BTS7960 is rated to 25 kHz, so there is
// headroom left in this number, which the shield never had.
#define WIND_PWM_HZ        20000UL
#define PWM_TOP            ((uint16_t)((F_CPU / WIND_PWM_HZ) - 1))

// Pins 9 and 10 are OC1A and OC1B - the only two the timer can drive
// directly, and the reason the two fans live on channels 0 and 1.
#define PIN_PWM_LEFT       9
#define PIN_PWM_RIGHT      10
// Each module's R_EN and L_EN, tied together and driven from one pin.
#define PIN_EN_LEFT        7
#define PIN_EN_RIGHT       8

// **Only two of the four channels reach hardware, and that is deliberate.**
// The protocol carries four because the host reads exactly `motorCount()`
// bytes with no delimiters, so the wire format may not be trimmed to the
// hardware. Channels 2 and 3 are accepted, recorded and driven nowhere.
// A third and fourth fan would go on Timer2 (pins 3 and 11).
#define DRIVEN_CHANNELS    2

// **Zero disables the bridge rather than commanding zero duty, and the
// difference matters for these fans.** With R_EN low the BTS7960's outputs
// go high-impedance and the fan free-wheels, exactly as the old shield's
// `run(RELEASE)` did. Held enabled at zero duty the bridge would instead
// clamp both fan terminals to ground - shorting the blower's own internal
// supply capacitor, which is the one thing its controller likes least.
static void setMotorOutput(uint8_t idx, uint8_t value) {
  motorValue[idx] = value;
  if (idx >= DRIVEN_CHANNELS) return;

  const uint8_t enable = (idx == 0) ? PIN_EN_LEFT : PIN_EN_RIGHT;
  if (value == 0) {
    digitalWrite(enable, LOW);
    if (idx == 0) OCR1A = 0; else OCR1B = 0;
    return;
  }
  // 255 maps to TOP, so full duty is genuinely full rather than 99.6%.
  const uint16_t duty = (uint16_t)(((uint32_t)value * PWM_TOP) / 255u);
  if (idx == 0) OCR1A = duty; else OCR1B = duty;
  digitalWrite(enable, HIGH);
}

static void shieldBegin() {
  pinMode(PIN_PWM_LEFT, OUTPUT);
  pinMode(PIN_PWM_RIGHT, OUTPUT);
  pinMode(PIN_EN_LEFT, OUTPUT);
  pinMode(PIN_EN_RIGHT, OUTPUT);
  digitalWrite(PIN_EN_LEFT, LOW);      // bridges off until commanded
  digitalWrite(PIN_EN_RIGHT, LOW);

  // Fast PWM, TOP = ICR1 (mode 14), non-inverting on both outputs,
  // prescaler 1. Timer0 keeps millis(); Timer1 is ours.
  TCCR1A = _BV(COM1A1) | _BV(COM1B1) | _BV(WGM11);
  TCCR1B = _BV(WGM13)  | _BV(WGM12)  | _BV(CS10);
  ICR1  = PWM_TOP;
  OCR1A = 0;
  OCR1B = 0;

  for (uint8_t i = 0; i < CHANNELS; i++) {
    motorValue[i] = 0;
    setMotorOutput(i, 0);
  }
}

#endif  // drive backend

// ============================================================== ARQ SERIAL
//
// SimHub's framing, reimplemented from `ArqSerial.h`:
//
//     01 01 <packet id> <length> <data...> <crc8>
//
// The checksum covers the id, the length and the data - NOT the two header
// bytes. It is CRC-8/DVB-S2 (polynomial 0xD5, not reflected, init 0). That
// was not guessable: `arq.py` had to ask the board, which rejected
// Dallas/Maxim, CRC-8/ATM and SAE-J1850 in turn before acknowledging this
// one. Computed bitwise here rather than carried as a 256-entry table,
// because a table is 256 chances to mistype a constant and this is not a
// throughput-limited link.

static uint8_t crc8Update(uint8_t crc, uint8_t value) {
  crc ^= value;
  for (uint8_t bit = 0; bit < 8; bit++) {
    crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0xD5) : (uint8_t)(crc << 1);
  }
  return crc;
}

// Rejection reasons, sent back in a NACK. The host distinguishes them, and
// reason 4 in particular is what let it discover the polynomial at all, so
// these numbers are wire format and not diagnostics.
#define NACK_NO_PACKET_ID   0x01
#define NACK_BAD_LENGTH     0x02
#define NACK_NO_CHECKSUM    0x03
#define NACK_BAD_CHECKSUM   0x04
#define NACK_INCOMPLETE     0x05

#define MAX_PAYLOAD         32
#define DATA_BUFFER_SIZE    32

static uint8_t  partialData[MAX_PAYLOAD];
static int      lastValidPacket = 255;

// Accepted payloads accumulate here and the command layer reads from it, so
// a command's arguments may arrive in a later frame than its opcode. That is
// not incidental - it is why the hello handler's stray read can swallow the
// first byte of the *next* packet, a fault that ran for weeks on the host
// side before `hello_payload` grew its third byte.
static uint8_t  dataBuffer[DATA_BUFFER_SIZE];
static uint8_t  dataHead = 0, dataTail = 0, dataCount = 0;

static void bufferPush(uint8_t value) {
  if (dataCount >= DATA_BUFFER_SIZE) return;   // drop rather than wrap over
  dataBuffer[dataHead] = value;
  dataHead = (uint8_t)((dataHead + 1) % DATA_BUFFER_SIZE);
  dataCount++;
}

static int bufferPop() {
  if (dataCount == 0) return -1;
  uint8_t value = dataBuffer[dataTail];
  dataTail = (uint8_t)((dataTail + 1) % DATA_BUFFER_SIZE);
  dataCount--;
  return (int)value;
}

static void sendAck(uint8_t packetId) {
  Serial.write(0x03);
  Serial.write(packetId);
  Serial.flush();
}

static void sendNack(uint8_t lastKnownValid, uint8_t reason) {
  Serial.write(0x04);
  Serial.write(lastKnownValid);
  Serial.write(reason);
  Serial.flush();
}

// One byte off the UART, waiting up to 100 ms. Mid-frame only: a frame that
// stalls here is reported as incomplete rather than left half-applied.
static int rawTimedRead() {
  unsigned long start = millis();
  do {
    int c = Serial.read();
    if (c >= 0) return c;
  } while (millis() - start < 100);
  return -1;
}

// **Every well-formed frame is acknowledged, including one whose id is out
// of sequence - it is simply not applied.** Skipping the ack for a duplicate
// would look identical to a dead board from the host's side, and the host
// treats an unanswered frame as a lost link.
static void processIncoming() {
  while (Serial.available() > 0) {
    if (rawTimedRead() != 0x01) continue;
    if (rawTimedRead() != 0x01) return;

    uint8_t reason = 0;
    int packetId = 0, length = 0, crc = 0;

    packetId = rawTimedRead();
    if (packetId < 0) reason = NACK_NO_PACKET_ID;

    if (!reason) {
      length = rawTimedRead();
      if (length <= 0 || length > MAX_PAYLOAD) reason = NACK_BAD_LENGTH;
    }

    if (!reason) {
      for (int i = 0; i < length; i++) {
        int res = rawTimedRead();
        if (res < 0) { reason = NACK_INCOMPLETE; break; }
        partialData[i] = (uint8_t)res;
      }
    }

    if (!reason) {
      crc = rawTimedRead();
      if (crc < 0) reason = NACK_NO_CHECKSUM;
    }

    if (!reason) {
      uint8_t computed = 0;
      computed = crc8Update(computed, (uint8_t)packetId);
      computed = crc8Update(computed, (uint8_t)length);
      for (int i = 0; i < length; i++) {
        computed = crc8Update(computed, partialData[i]);
      }
      if ((uint8_t)crc != computed) reason = NACK_BAD_CHECKSUM;
    }

    if (!reason) {
      int expected = (lastValidPacket > 127) ? 0 : lastValidPacket + 1;
      // 255 is the broadcast id: accepted whatever was expected next. It is
      // the host's resync escape hatch, and its handshake opens with it,
      // because nothing can know where the sequence stands on a board that
      // has been talking to something else all week.
      if (packetId == expected || packetId == 255) {
        for (int i = 0; i < length; i++) bufferPush(partialData[i]);
        lastValidPacket = packetId;
      }
      sendAck((uint8_t)packetId);
    } else {
      sendNack((uint8_t)lastValidPacket, reason);
    }
  }
}

// One payload byte, pumping the receiver while it waits. 400 ms, matching
// the old firmware: the host's hello latency of 417 ms was measured against
// exactly this timeout.
static int arqRead() {
  unsigned long start = millis();
  do {
    if (dataCount > 0) return bufferPop();
    processIncoming();
  } while (millis() - start < 400 || dataCount > 0);
  return -1;
}

static int arqAvailable() {
  if (dataCount == 0) processIncoming();
  return (int)dataCount;
}

// --------------------------------------------------------- outgoing packets
//
// The markers the host's `split_packets` cuts the stream on:
//   08 <value>              a single value
//   06 <len> <bytes...> 20  a string, with a trailing 0x20 separator
//   03 <id> / 04 <id> <why> ack and nack, above

static void writeValue(uint8_t data) {
  Serial.write(0x08);
  Serial.write(data);
  Serial.flush();
}

static void writeString(const char *str) {
  uint8_t len = (uint8_t)strlen(str);
  Serial.write(0x06);
  Serial.write(len);
  Serial.write((const uint8_t *)str, len);
  Serial.write(0x20);
  Serial.flush();
}

static void writeStringLn(const char *str) {
  uint8_t len = (uint8_t)strlen(str);
  Serial.write(0x06);
  Serial.write((uint8_t)(len + 1));
  Serial.write((const uint8_t *)str, len);
  Serial.write('\n');
  Serial.write(0x20);
  Serial.flush();
}

// ================================================================ COMMANDS

// **The stray read is not a bug and must stay.** `Command_Hello` pops one
// byte before answering, so the host sends a three-byte hello whose third
// byte is padding. Removing the read here would make this firmware
// incompatible with the host that is already deployed - it would eat the
// first byte of whatever came next instead.
static void commandHello() {
  arqRead();
  delay(10);
  writeValue((uint8_t)FIRMWARE_VERSION);
}

static void commandAcq() { writeValue(0x03); }

static void commandDeviceName() {
  writeString(DEVICE_NAME);
  writeString("\n");
}

static void commandUniqueId() {
  writeString(DEVICE_UNIQUE_ID);
  writeString("\n");
}

// The signature bytes of the part this is running on, read from the headers
// the compiler defines - so a board swap reports the board it swapped to.
static void commandMcuType() {
  writeValue((uint8_t)SIGNATURE_0);
  writeValue((uint8_t)SIGNATURE_1);
  writeValue((uint8_t)SIGNATURE_2);
}

static void commandExpandedList() {
  writeStringLn("mcutype");
  writeStringLn("keepalive");
  writeStringLn("shieldfreq");
  writeStringLn("shielddump");
  writeValue('\n');
}

// **What the shield is actually running at, read back off the chip.**
//
// Not a diagnostic nicety. The whole point of this firmware is a frequency
// change, and without this the claim "1526 Hz" rests entirely on the number
// in the source reaching the part - which nothing verifies, because an I2C
// write that goes nowhere is silent and the board would acknowledge every
// frame exactly as it does now.
//
// Two bytes: PRESCALE, then MODE1. Frequency is 25e6/(4096*(prescale+1)), so
// prescale 3 is 1525.9 Hz and prescale 4 is 1220.7. **A prescale of 0 means
// the read failed** - nothing answered at 0x60 - and is the one value that
// cannot be a real setting, since the datasheet floor is 3.
static void commandShieldFreq() {
#ifdef DRIVE_ADAFRUIT_SHIELD
  writeValue(pcaRead(PCA9685_PRESCALE));
  writeValue(pcaRead(PCA9685_MODE1));
#else
  // TOP is what sets the frequency here, so it is what gets reported:
  // f = 16 MHz / (TOP + 1). Sent low byte first. The third value is the
  // timer's own mode register, which proves the timer was actually
  // configured rather than left in the core's default 490 Hz state - the
  // same question the PCA9685 prescale answered on the old board.
  writeValue((uint8_t)(ICR1 & 0xFF));
  writeValue((uint8_t)(ICR1 >> 8));
  writeValue(TCCR1B);
#endif
}

// **The registers M1 and M2 are actually holding, read back off the chip.**
//
// 6 Sep 2026: the right fan (M2) did not turn while the left one did, and
// 767 of 767 frames were acknowledged - because an ACK is sent when the FRAME
// ARRIVES, before any motor is touched. It says nothing about the outputs.
//
// This is what tells the two candidate faults apart without a meter. If M2's
// registers match M1's, the firmware is writing what it should and the fault
// is past the chip - the H-bridge channel, the wiring, or the fan. If they
// differ, the fault is here.
//
// Twelve channels' worth would not fit a useful reply, so it dumps the six
// that matter, PWM/IN2/IN1 for M1 then the same for M2, four registers each
// (ON_L, ON_H, OFF_L, OFF_H) in that order. Bit 4 of an _H register is the
// part's full-on/full-off flag rather than a count.
static void commandShieldDump() {
#ifdef DRIVE_ADAFRUIT_SHIELD
  static const uint8_t DUMP[6] = { 8, 9, 10, 13, 12, 11 };
  for (uint8_t i = 0; i < 6; i++) {
    uint8_t base = (uint8_t)(PCA9685_LED0_ON_L + 4 * DUMP[i]);
    for (uint8_t r = 0; r < 4; r++) writeValue(pcaRead((uint8_t)(base + r)));
  }
#else
  // The same question on the new hardware: what are the outputs actually
  // holding? Compare duty against TOP, and the enable state says whether
  // the bridge is driving at all. Left channel then right: duty low, duty
  // high, enabled.
  writeValue((uint8_t)(OCR1A & 0xFF));
  writeValue((uint8_t)(OCR1A >> 8));
  writeValue((uint8_t)digitalRead(PIN_EN_LEFT));
  writeValue((uint8_t)(OCR1B & 0xFF));
  writeValue((uint8_t)(OCR1B >> 8));
  writeValue((uint8_t)digitalRead(PIN_EN_RIGHT));
#endif
}

// Feature letters. G gear, N name, I unique id, J buttons, P custom
// protocol, X expanded, V motors. Unchanged from the SimHub build even where
// this firmware has nothing behind the letter, because the host's device
// record was written against this exact set.
static void commandFeatures() {
  delay(10);
  writeValue('G'); writeValue('N'); writeValue('I'); writeValue('J');
  writeValue('P'); writeValue('X'); writeValue('V');
  writeString("\n");
}

// **A partial frame leaves the deadman un-fed on purpose.** If a byte times
// out mid-frame the channels already written keep their new values, but
// `lastMotorsRead` is not touched - so if nothing completes within the
// safety delay, everything is zeroed. Half a command is not a command.
static void commandMotorsSet() {
  for (uint8_t i = 0; i < CHANNELS; i++) {
    int value = arqRead();
    if (value < 0) return;
#if WIND_RAMP_STEP > 0
    // Rises are capped; falls are immediate. See WIND_RAMP_STEP.
    if (value > (int)motorValue[i] &&
        value - (int)motorValue[i] > WIND_RAMP_STEP) {
      value = (int)motorValue[i] + WIND_RAMP_STEP;
    }
#endif
    setMotorOutput(i, (uint8_t)value);
  }
  lastMotorsRead = millis();
}

// The reply the host parses in `parse_motors_count` / `parse_motors_board`,
// in this order and no other:
//     08 ff   08 04   06 19 "Adafruit Motor Shield V2;" 20   08 0a
// The leading 255 is a marker, not a count - the host skips it, and an
// earlier version of the host that did not skip it read 8 channels off a
// hello reply and drove nothing for a whole session.
static void commandMotorsCount() {
  writeValue(255);
  writeValue(CHANNELS);
  writeString(MOTOR_BOARD_NAME ";");
  writeValue('\n');
}

static void commandMotors() {
  int action = arqRead();
  if (action == 'C')      commandMotorsCount();
  else if (action == 'S') commandMotorsSet();
}

static void safetyCheck() {
  if (lastMotorsRead > 0 &&
      (millis() - lastMotorsRead) > SAFETY_DELAY_MS) {
    for (uint8_t i = 0; i < CHANNELS; i++) setMotorOutput(i, 0);
    lastMotorsRead = 0;
  }
}

// ==================================================================== main

#define MESSAGE_HEADER 0x03

void setup() {
  Serial.begin(BOOT_BAUD);
  shieldBegin();
}

void loop() {
  safetyCheck();

  if (arqAvailable() > 0) {
    if (arqRead() == MESSAGE_HEADER) {
      int opt = arqRead();
      if (opt == '1')      commandHello();
      else if (opt == 'V') commandMotors();
      else if (opt == 'A') commandAcq();
      else if (opt == 'N') commandDeviceName();
      else if (opt == 'I') commandUniqueId();
      else if (opt == '0') commandFeatures();
      else if (opt == 'X') {
        // An expanded command is a word terminated by space or newline.
        char word[16];
        uint8_t pos = 0;
        int c = arqRead();
        while (c >= 0 && c != ' ' && c != '\n' && pos < sizeof(word) - 1) {
          word[pos++] = (char)c;
          c = arqRead();
        }
        word[pos] = 0;
        if (!strcmp(word, "list"))            commandExpandedList();
        else if (!strcmp(word, "mcutype"))    commandMcuType();
        else if (!strcmp(word, "shieldfreq")) commandShieldFreq();
        else if (!strcmp(word, "shielddump")) commandShieldDump();
      }
    }
  }
}
