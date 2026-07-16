"""User Guide HTML content (static).

Extracted from ui/dashboard.py (audit item 7, decomposition slice 1) so the
main-window module carries orchestration, not a ~160-line content blob.
Pure content; imported by MainWindow._build_guide_reference_widget.
"""
from __future__ import annotations

GUIDE_HTML = """<style>
  body  { background:#0D1B2A; color:#E0E0E0; font-family:'Segoe UI',sans-serif; font-size:12px; }
  h1    { color:#2EA043; font-size:18px; margin-bottom:4px; }
  h2    { color:#AAE4AA; font-size:14px; margin-top:18px; margin-bottom:4px;
          border-bottom:1px solid #3A3A3A; padding-bottom:2px; }
  h3    { color:#F5C542; font-size:12px; margin-top:12px; margin-bottom:2px; }
  table { border-collapse:collapse; width:100%; margin-top:6px; }
  th    { background:#1F4E78; color:white; padding:5px 8px; text-align:left; }
  td    { padding:4px 8px; border-bottom:1px solid #333; vertical-align:top; }
  tr:nth-child(even) td { background:#111D2A; }
  .kw   { color:#AAE4AA; font-weight:bold; }
  .note { color:#888; font-size:11px; }
  ul    { margin:4px 0 4px 20px; padding:0; }
  li    { margin-bottom:2px; }
  .tag  { background:#1F4E78; color:white; padding:1px 5px; border-radius:3px;
          font-size:11px; }
  .warn { color:#F5C542; }
  .step { color:#F5C542; font-weight:bold; }
</style>

<h1>Next Gear Racing Pit Crew — User Guide</h1>
<p class="note">Real-time race engineer for Gran Turismo 7. Reads UDP telemetry from your PS5
and gives voice alerts. Fully local, offline and deterministic — no AI, no internet,
no API key.</p>

<p class="note"><b>Tool tabs (⚙):</b> tabs whose name starts with a gear symbol —
<b>⚙ Telemetry</b>, <b>⚙ Diagnostics</b> and <b>⚙ Track Modelling</b> —
are advanced tools for checking raw data and troubleshooting. They are safe to
ignore during a normal race weekend; the workflow below never requires them.</p>

<h2>How to use this app — 10-step workflow</h2>
<p>The app is event-centred: every tab draws its context from the <b>active event</b>.
Set an event first, then every other tab fills in automatically.</p>

<h3><span class="step">Step 1</span> &nbsp; Event Planner — create your event profile</h3>
<p>Go to <b>Event Planner</b> (first tab). Create an entry for each race you plan to enter:</p>
<ul>
  <li><b>Track</b> and <b>Car</b> — pick from the lists. Use <b>← Garage</b> next to Car to browse specs first.</li>
  <li><b>Race Type</b> — Lap Race or Timed Race; set total laps or duration.</li>
  <li><b>Tyre Wear / Fuel Multiplier</b> — match the GT7 lobby settings exactly.</li>
  <li><b>Available Tyres</b> — e.g. <span class="kw">RS, RM, RH</span></li>
  <li><b>Required Tyre</b> — mandatory compound if the event enforces one.</li>
  <li><b>Refuel Rate</b> — litres per second your pit crew delivers (check replay or use 10 L/s as default).</li>
</ul>
<p>When the event is ready, click <b>Set as Active</b>. All downstream tabs update instantly.</p>

<h3><span class="step">Step 2</span> &nbsp; Garage — pick your car</h3>
<p>Switch to <b>Garage</b>. Browse your cars, read specs, check BOP data.
When you find the car for this event, click <b>Load to Event ↩</b> — the car name
flows back to the Event Planner and the Strategy Builder.</p>
<p class="note">The "Load to Event ↩" button only appears when an event is active.</p>

<h3><span class="step">Step 3</span> &nbsp; Setup Builder — build or tune a setup</h3>
<p>Switch to <b>Setup Builder</b>. The yellow banner at the top confirms which event is active.
The car field is already populated from your event.</p>
<ul>
  <li>Use the <b>Setup Builder</b> to create or load a setup for the session (qualifying or race).</li>
  <li>Drive the setup. If something feels wrong, note it in <b>How does the car feel?</b>
      and adjust the relevant setup values for the specific problem.</li>
  <li>Iterate: drive, type the feeling, fix, repeat until the car is right.</li>
</ul>

<h3><span class="step">Step 4</span> &nbsp; Practice Review — record real degradation data</h3>
<p>The <b>Practice Review</b> tab auto-filters to your active event car and track when you switch to it.
Use it to build your tyre data:</p>
<ul>
  <li>Drive stints of 10+ laps per compound (<span class="kw">RS</span>, <span class="kw">RM</span>, <span class="kw">RH</span>).</li>
  <li>Tag each lap in the Lap Data column — double-click the <span class="tag">Compound ✎</span> cell.</li>
  <li>Click <b>Analyse Degradation</b> — finds the performance cliff per compound from your actual laps.
      The <b>Opt. Stint</b> column is when to pit for best pace; <b>Total Life</b> is when the tyre is fully worn.</li>
  <li>Click <b>Full Practice Analysis</b> — returns strategy options, setup changes, and what further stints to run.</li>
</ul>

<h3><span class="step">Step 5</span> &nbsp; Practice Review — driver feedback</h3>
<p>After each stint, submit a <b>Driver Feedback</b> form in Practice Review.
Rate corner entry, mid-corner, exit stability, rear under braking, and tyre condition.
The engine uses this alongside your telemetry events (lock-ups, wheelspin, oversteer) to make
setup suggestions specific to what you actually felt, not generic physics.</p>

<h3><span class="step">Step 6</span> &nbsp; Strategy Builder — generate your race strategy</h3>
<p>Switch to <b>Strategy Builder</b>. All race parameters (track, car, race type, laps, tyre wear, fuel)
are pre-populated from your active event — no manual re-entry needed.</p>
<ul>
  <li>Click <b>Race Strategy Analysis</b> — generates 3 ranked strategies using your real degradation data.</li>
  <li>Review the stint plan, pit windows, fuel targets, and compound recommendations.</li>
  <li>Load the preferred strategy and click <b>Apply Plan</b>.</li>
</ul>

<h3><span class="step">Step 7</span> &nbsp; Live Race Engineer — race with real-time coaching</h3>
<p>Switch the Live tab to <b>Race</b> mode. The engineer monitors everything automatically:</p>
<ul>
  <li>Fuel burn vs target, tyre temperatures, pit window timing, pace consistency.</li>
  <li>Voice alerts: pit warning 2 laps out, "Box box box" on the stop lap, overdue replan if you miss a stop.</li>
  <li>Push-to-talk for on-demand queries: fuel, position, strategy, pace, last lap stats.</li>
</ul>
<p class="note">If you miss a pit stop, the engineer detects it and announces a revised window immediately — no manual update needed.</p>

<h3><span class="step">Step 8</span> &nbsp; Home — race engineer overview</h3>
<p>The <b>Home</b> tab (first tab, shown when the app opens) is the Race Engineer Command Centre. It shows your
active event, track data status, latest setup, strategy plan, and whether the engine
is working from up-to-date inputs — plus the single suggested <b>next step</b> and
which tab to do it on. Anything stale or missing is flagged in plain English.
Good for checking overall state before and after a race weekend.</p>

<h3><span class="step">Step 9</span> &nbsp; History — browse past sessions</h3>
<p>The <b>History</b> tab lists every recorded session by car and track.
Click any session to see its laps, compound tags, and telemetry summary.
Use <b>Load to Practice Review</b> to pull old laps back into the analysis workflow.</p>

<h3><span class="step">Step 10</span> &nbsp; Settings — profile, voice, and connection</h3>
<p>Configure once and leave:</p>
<ul>
  <li><b>Connection</b> — PS5 IP address and UDP port (default 33741). Must match GT7 "Send Data" settings.</li>
  <li><b>Voice Alerts</b> — enable/disable categories, set push-to-talk key.</li>
  <li><b>Driver Profile</b> — click <b>Refresh Stats</b> after each race weekend (free, instant)
      to keep your driving profile current from measured telemetry.</li>
</ul>

<h2>GT7 setup (one-time)</h2>
<p>In GT7: <b>Options → Network → Custom → Send Data to PS Remote Play</b> — set the
destination to your PC's IP address and port <b>33741</b>. The app must be running before starting a GT7 session.</p>

<h2>Push-to-talk voice commands</h2>
<p>Press your configured PTT button, wait for the click cue, then say any of these:</p>
<table>
<tr><th>Say…</th><th>Response</th></tr>
<tr><td><span class="kw">fuel</span></td><td>Current fuel level + estimated laps remaining</td></tr>
<tr><td><span class="kw">position</span></td><td>Current race position (P3 of 16, etc.)</td></tr>
<tr><td><span class="kw">laps</span></td><td>Laps remaining or estimated laps from time remaining</td></tr>
<tr><td><span class="kw">strategy</span> / next stop</td><td>Next pit lap, fuel target, next compound, stop number</td></tr>
<tr><td><span class="kw">pace</span></td><td>Last 3-lap average vs best, trend, tyre note if degrading</td></tr>
<tr><td><span class="kw">last lap</span></td><td>Time, lock-ups, wheelspin, oversteer, kerb strikes, braking consistency</td></tr>
<tr><td><span class="kw">rain</span></td><td>Marks wet conditions; shortens slick stint; updates pit window</td></tr>
<tr><td><span class="kw">damage</span></td><td>Reports damage; recommends pit if major; monitors pace recovery</td></tr>
<tr><td><span class="kw">improve</span> / coaching</td><td>Deterministic coaching from your last 3 laps (offline)</td></tr>
<tr><td><span class="kw">setup</span></td><td>Rule-based setup advice from telemetry (offline)</td></tr>
</table>

<h2>Tyre compound tags</h2>
<table>
<tr><th>Tag</th><th>Compound</th></tr>
<tr><td><span class="kw">RS</span></td><td>Racing Soft</td></tr>
<tr><td><span class="kw">RM</span></td><td>Racing Medium</td></tr>
<tr><td><span class="kw">RH</span></td><td>Racing Hard</td></tr>
<tr><td><span class="kw">IM</span></td><td>Intermediate</td></tr>
<tr><td><span class="kw">W</span></td><td>Wet</td></tr>
</table>
<p class="note">Double-click the <span class="tag">Compound ✎</span> column in the Lap Data tab to tag.
Also accepts full names: Soft, Medium, Hard, Inter, Wet, Racing Soft, etc.</p>

<h2>Car Setup fields</h2>
<table>
<tr><th>Field</th><th>What it means in GT7</th></tr>
<tr><td>Ride Height F/R (mm)</td><td>Lower = better aero and stiffer feel.</td></tr>
<tr><td>Springs F/R (Hz)</td><td>Natural frequency in Hz. Higher = stiffer. Road: 1.5–3 Hz, Race: 4–8 Hz. Stiffer front → understeer.</td></tr>
<tr><td>Dampers Comp/Ext F/R</td><td>Compression (20–40) and Extension (30–50). Extension must always be higher than Compression.</td></tr>
<tr><td>ARB F/R</td><td>Anti-roll bar. Stiffer rear ARB = more oversteer on entry. Range 1–10.</td></tr>
<tr><td>Camber F/R (°)</td><td>Negative = top inward. −1° to −3° typical for track use.</td></tr>
<tr><td>Toe F/R (°)</td><td>Toe-in = stable. Toe-out = more turn-in response.</td></tr>
<tr><td>Aero F/R (kg)</td><td>Downforce. Higher = more grip, more drag, more fuel burn.</td></tr>
<tr><td>LSD Initial/Accel/Decel</td><td>Initial: constant locking. Accel: under power. Decel: during braking/trail braking.</td></tr>
<tr><td>Brake Bias (−5…+5)</td><td>−5 = more front braking, +5 = more rear braking.</td></tr>
<tr><td>Min Weight / Max Power</td><td>Event regulations. Used for ballast and power-restrictor calculations.</td></tr>
<tr><td>BOP</td><td>Check for Balance of Performance races. Loads BOP data automatically.</td></tr>
</table>
"""
