# MP-013 — Interactive historical synthetic motor trends

**Scope:** localhost-only, synthetic-only visualization of already persisted MP-012 telemetry read through the read-only MP-040 REST API. Not a field monitoring system, failure probability, physical degradation or remaining useful life estimate.

## Run the dashboard

    python -m motorpulse --paused --database ./motorpulse-local.sqlite3

Open http://127.0.0.1:8765/. The existing live motor cards, seed/virtual-clock form, Start/Pause/Step/Reset controls and per-motor fault scenario editor remain available. Scroll to **Recorded synthetic trends** to browse previous recordings. The default startup with **no** database still serves the live simulation and chart panel; the chart panel reports that recording history requires the --database flag, rather than manufacturing historical points.

The new chart script is bundled in the installed Python wheel at motorpulse/web/history.js and is served locally. Charts use native SVG/DOM methods, no JavaScript chart dependencies, remote CDNs, cookies, external APIs or web fonts.

### What the controls show

1. **Recording session:** select a persisted simulation session (startup, reset, new runtime seed/clock setting or changed fault configuration), including sessions from previous process restarts. The selector initially shows up to the **latest 100** sessions. The current active session is selected by default; previously chosen sessions remain selectable during a normal refresh.
2. **Motor:** assets listed for the selected session are sourced from its persisted scenario configuration, not the current dashboard settings. Selecting a different session rebuilds the motor list.
3. **From / To virtual UTC:** leave blank to include all times or supply a complete RFC3339 UTC timestamp, e.g. 2026-01-01T00:00:00Z or 2026-01-01T00:00:00.123456+00:00. Bounds are inclusive. A UTC offset other than +00:00 is rejected. A literal + should be encoded by the browser as %2B; the UI uses URLSearchParams. No implicit browser-local timezone conversion occurs.
4. **Events per page:** 25, 50 or 100 synthetic per-motor observations (the server never returns more than 100 for one API request). Older/Newer buttons navigate by the MP-040 resource-specific exclusive row-ID cursor. Changing time filters resets the cursor; apply them via **Load trends**. **Current recording** selects the live session and clears UTC bounds. There is no unbounded bulk download or polling of historical events at the live snapshot interval.

After a manual Step the dashboard reloads the selected chart page; after Reset, applying runtime settings or replacing motor scenarios, it reloads sessions and selects the new recording. The interval-driven live snapshot poll **does not poll the full history API every 1.5 seconds**. Select Load trends to refresh an already-open session after automatic background stepping.

### Three synthetic feature trends

| Chart | Sensor/feature | Representation |
| --- | --- | --- |
| Vibration RMS | Original synthetic vibration root-mean-square acceleration, **g** | Only good-sensor numeric points appear in the plotted trace. Missing vibration, nonfinite values and simulated sensor outliers interrupt the line; the dashboard **does not interpolate**, infer or set unavailable RMS to zero. |
| Temperature | Synthetic asset temperature, **°C** | Numeric temperature points are retained even when only the vibration sensor quality is missing/suspect; it does not claim field sensor calibration. |
| Motor speed | Synthetic rotational speed, **RPM** | Recorded RPM feature, not a physical speed controller or live PLC feedback. |

All three charts use the recorded **virtual UTC event timestamps** on the x-axis, so time spacing reflects the simulator configuration rather than assuming a uniform wall-clock sampling rate or placing every sample equally. Each figure announces its purpose to assistive technology, shows plotted/excluded counts and numeric min/max, and the page displays the filtered event count and sensor-quality caveats. Each chart is only the **selected page of observations**; segments are not connected across page boundaries or absent records. An empty match is reported explicitly.

Below the SVGs, an expandable **numerical data table** offers full virtual UTC timestamps, raw recorded vibration RMS, temperature, RPM, sensor quality and original rule health, newest first. This is a keyboard-accessible alternative to chart shape. Raw outlier vibration values may remain in the table with their outlier quality label, but are deliberately **not** connected or counted as good-sensor plotted vibrations.

Charts use CSS responsive columns, labelled form fields, focused controls, polite status updates and a data table without reliance on color alone. Motor/session names and telemetry text are inserted using DOM textContent rather than unsanitized HTML.

## Implementation notes and limitations

- Backend remains unchanged: MP-040 GET /api/history/sessions and GET /api/history/events accept the filtered and paged requests, and existing snapshot GET is non-mutating.
- Read failures or HTTP 409 (persistence disabled) are visible in the history message. They do not stop the live cards or mutate a generator.
- To protect local performance, charts cap page size to 100 events, and session chooser lists the most recent 100 sessions. Historical data older than those sessions remains in SQLite and in the MP-040 API, but is not selectable using the current single-page session chooser.
- Chart values are **synthetic feature summaries**, not raw waveform plots, uncertainty intervals, validated industrial thresholds or sensor calibrations.
- This milestone does **not** introduce SSE/WebSocket streaming (MP-014), alert lifecycle acknowledgements or deduplication (MP-042), chart exports (MP-044), machine learning in the live dashboard, or RUL forecasts.

## Tests

    python -m unittest discover -s tests -p 'test_history_dashboard.py' -v
    python -m unittest discover -s tests -v

Regression tests validate packaged static HTML and JavaScript, accessible SVG and table semantics, a read-only REST fetch after restart, event/session/time filtering, missing/outlier vibration fixtures, 409 fallback without persistence, responsive controls and history update hooks. When a Node.js JavaScript runtime is already available in the **test environment**, optional V8 client tests additionally execute the real chart mathematics/DOM rendering with a tiny test double to check exact microsecond spacing, missing-sensor gaps, non-interpolation, and numerical table rows. Node is **not a runtime dependency** of MotorPulse-AI and is not needed to run the dashboard.

See also [HISTORY_API.md](HISTORY_API.md), [SQLITE_HISTORY.md](SQLITE_HISTORY.md) and [RUNTIME_CONTROLS.md](RUNTIME_CONTROLS.md).
