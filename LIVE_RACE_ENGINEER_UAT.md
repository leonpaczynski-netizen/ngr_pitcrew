# Live Race Engineer — User Acceptance Test
**Group 18F | Product: Next Gear Racing Pit Crew**
**Version:** 1.0 | **Date:** 2026-06-26 | **Tester:** _______________

## Purpose
Verify that the Live Race Engineer tab correctly receives telemetry, responds
to all PTT voice intents with accurate data, delivers proactive pit alerts at
the correct lap, and transitions PTT status correctly through the full cycle.

---

## Preconditions

| # | Requirement | Pass | Fail |
|---|---|---|---|
| P1 | App is launched; Live Race Engineer tab is shown first | | |
| P2 | GT7 is running; a race or practice session is in progress | | |
| P3 | UDP telemetry is connected — packet age label is green and updating | | |
| P4 | A microphone is connected and the OS has granted permission to the app | | |
| P5 | Speech-to-text service is configured in Settings → Voice Settings | | |
| P6 | Anthropic API key is set for intents that require AI (coaching, setup_advice) | | |
| P7 | Session Mode is set to match the GT7 session (Practice / Qualifying / Race) | | |
| P8 | For pit-alert and strategy intent tests: a strategy has been loaded and a race session is active | | |

---

## 1. Initial State — Live Race Engineer Tab

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 1.1 | Confirm Live Race Engineer is the first tab | Tab at index 0 is active on startup | | | |
| 1.2 | Inspect the PTT status label | Shows "RADIO READY" in green | | | |
| 1.3 | Inspect telemetry readouts: Lap number, Lap time, Fuel bar, Tyre temperature circles | All four tyre circles visible; fuel bar visible; lap number shows current GT7 lap | | | |
| 1.4 | Confirm packet age indicator | Green; updating at least once per second | | | |
| 1.5 | Inspect Session Mode selector | Shows Practice, Qualifying, or Race — matches GT7 session type | | | |

---

## 2. PTT Status Cycle

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 2.1 | Press the PTT button (or configured keyboard hotkey) | PTT status label changes from "RADIO READY" to "TRANSMITTING" (amber/yellow); 440 Hz beep heard | | | |
| 2.2 | Speak a short phrase ("fuel check") while status is TRANSMITTING | Microphone is recording | | | |
| 2.3 | Release PTT or wait for auto-stop | Status changes to "PROCESSING" | | | |
| 2.4 | Wait for speech recognition and intent match | Status changes to "ENGINEER RESPONDING" (blue) | | | |
| 2.5 | Wait for text-to-speech to finish | Status returns to "RADIO READY" (green) | | | |
| 2.6 | Confirm no status gets "stuck" | Full cycle completes within 15 s under normal conditions | | | |

---

## 3. Intent: Fuel

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 3.1 | Press PTT; say "how much fuel do I have?" | Intent matched: **fuel** | | | |
| 3.2 | Listen to response | Response states current fuel level in litres and estimated laps remaining | | | |
| 3.3 | Confirm values are plausible | Litres ≤ tank capacity; lap estimate = fuel / avg_fuel_per_lap | | | |
| 3.4 | Repeat with "tank" as trigger word | Same response type | | | |

---

## 4. Intent: Position

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 4.1 | Press PTT; say "what position am I in?" | Intent matched: **position** | | | |
| 4.2 | Listen to response | "You are P{n} of {total} cars" or equivalent | | | |
| 4.3 | Cross-check with GT7 HUD | Position number matches GT7 display | | | |

---

## 5. Intent: Laps Remaining

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 5.1 | In a Lap Race, press PTT; say "how many laps remaining?" | Intent matched: **laps** | | | |
| 5.2 | Listen to response | Exact lap count remaining stated | | | |
| 5.3 | In a Timed Race, press PTT; say "how many laps remaining?" | Response gives an estimated lap count based on time remaining and average lap time | | | |

---

## 6. Intent: Time Remaining

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 6.1 | Press PTT; say "how much time remaining?" | Intent matched: **time** | | | |
| 6.2 | Listen to response | Race time remaining stated in minutes and seconds | | | |
| 6.3 | Confirm value updates each call | Repeated calls give decreasing time values | | | |

---

## 7. Intent: Best Lap

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 7.1 | Complete at least 2 laps; press PTT; say "what is my best lap?" | Intent matched: **best** | | | |
| 7.2 | Listen to response | Best lap time stated in m:ss.mmm format | | | |
| 7.3 | Cross-check with GT7 HUD best lap display | Times match | | | |

---

## 8. Intent: Pit Window

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 8.1 | With a strategy loaded, press PTT; say "when should I pit?" | Intent matched: **pit**; rule-based response (no AI call) | | | |
| 8.2 | Listen to response | Response states the lap to pit, next compound, or whether all stops are done | | | |
| 8.3 | Confirm no AI API call is made | AI Log tab does NOT show a new entry for this intent | | | |
| 8.4 | With no strategy loaded, say "pit stop" | Response: "No strategy loaded. Pit when you judge." or similar | | | |
| 8.5 | When all planned stops are done, say "when should I pit?" | Response: "All planned stops done. Push to the flag." or similar | | | |

---

## 9. Intent: Strategy

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 9.1 | Press PTT; say "what is the plan?" | Intent matched: **strategy** | | | |
| 9.2 | Listen to response | Current stint info: compound, laps remaining in stint, next stop lap | | | |
| 9.3 | With no strategy loaded, say "what's the plan?" | Graceful response: "No strategy loaded" or similar; no crash | | | |

---

## 10. Intent: Pace

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 10.1 | Press PTT; say "how am I going?" | Intent matched: **pace** | | | |
| 10.2 | Listen to response | Current pace vs target assessment; delta mentioned if strategy is loaded | | | |

---

## 11. Intent: Tyre State

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 11.1 | After 2+ laps, press PTT; say "how are my tyres?" | Intent matched: **tyre_state** | | | |
| 11.2 | Listen to response | Each tyre corner (FL, FR, RL, RR) mentioned with temperature state (COLD, OPTIMAL, HOT) | | | |
| 11.3 | Confirm tyre temperature circles on the Live tab | Circles show colour changes matching temperature (blue→green→red) | | | |

---

## 12. Intent: Fuel Check (Strategy Target)

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 12.1 | With a strategy loaded, press PTT; say "fuel check" | Intent matched: **fuel_check** | | | |
| 12.2 | Listen to response | Response compares current fuel burn rate vs strategy target; states whether ahead or behind target | | | |

---

## 13. Intent: Lap Analysis

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 13.1 | Complete a lap; press PTT; say "how was my last lap?" | Intent matched: **lap_analysis** | | | |
| 13.2 | Listen to response | Last lap delta and any problem areas mentioned | | | |

---

## 14. Intent: Coaching (AI Call)

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 14.1 | Press PTT; say "give me some tips" | Intent matched: **coaching**; AI API call made | | | |
| 14.2 | Wait for response (up to 30 s) | Sector-specific coaching advice delivered via TTS | | | |
| 14.3 | Confirm AI Log entry | Feature = "Driver Coaching"; success = true; session_id populated | | | |
| 14.4 | Say "how can I go faster in the last sector?" | Coaching response with sector context | | | |

---

## 15. Intent: Setup Advice (AI Call)

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 15.1 | Press PTT; say "any setup advice?" | Intent matched: **setup_advice**; AI API call made | | | |
| 15.2 | Wait for response (up to 30 s) | Setup adjustment suggestions delivered via TTS | | | |
| 15.3 | Confirm AI Log entry | Feature = "Setup Advice" or "Driver Feeling"; success = true | | | |

---

## 16. Prior Context Injection — Coaching

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 16.1 | After at least one prior coaching AI call, press PTT; say "coaching" again | Second AI call made | | | |
| 16.2 | Check AI Log prompt for the second call | Prompt contains a "Previous AI Recommendations" or "Prior Advice" section with the earlier recommendation injected | | | |

---

## 17. Proactive Pit Alert

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 17.1 | With a strategy loaded (e.g., pit on lap 12), race to 2 laps before the pit lap (lap 10) | App is tracking laps | | | |
| 17.2 | Complete lap 10 | TTS automatically announces a pit window alert without pressing PTT: "Pit window opens in 2 laps. Box on lap 12. Fit {compound}." or equivalent | | | |
| 17.3 | Confirm the alert fires only once | Alert does not repeat on lap 11, 12, etc. | | | |

---

## 18. Unrecognised Intent

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 18.1 | Press PTT; say a phrase with no intent keywords (e.g., "hello there") | No match; graceful fallback response: "Sorry, I didn't understand that" or similar; no crash | | | |
| 18.2 | Confirm PTT status returns to "RADIO READY" | Status cycles correctly even on no-match | | | |

---

## 19. Telemetry Disconnected — Failure Mode

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 19.1 | Stop GT7 or disconnect UDP; wait 5 s | Packet age label turns red or shows "No packets" | | | |
| 19.2 | Press PTT; say "fuel check" | Response uses last-known data or states "telemetry not available"; no crash | | | |
| 19.3 | Reconnect GT7 | Packet age label returns to green; live data resumes | | | |

---

## 20. Microphone / STT Failure Mode

| Step | Description | Expected Result | Pass | Fail | Notes |
|---|---|---|---|---|---|
| 20.1 | Disconnect or mute the microphone at OS level | Microphone unavailable | | | |
| 20.2 | Press PTT | Status changes to TRANSMITTING; no beep (or silent beep) | | | |
| 20.3 | Observe result | Error message or TTS fallback: "Could not capture audio" or similar; no crash; status returns to RADIO READY | | | |

---

## Summary

| Section | Description | Pass | Fail | Defects |
|---|---|---|---|---|
| 1 | Initial state | | | |
| 2 | PTT status cycle | | | |
| 3 | Fuel intent | | | |
| 4 | Position intent | | | |
| 5 | Laps remaining | | | |
| 6 | Time remaining | | | |
| 7 | Best lap | | | |
| 8 | Pit window | | | |
| 9 | Strategy | | | |
| 10 | Pace | | | |
| 11 | Tyre state | | | |
| 12 | Fuel check | | | |
| 13 | Lap analysis | | | |
| 14 | Coaching (AI) | | | |
| 15 | Setup advice (AI) | | | |
| 16 | Prior context injection | | | |
| 17 | Proactive pit alert | | | |
| 18 | Unrecognised intent | | | |
| 19 | Telemetry disconnected | | | |
| 20 | Microphone failure | | | |

**Overall result:** PASS / FAIL

---

## Defect Register

| ID | Section | Step | Description | Severity | Status | Root Cause | Fix |
|---|---|---|---|---|---|---|---|
| LRE-001 | | | | | | | |

---

## Tester Notes

_Free-form observations, microphone model, speech-to-text service used, GT7 version, track, session type:_
