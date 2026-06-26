# Technical Specification

## GT7 Pit Crew Race Engineer Application

### 1. Product Vision

Build a personalised GT7 pit crew application that helps the driver plan, tune, practise, qualify, and race.

The application must act as:

1. **Setup engineer**
   Builds car setup recommendations based on track, car, race rules, tyre compound, fuel/tyre multipliers, and the driver's known driving style.

2. **Telemetry logger**
   Records live GT7 telemetry during practice, qualifying, and race sessions.

3. **AI race engineer**
   Combines telemetry data and driver feedback to recommend setup changes, strategy changes, and driver coaching.

4. **Race strategist**
   Produces multiple race strategy options and dynamically updates advice during the race.

5. **Voice companion**
   Provides real-time spoken updates and allows push-to-talk questions during sessions.

---

# 2. Core User Profile

The system is designed for a GT7 driver who prefers:

* Trail braking
* Strong front-end bite on corner entry
* Smooth progressive throttle
* Stable rear platform
* Rotation without snap oversteer
* Race setups that balance lap speed, tyre life, fuel use, and consistency

This driver profile must be stored and used by the AI setup and coaching system.

---

# 3. Core Modules

## 3.1 Race Setup Planner

### Purpose

Allow the user to create a race event profile and receive a recommended GT7 car setup.

### Inputs

The user must be able to enter:

* Track
* Track layout
* Car
* Car category
* Race duration type:

  * Timed race
  * Lap race
* Race length:

  * Minutes
  * Laps
* Tyre wear multiplier
* Fuel consumption multiplier
* Refuel rate
* Available tyre compounds
* Required tyre compounds
* Mandatory pit stops
* BoP on/off
* Tuning allowed yes/no
* Weather:

  * Fixed
  * Random
  * Wet risk
* Time of day
* Damage setting
* Starting fuel
* Driver style profile

### Output

The application should generate:

* Recommended suspension setup
* Differential setup
* Brake balance recommendation
* Aero balance
* Gearbox approach
* Ballast/power restriction advice where applicable
* Tyre strategy implications
* Fuel-saving notes
* Setup reasoning in plain English
* Suggested practice test plan

### Example Output Sections

* "Base Setup"
* "Why this suits your driving style"
* "What to test first"
* "Watch for these handling symptoms"
* "Expected tyre behaviour"
* "Expected fuel behaviour"

---

# 4. Practice Session Logger

## 4.1 Purpose

Record user practice sessions with a selected setup and tyre compound.

## 4.2 Practice Flow

1. User selects event profile.
2. User selects car setup.
3. Default tyre compound loads from setup.
4. User may override tyre compound before session.
5. User starts session.
6. App records telemetry.
7. App detects laps and stores lap-by-lap data.
8. User ends session.
9. App prompts for driver feedback.

## 4.3 Driver Feedback Form

After each stint, the app should ask:

* How was corner entry?
* How was mid-corner rotation?
* How was throttle exit stability?
* Did the rear feel loose?
* Did the front wash wide?
* Did tyres overheat?
* Did fuel use feel too high?
* Did the car suit your driving style?
* Free text feedback

Feedback options should include:

* Too much understeer
* Too much oversteer
* Rear unstable under braking
* Poor traction
* Front tyres overheating
* Rear tyres overheating
* Good balance
* Needs more rotation
* Needs more stability
* Gearbox too short
* Gearbox too long

---

# 5. Telemetry System

## 5.1 Telemetry Capture

The application must connect to GT7 telemetry over the local network.

### Required Telemetry Fields

Where available from the GT7 telemetry stream, capture:

* Timestamp
* Session ID
* Lap number
* Current lap time
* Last lap time
* Best lap time
* Speed
* Gear
* RPM
* Throttle position
* Brake pressure
* Steering angle
* Fuel remaining
* Fuel usage rate
* Tyre temperatures
* Tyre compound selected by user
* Suspension travel
* Yaw rate
* Car position
* Track position
* Distance around lap
* Acceleration
* Brake zones
* Throttle zones
* Coasting zones

### Derived Metrics

The app must calculate:

* Fuel used per lap
* Estimated laps remaining
* Average lap time
* Best theoretical lap
* Lap delta to best lap
* Sector delta where possible
* Tyre temperature trend
* Tyre degradation proxy
* Brake consistency
* Throttle smoothness
* Corner entry stability
* Exit traction quality
* Time lost by corner/segment
* Fuel target versus actual use
* Pit window estimate

---

# 6. AI Setup Analysis

## 6.1 Purpose

Combine telemetry and driver feedback to suggest setup changes.

## 6.2 AI Input Package

When sending data to AI, include:

* Event profile
* Track
* Car
* Current setup
* Driver style profile
* Tyre compound
* Session type
* Lap telemetry summary
* Best lap telemetry
* Average lap telemetry
* Worst lap telemetry
* Fuel usage
* Tyre temperature trends
* Driver feedback
* Handling complaints
* Previous setup changes
* Previous AI recommendations

## 6.3 AI Output

AI should return:

* Recommended setup changes
* Reason for each change
* Expected handling effect
* Risk of each change
* Priority order
* Test plan for next stint
* Driver coaching points
* Strategy impact

### Example

> Increase rear braking sensitivity slightly to improve trail-braking rotation, but monitor rear stability into heavy braking zones.

---

# 7. Race Strategy Generator

## 7.1 Purpose

Once the user is happy with setup and has completed enough laps, the app generates three race strategy options.

## 7.2 Strategy Inputs

* Race duration
* Average lap time
* Best sustainable lap time
* Fuel per lap
* Tyre wear trend
* Tyre temperature behaviour
* Pit loss estimate
* Refuel rate
* Tyre compounds available
* Required compounds
* Mandatory stops
* Weather risk
* User consistency
* Driver preference:

  * Safe
  * Balanced
  * Aggressive

## 7.3 Output

The app must provide three options:

### Strategy A: Safe

* Lower risk
* More fuel margin
* Conservative tyre use
* Stable lap targets

### Strategy B: Balanced

* Best projected overall race time
* Reasonable fuel margin
* Moderate tyre risk

### Strategy C: Aggressive

* Fastest theoretical strategy
* Higher tyre/fuel risk
* Requires consistent pace

Each strategy must include:

* Starting tyre
* Pit lap or pit window
* Tyres for each stint
* Fuel target per stint
* Refuel amount
* Target lap time
* Fuel-saving requirement
* Positives
* Negatives
* Risk rating
* Recommended use case

---

# 8. Save Race Plan

Once the user selects a strategy, save:

* Event profile
* Final setup
* Selected strategy
* Target lap times
* Fuel targets
* Pit windows
* Tyre plan
* AI notes
* Driver notes

This saved plan becomes the active race plan for race day.

---

# 9. Live Session Modes

The live tab must allow manual selection of:

1. Practice
2. Qualifying
3. Race

---

## 9.1 Practice Mode

### Purpose

Coach the driver during practice.

### Features

* Log telemetry
* Show lap delta to best lap
* Show tyre temperatures
* Show fuel use
* Give driver coaching
* Identify where time is being lost
* Compare current lap to best lap
* Suggest driving improvements

### Voice Examples

* "You're losing time on corner exit. Try getting back to throttle smoother."
* "Front tyres are getting hot. Brake a touch earlier and release more progressively."
* "Fuel use is higher than target. Short shift two hundred RPM earlier on the next lap."

---

## 9.2 Qualifying Mode

### Purpose

Help the driver hit a target qualifying lap.

### Setup

User can select:

* Use best practice lap as target
* Manually enter target lap time

### Features

* Out lap calming/motivation voice
* Live delta against target
* Sector/segment performance where possible
* Push advice during lap
* Reduce chatter during critical corners

### Voice Examples

* "Good exit. You're two tenths up."
* "Breathe. Build tyre temperature. No need to rush this out lap."
* "You're down one tenth. Focus on clean exit, not over-driving."

---

## 9.3 Race Mode

### Purpose

Act as a full race engineer.

### If Strategy Is Loaded

The app must:

* Track actual pace versus target
* Track fuel use versus target
* Track tyre condition proxy
* Adjust fuel advice dynamically
* Confirm pit window
* Tell user when to box
* Tell user what tyres to fit
* Tell user how much fuel to add
* Recalculate strategy if pace/fuel changes
* Warn if strategy is becoming impossible
* Suggest push/save phases

### If No Strategy Is Loaded

The app must ask:

* Race type:

  * Timed
  * Lap race
* Race length:

  * Minutes
  * Laps
* Tyres being used
* Starting fuel if needed

Then it should provide:

* Lap delta to best lap
* Fuel remaining estimate
* Fuel needed to finish
* Pit fuel amount
* Basic pit advice

---

# 10. Push-to-Talk Race Engineer

## 10.1 Purpose

Allow the user to ask race engineer questions verbally during the session.

## 10.2 Required Questions

The app should support:

* "How many laps left?"
* "How much fuel left?"
* "Can I make it to the end?"
* "When is my next pit?"
* "What tyres next?"
* "How much fuel do I need?"
* "How am I going against strategy?"
* "Should I push?"
* "Should I save fuel?"
* "What's my lap delta?"
* "What was my last lap?"
* "What's my best lap?"
* "How are my tyres?"
* "What position am I?"
* "What should I change in the setup?"
* "Where am I losing time?"

## 10.3 Response Requirements

Responses must be:

* Short
* Clear
* Spoken naturally
* Useful during racing
* Not overly verbose
* Able to be interrupted

Example:

> "You need 18 litres to finish safely. Add 20 if you want margin."

---

# 11. Learning System

## 11.1 Purpose

The application must improve over time based on the driver's data.

## 11.2 Store Over Time

* Driver profile
* Track history
* Car history
* Setup history
* Tyre wear patterns
* Fuel use patterns
* Lap consistency
* Feedback history
* AI recommendations
* Successful strategies
* Failed strategies
* Preferred setup traits

## 11.3 Learning Outputs

The app should gradually improve:

* Setup recommendations
* Fuel predictions
* Tyre life predictions
* Lap target predictions
* Coaching advice
* Strategy generation
* Driver-specific tuning language

---

# 12. User Interface

## 12.1 Main Tabs

Recommended tabs:

1. Dashboard
2. Event Planner
3. Garage
4. Setup Builder
5. Practice Review
6. Strategy Builder
7. Live Race Engineer
8. History
9. Settings

---

## 12.2 Dashboard

Show:

* Next saved race
* Active car
* Active setup
* Active strategy
* Recent sessions
* Suggested next action

---

## 12.3 Event Planner

User creates or edits race event profiles.

---

## 12.4 Garage

Stores:

* Cars
* Car category
* Setups
* Notes
* Track-specific setup history

---

## 12.5 Setup Builder

Displays:

* Current setup
* AI recommended setup
* Setup change history
* Test plan

---

## 12.6 Practice Review

Shows:

* Lap table
* Best lap
* Average lap
* Fuel use
* Tyre temperature trends
* Driver feedback
* AI analysis
* Recommended next changes

---

## 12.7 Strategy Builder

Shows:

* Three race strategies
* Comparison table
* Pros and cons
* Select and save strategy button

---

## 12.8 Live Race Engineer

Shows:

* Session mode selector
* Current lap
* Last lap
* Best lap
* Delta
* Fuel remaining
* Fuel target
* Estimated laps remaining
* Tyre temperatures
* Pit window
* Next instruction
* Push-to-talk button
* Voice status

---

# 13. Data Model

## 13.1 UserProfile

Fields:

* id
* name
* driving_style_summary
* setup_preferences
* brake_bias_preference
* throttle_style
* trail_braking_preference
* stability_preference
* rotation_preference
* created_at
* updated_at

---

## 13.2 EventProfile

Fields:

* id
* name
* track
* layout
* car_id
* race_type
* race_length_laps
* race_length_minutes
* tyre_wear_multiplier
* fuel_multiplier
* refuel_rate
* available_tyres
* required_tyres
* mandatory_pit_stops
* bop_enabled
* tuning_enabled
* weather_type
* damage_setting
* notes

---

## 13.3 Car

Fields:

* id
* manufacturer
* model
* category
* drivetrain
* power
* weight
* pp
* notes

---

## 13.4 Setup

Fields:

* id
* car_id
* event_id
* name
* tyre_compound_default
* suspension_settings
* differential_settings
* aero_settings
* brake_balance
* gearbox_settings
* ballast_settings
* power_settings
* notes
* ai_reasoning
* created_at

---

## 13.5 Session

Fields:

* id
* event_id
* setup_id
* session_type
* tyre_compound
* start_time
* end_time
* notes

---

## 13.6 Lap

Fields:

* id
* session_id
* lap_number
* lap_time
* valid_lap
* fuel_used
* average_speed
* tyre_temp_average
* delta_to_best
* telemetry_summary

---

## 13.7 TelemetrySample

Fields:

* id
* session_id
* lap_id
* timestamp
* speed
* rpm
* gear
* throttle
* brake
* steering
* fuel
* tyre_temps
* suspension
* yaw_rate
* position
* distance_around_lap

---

## 13.8 DriverFeedback

Fields:

* id
* session_id
* corner_entry_rating
* mid_corner_rating
* exit_rating
* stability_rating
* tyre_feedback
* fuel_feedback
* free_text
* created_at

---

## 13.9 Strategy

Fields:

* id
* event_id
* setup_id
* name
* strategy_type
* stint_plan
* pit_windows
* fuel_targets
* tyre_plan
* target_lap_times
* positives
* negatives
* risk_rating
* selected_for_race

---

# 14. AI Integration

## 14.1 AI Functions Required

The app should have AI functions for:

1. Setup recommendation
2. Practice session analysis
3. Driver feedback interpretation
4. Setup change recommendation
5. Race strategy generation
6. Live race strategy recalculation
7. Driver coaching
8. Push-to-talk question answering

## 14.2 AI Guardrails

AI must not guess missing telemetry values.

If data is unavailable, AI should say:

> "This cannot be measured directly from telemetry. I am estimating based on available data."

AI must distinguish between:

* Measured data
* Calculated data
* Estimated data
* Driver feedback

---

# 15. Voice System

## 15.1 Speech-to-Text

Required for push-to-talk commands.

## 15.2 Text-to-Speech

Required for race engineer responses.

## 15.3 Voice Behaviour

Voice must be:

* Calm under pressure
* Short during race
* More detailed after session
* Motivational on out laps
* Clear about strategy

---

# 16. Technical Architecture

## 16.1 Recommended Stack

### Desktop MVP

* Frontend: React or Electron
* Backend: Node.js or Python
* Database: SQLite
* Telemetry service: Python recommended
* AI integration: OpenAI-compatible API layer
* Voice:

  * Local push-to-talk recording
  * Speech-to-text API
  * Text-to-speech API

### Reason

A desktop app is best for local network telemetry capture, file storage, voice input/output, and race-day reliability.

---

## 16.2 Core Services

1. Telemetry Listener Service
2. Session Recorder Service
3. Lap Analysis Service
4. Setup Recommendation Service
5. Strategy Engine
6. AI Analysis Service
7. Voice Command Service
8. Text-to-Speech Service
9. Data Storage Service
10. UI State Service

---

# 17. MVP Scope

## Phase 1: Foundation

Build:

* Event creation
* Car creation
* Setup storage
* Manual setup notes
* Telemetry connection
* Session recording
* Lap table
* Fuel per lap calculation
* Basic tyre temp display

---

## Phase 2: AI Setup Engineer

Build:

* Driver profile
* AI setup recommendation
* Driver feedback form
* AI practice analysis
* Setup change recommendations

---

## Phase 3: Strategy Builder

Build:

* Strategy generation
* Three strategy options
* Fuel calculations
* Pit window calculations
* Save selected race strategy

---

## Phase 4: Live Race Engineer

Build:

* Practice mode
* Qualifying mode
* Race mode
* Live delta
* Fuel target tracking
* Pit advice
* Voice alerts

---

## Phase 5: Push-to-Talk Engineer

Build:

* Push-to-talk input
* Speech-to-text
* Race question intent detection
* Spoken responses
* AI-enhanced race engineer answers

---

## Phase 6: Learning System

Build:

* Historical driver model
* Track/car-specific setup memory
* Fuel prediction improvements
* Tyre behaviour prediction
* Personalised coaching model

---

# 18. Key Calculations

## 18.1 Fuel Needed to Finish

Formula:

Fuel needed = average fuel per lap × laps remaining

Add safety margin:

Safe fuel = fuel needed × 1.05

---

## 18.2 Timed Race Laps Remaining

Formula:

Estimated laps remaining = remaining race time ÷ average lap time

Add final lap allowance if race rules require crossing the line after timer expires.

---

## 18.3 Refuel Amount

Formula:

Fuel to add = required fuel to complete stint - current fuel

Add margin based on strategy type:

* Safe: 8 percent margin
* Balanced: 5 percent margin
* Aggressive: 2 percent margin

---

## 18.4 Pit Window

Pit window should be based on:

* Fuel remaining
* Tyre temperature trend
* Tyre life estimate
* Strategy target
* Mandatory tyre requirement
* Pit loss
* Race time remaining

---

# 19. Non-Functional Requirements

## 19.1 Performance

* Telemetry should update live with minimal delay.
* Voice responses should be fast enough to be useful during a race.
* Data logging must not interrupt telemetry capture.

## 19.2 Reliability

* App must continue logging if AI service is unavailable.
* App must not crash if telemetry disconnects.
* App must reconnect automatically.
* Race mode must prioritise local calculations over AI if latency is high.

## 19.3 Privacy

* Store telemetry locally by default.
* Ask user before sending session data to AI.
* Allow deletion of sessions.
* Allow export of data.

## 19.4 Safety

* Race voice must not overload the driver with excessive talking.
* Critical calls should be short.
* App should have quiet zones during qualifying laps if needed.

---

# 20. Programmer Notes

The application should be built around a simple principle:

> Capture everything, summarise intelligently, speak only when useful.

The AI should not replace deterministic race calculations. Fuel, lap count, stint length, and pit timing should be calculated locally first. AI should add interpretation, setup reasoning, coaching, and strategy explanation.

The app must feel like a personal race engineer, not a generic dashboard.

---

# 21. Future Features

Possible future additions:

* Opponent tracking if available
* Weather prediction if telemetry allows
* Replay file import
* Setup comparison tool
* Automatic session type detection
* Discord export
* Race briefing PDF export
* Engineer personality options
* Team/league mode
* Cloud sync
* Mobile companion app
* VR-friendly audio-only mode

---

# 22. Open Questions

These should be confirmed before final development:

1. Will this be Windows-only for MVP?
2. Will the app use OpenAI API, local AI, or both?
3. Should voice work offline?
4. Should setup sheets match GT7's exact setup screen layout?
5. Should the app export setup and strategy reports as PDF?
6. Should it support multiple drivers or only one driver profile?
7. Should race engineer voice be serious, motivational, or customisable?
8. Should data sync between PC and mobile later?
9. Should it include NGR branding?
10. Should it eventually support league/team use?

---

# 23. Success Criteria

The app is successful when the user can:

1. Create a race event.
2. Select a car.
3. Generate a setup matched to track, car, and driving style.
4. Practise with that setup.
5. Record telemetry.
6. Add driver feedback.
7. Receive AI setup changes.
8. Build three race strategies.
9. Save a selected strategy.
10. Use live practice, qualifying, and race modes.
11. Ask push-to-talk race engineer questions.
12. Receive useful, dynamic, personalised race advice.
13. Improve over time as the app learns the driver.
