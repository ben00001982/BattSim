"""
ui/pages/8_User_Guide.py

BattSim User Guide — interactive Streamlit page with PDF download.
"""
import streamlit as st

from ui.components.user_guide_pdf import generate_user_guide_pdf

st.set_page_config(page_title="User Guide – BattSim", page_icon="📖", layout="wide")

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("📖 BattSim User Guide")
st.markdown(
    "Complete reference for all features in BattSim. "
    "Use the sections below to navigate, or download the full PDF for offline reading."
)

col_dl, col_sp = st.columns([2, 8])
with col_dl:
    if st.button("⬇ Download PDF Guide", type="primary", use_container_width=True):
        with st.spinner("Generating PDF…"):
            pdf_bytes = generate_user_guide_pdf()
        st.download_button(
            label="Save PDF",
            data=pdf_bytes,
            file_name="BattSim_User_Guide.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

st.divider()

# ── Table of Contents ──────────────────────────────────────────────────────────
with st.expander("Table of Contents", expanded=True):
    st.markdown("""
1. [Getting Started](#getting-started)
2. [Dashboard](#dashboard)
3. [Battery Browser](#battery-browser)
4. [UAV Configurator](#uav-configurator)
5. [Mission Configurator](#mission-configurator)
6. [Simulation](#simulation)
7. [Reports](#reports)
8. [Tools](#tools)
9. [Log Tools](#log-tools)
10. [Log → Mission](#log-mission)
11. [Key Concepts](#key-concepts)
12. [Troubleshooting](#troubleshooting)
""")

# ── Section helpers ────────────────────────────────────────────────────────────
def _section(anchor: str, title: str, icon: str):
    st.markdown(f'<a name="{anchor}"></a>', unsafe_allow_html=True)
    st.subheader(f"{icon} {title}")


def _tip(text: str):
    st.info(f"**Tip:** {text}")


def _warn(text: str):
    st.warning(f"**Note:** {text}")


# ══════════════════════════════════════════════════════════════════════════════
# 1. GETTING STARTED
# ══════════════════════════════════════════════════════════════════════════════
_section("getting-started", "Getting Started", "🚀")

st.markdown("""
BattSim is a UAV battery analysis and simulation tool. It helps you:

- **Browse and compare** battery packs from a database of real-world specs
- **Configure UAVs** with specific battery and equipment combinations
- **Define missions** with multiple flight phases (hover, cruise, climb, etc.)
- **Simulate** battery discharge during a mission to predict flight time and end-of-flight voltage
- **Import flight logs** and convert them into reusable mission profiles
- **Generate reports** with charts, tables, and mission summaries

### First-Time Setup

1. Launch the app: `streamlit run ui/Main_Dashboard.py`
2. The app opens in your browser at `http://localhost:8501`
3. All data is stored in `battery_db.xlsx` in the project root
4. No internet connection required — the tool runs entirely locally
""")

_tip("If the database file is missing, the app will show an error. Make sure `battery_db.xlsx` is present in the project root.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 2. DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
_section("dashboard", "Dashboard", "🏠")

st.markdown("""
The **Main Dashboard** is the landing page. It provides a high-level overview of your database.

| Panel | Description |
|---|---|
| Battery Packs | Count of packs loaded from the database |
| UAV Configurations | Number of configured UAV platforms |
| Mission Profiles | Number of saved mission templates |
| Recent Activity | Quick links to recently used items |

### Navigation
Use the **sidebar** on the left to navigate between pages. Pages are numbered 1–8 and cover each major function.
""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 3. BATTERY BROWSER
# ══════════════════════════════════════════════════════════════════════════════
_section("battery-browser", "Battery Browser", "🔋")

st.markdown("""
**Page 1 — Battery Browser** lets you search, filter, and compare battery packs.

### Browsing Packs
- All packs from the database are shown in a sortable table
- Click any column header to sort
- Use the **filter controls** in the sidebar to narrow by chemistry, cell count, or capacity

### Pack Detail
Click a pack row to expand its full specification:
- Nominal/max voltage, capacity (Ah and Wh)
- Discharge C-rating, weight, dimensions
- Internal resistance model parameters (R0, R1, C1 for the ECM)

### Adding a New Pack
1. Click **"Add Battery Pack"** in the sidebar
2. Fill in the required fields (name, chemistry, cell config, capacity)
3. Click **Save** — the pack is written to `battery_db.xlsx`

### Editing / Deleting
- Select a pack and click **Edit** to modify its parameters
- Click **Delete** to remove it (confirmation required)
""")

_warn("Deleting a battery pack will not automatically remove UAV configurations that reference it.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 4. UAV CONFIGURATOR
# ══════════════════════════════════════════════════════════════════════════════
_section("uav-configurator", "UAV Configurator", "✈️")

st.markdown("""
**Page 2 — UAV Configurator** manages UAV platform definitions.

### What is a UAV Configuration?
A UAV configuration ties together:
- A **battery pack** (from the Battery Browser)
- An **equipment profile** (motors, ESCs, payload) with power estimates per flight mode
- Platform metadata (name, frame type, MTOW)

### Creating a UAV Configuration
1. Click **"New UAV Config"**
2. Enter a unique config ID and display name
3. Select the battery pack from the dropdown
4. Enter equipment power levels for each flight mode:
   - **Idle / Ground**: power when motors are armed but not flying
   - **Hover**: power during steady hover
   - **Climb**: power during ascent
   - **Cruise**: power at cruise airspeed
5. Click **Save**

### Equipment Editor
Each UAV configuration has an associated **equipment profile**. The Equipment Editor lets you set power levels per flight mode with optional override values. These become the default power values used in simulation when no `power_override_w` is set on a mission phase.

### 3-Level Power Model
BattSim uses a simplified 3-level power model:
- **Low power** (idle/ground)
- **Medium power** (cruise/loiter)
- **High power** (hover/climb/takeoff/landing)

Each level corresponds to a wattage that drives the battery discharge simulation.
""")

_tip("Use realistic power figures from a power meter during actual test flights for the most accurate simulation results.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 5. MISSION CONFIGURATOR
# ══════════════════════════════════════════════════════════════════════════════
_section("mission-configurator", "Mission Configurator", "🗺️")

st.markdown("""
**Page 3 — Mission Configurator** lets you define multi-phase mission profiles.

### Mission Structure
A mission is a sequence of **phases**. Each phase has:

| Field | Description |
|---|---|
| Phase Name | Display label (e.g., "Transit to site") |
| Phase Type | ArduPilot mode or power category (HOVER, CRUISE, CLIMB, etc.) |
| Duration (s) | How long this phase lasts |
| Distance (m) | Ground distance covered (optional) |
| Altitude (m) | Mean altitude above takeoff point |
| Airspeed (m/s) | Mean airspeed |
| Power Override (W) | Force a specific power draw; leave blank to use UAV equipment model |
| Notes | Free-text annotation |

### Creating a Mission
1. Click **"New Mission"**
2. Enter a mission ID and name
3. Select the UAV configuration this mission is designed for
4. Add phases using the phase editor:
   - Click **"Add Phase"** to append a new row
   - Fill in duration and phase type at minimum
5. Click **Save Mission**

### Power Override
Setting `power_override_w` on a phase bypasses the UAV equipment model. Use this when you have measured power data for that specific manoeuvre (e.g., from a flight log import).

### Importing from a Log
You can automatically populate a mission from a flight log using the **Log → Mission** tool in Log Tools (Page 7). This extracts phases directly from flight data.
""")

_tip("Mission IDs must be unique. Use a consistent naming convention such as `SITE_MISSION_DATE` (e.g., `AG_SPRAY_001`).")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 6. SIMULATION
# ══════════════════════════════════════════════════════════════════════════════
_section("simulation", "Simulation", "⚡")

st.markdown("""
**Page 4 — Simulation** runs the battery discharge model against a mission profile.

### Running a Simulation
1. Select a **Battery Pack** from the dropdown
2. Select a **UAV Configuration** (must be compatible with the battery)
3. Select a **Mission Profile**
4. Set the initial State of Charge (SoC) — default is 100%
5. Click **Run Simulation**

### What the Simulation Computes
For each mission phase, the simulator:
1. Looks up power draw (from `power_override_w` or the UAV equipment model)
2. Calculates current draw: `I = P / V_terminal`
3. Steps the ECM (Equivalent Circuit Model) to update:
   - Terminal voltage `V_t`
   - State of Charge (SoC %)
   - Cumulative energy (Wh) and charge (mAh) consumed
4. Checks for end-of-discharge conditions:
   - SoC ≤ minimum threshold
   - Voltage ≤ cutoff voltage

### Simulation Results
| Output | Description |
|---|---|
| Flight time | Total mission duration if battery lasts; otherwise time until cutoff |
| End SoC | Remaining charge at end of mission |
| End voltage | Terminal voltage at mission end |
| Energy used | Total Wh consumed |
| Charge used | Total mAh consumed |
| Phase breakdown | Per-phase voltage, SoC, and power chart |

### Equivalent Circuit Model (ECM)
BattSim uses a first-order RC circuit model (Thevenin model):
- `R0` — internal resistance (ohmic)
- `R1`, `C1` — diffusion resistance and capacitance

These parameters are stored per battery pack and affect how voltage sags under load.
""")

_warn("If no power override is set and the UAV equipment model has zero power for a phase type, that phase will consume no energy. Check your UAV configuration before simulating.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 7. REPORTS
# ══════════════════════════════════════════════════════════════════════════════
_section("reports", "Reports", "📊")

st.markdown("""
**Page 5 — Reports** generates printable PDF reports summarising battery and mission data.

### Report Types
- **Battery Summary Report** — specs and ECM parameters for one or more packs
- **Mission Report** — phase breakdown, simulated discharge curve, key metrics
- **Fleet Report** — comparative view across multiple UAV / battery combinations

### Generating a Report
1. Select the report type from the dropdown
2. Choose the battery packs / missions / UAV configs to include
3. Click **Generate Report**
4. Preview the report in the page, then click **Download PDF**

### Report Contents
Each report includes:
- Cover page with date/time
- Summary tables
- Voltage vs. time discharge chart (for mission reports)
- Phase-by-phase energy breakdown
- Key statistics (end SoC, peak current, total Wh)

### Customisation
- Report title and subtitle can be edited before generation
- You can include/exclude individual sections using checkboxes
""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 8. TOOLS
# ══════════════════════════════════════════════════════════════════════════════
_section("tools", "Tools", "🔧")

st.markdown("""
**Page 6 — Tools** provides three tabs for building battery packs, validating models, and importing data.

### Tab: Pack Builder

#### Sub-tab: Build from Cell
Construct a new battery pack by selecting an individual cell from the Cell Catalog and specifying a series/parallel configuration.

1. **Select a cell** — choose from the Cell Catalog (manufacturer, chemistry, format, capacity)
2. **Set series (S) and parallel (P)** — defines the pack voltage and capacity
3. **Weight overhead %** — adds BMS and wiring mass on top of bare cell weight (default 12%)
4. **Pack ID / Name** — leave blank to auto-generate from the cell and config
5. **UAV class** and **Notes** — optional metadata
6. Review the computed specs: voltage, capacity, energy, weight, specific energy, max current, max power, internal resistance
7. Click **Save to Database** — written directly to `battery_db.xlsx`

#### Sub-tab: Combine Packs
Connect existing packs together to create a new combined pack entry.

1. Choose **series** (higher voltage) or **parallel** (higher capacity)
2. Add packs from the dropdown, with a quantity for each
3. Review the combined pack preview
4. Click **Save Combined Pack** to write to the database

A **View Cell Catalog** expander at the bottom shows all cells with their full specifications.

### Tab: Model Validation
Compare FAST, STANDARD, and PRECISE voltage model accuracy against a real flight log.

**Requirements:** A flight log must first be loaded in the **Log Tools** page (upload or generate synthetic). PRECISE mode additionally requires fitted ECM parameters registered via Log Tools.

**Workflow:**
1. Select battery pack, mission profile, and UAV configuration
2. Set ambient temperature, initial SoC, Peukert exponent, and cutoff SoC
3. Choose which model modes to compare (FAST / STANDARD / PRECISE)
4. Click **Run Validation**

**Results:**
| Metric | Description |
|---|---|
| RMSE (V) | Root mean squared error between simulated and measured voltage |
| MAE (V) | Mean absolute error |
| R² | Coefficient of determination (1.0 = perfect fit) |
| Bias (V) | Systematic over/under-prediction |
| Points | Number of comparison data points |

A voltage comparison chart overlays simulated vs. measured traces for each model mode.

### Tab: Bulk Data Upload

#### Sub-tab: CSV Bulk Import
Import multiple battery packs at once from a CSV file.

1. Click **Download CSV Template** to get a pre-filled example with all required columns
2. Fill in your pack data (one row per pack; `battery_id` must be unique)
3. Upload the completed CSV
4. Preview shows detected duplicates and count of new packs to add
5. Click **Import N packs** to write to the database

Required columns: `battery_id`, `pack_energy_wh`, `pack_weight_g`. All others are optional but recommended.

#### Sub-tab: Web Scraper
Automatically extract battery specifications from a product or datasheet web page.

1. Paste the target URL and click **Scrape Page**
2. BattSim fetches the page and extracts tables and key-value patterns (capacity, voltage, weight, energy, cell config, max discharge, chemistry)
3. Review the auto-extracted specs and any tables found on the page
4. Map the extracted data to the battery fields, set a Battery ID, and click **Save Scraped Pack to Database**

*Requires: `pip install requests beautifulsoup4`*

#### Sub-tab: PDF Datasheet
Upload a battery manufacturer PDF datasheet to extract specifications.

1. Upload the PDF file
2. BattSim extracts all text and tables using `pdfplumber`
3. Auto-parsed specs (capacity, voltage, weight, energy, cell config, max discharge) are shown
4. Review the extracted text and tables, correct any fields, then click **Save PDF Pack to Database**

*Requires: `pip install pdfplumber`*
""")

_tip("The Cell Catalog (visible in the Pack Builder expander) is separate from the Battery Pack catalog — cells are individual cells, packs are assembled multi-cell units.")
_warn("Battery IDs must be unique across all import methods. Duplicate IDs are skipped automatically during CSV import but will raise an error on individual saves.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 9. LOG TOOLS
# ══════════════════════════════════════════════════════════════════════════════
_section("log-tools", "Log Tools", "📋")

st.markdown("""
**Page 7 — Log Tools** contains tools for working with ArduPilot/PX4 flight logs.

### Tab: Log Analysis
Upload a `.bin` or `.log` flight log file to extract and visualise:
- Battery voltage and current over time
- State of charge (mAh consumed)
- GPS speed and altitude
- Flight mode history

The analysis view shows summary statistics and time-series charts for each data stream.

### Tab: Log Registry
A searchable list of all logs you have previously imported. Each entry stores:
- File name and upload date
- Total flight duration
- Peak and average power
- Tags and notes

Click any entry to re-open its analysis without re-uploading the file.

### Tab: ECM Parameter Viewer
After importing a log, BattSim can attempt to estimate ECM parameters (R0, R1, C1) from the voltage and current data. The ECM Viewer tab shows:
- Fitted vs. measured voltage trace
- R-squared goodness of fit
- Estimated parameter values

These estimates can be used to update a battery pack's ECM model in the Battery Browser.

### Tab: Log → Mission
See the dedicated [Log → Mission](#log-mission) section below.
""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 10. LOG → MISSION
# ══════════════════════════════════════════════════════════════════════════════
_section("log-mission", "Log → Mission", "🔄")

st.markdown("""
**Log → Mission** (in Page 7 — Log Tools) extracts a mission profile from a real flight log. Instead of manually defining phases, BattSim segments the log by flight mode and computes average power for each segment.

### Step 1 — Upload a Log
Click **"Choose a .bin/.log file"** in the Log → Mission tab. The log is parsed to extract:
- Timestamps
- Battery voltage and current
- Flight mode (phase_type) changes
- GPS altitude and speed

### Step 2 — Review Segments
After parsing, a table of **Mission Segments** is displayed. Each row represents one continuous flight mode block:

| Column | Description |
|---|---|
| Seq | Phase sequence number |
| Mode | ArduPilot mode name (e.g., LOITER, AUTO, STABILIZE) |
| Phase Name | Editable display label |
| Duration | Segment duration in seconds |
| Mean Power (W) | Average V×I power during this segment |
| Min / Max Power | Power range |
| Std Dev | Power variability — high std dev = turbulent or transitional flight |
| Energy (Wh) | Integrated energy for this segment |
| ΔmAh | Change in mAh counter during segment |
| Altitude (m) | Mean GPS altitude |
| Speed (m/s) | Mean GPS groundspeed |
| Confidence | Data quality indicator: **high** / **medium** / **low** |
| Transient | Flagged if duration < 8 s — likely a mode-change artefact |

### Confidence Levels
| Level | Criteria |
|---|---|
| **High** | ≥ 10 power samples AND power std dev < 35% of mean |
| **Medium** | ≥ 3 power samples |
| **Low** | Fewer than 3 power samples — power estimate unreliable |

### Step 3 — Edit Segments
You can edit segments before saving:
- **Rename** a phase (click the Phase Name cell)
- **Change Phase Type** to match BattSim's standard types
- **Delete** a row (select it and click Delete Segment)
- **Merge** two adjacent rows into one (select both, click Merge)

#### Merging Segments
When you merge two segments, BattSim computes a **duration-weighted mean power**:
```
merged_power = (power_A × duration_A + power_B × duration_B) / (duration_A + duration_B)
```
You can accept this calculated value or enter a manual override (e.g., if you know the true power from another source).

### Step 4 — Import Options
Before saving, choose the **Import Mode**:

| Mode | Power Override | When to Use |
|---|---|---|
| Phase + duration + estimated power | Set from log | When you trust the power measurements |
| Phase + duration only | Not set (None) | When you want the UAV equipment model to supply power at simulation time |

**Low-confidence** segments always have their power override set to `None` regardless of import mode, because the estimate is unreliable.

### Step 5 — Save Mission
1. Enter a **Mission ID** (unique, e.g., `SITE_SPRAY_001`)
2. Enter a **Mission Name** (display label)
3. Select the **UAV Configuration** this mission belongs to
4. Click **Save to Database**

The mission is appended to `battery_db.xlsx` and immediately available in the Mission Configurator and Simulation pages.

### Typical Workflow
```
Real flight → .bin log file
→ Upload in Log Tools → Log → Mission
→ Review and clean up segments
→ Set Mission ID / UAV config
→ Save
→ Run Simulation with actual flight data
```
""")

_tip("Log segments shorter than 8 seconds are automatically flagged as transient. These are usually mode-change artefacts and can safely be deleted before saving.")
_warn("The Log → Mission tool requires that the log contains mode/phase data. Logs without flight mode messages cannot be segmented.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 11. KEY CONCEPTS
# ══════════════════════════════════════════════════════════════════════════════
_section("key-concepts", "Key Concepts", "💡")

st.markdown("""
### Equivalent Circuit Model (ECM)
BattSim models a Li-Po / Li-ion battery as a first-order Thevenin circuit:

```
V_terminal = V_OCV(SoC) - I × R0 - V_RC
dV_RC/dt = I/C1 - V_RC/(R1×C1)
```

- `V_OCV` — open-circuit voltage, a function of SoC (look-up table)
- `R0` — pure ohmic resistance (immediate voltage sag)
- `R1`, `C1` — diffusion RC pair (slower transient response)

### State of Charge (SoC)
SoC is expressed as a percentage (0–100%). It is computed by Coulomb counting:
```
SoC(t) = SoC(0) - ∫ I(t) dt / Q_nominal
```
where `Q_nominal` is the rated capacity in Ah.

### Phase Types
BattSim uses ArduPilot mode names and abstract power categories as phase types:

| Category | Examples |
|---|---|
| Power categories | HOVER, CRUISE, CLIMB, DESCENT, IDLE, TAKEOFF, LANDING |
| ArduPilot modes | LOITER, AUTO, GUIDED, STABILIZE, ALT_HOLD, POSHOLD |

The UAV equipment model maps each type to a power level (high/medium/low).

### Import Mode (Log → Mission)
- **With power**: `power_override_w` is populated from the log measurement. The simulator uses this directly.
- **Without power**: `power_override_w` is `None`. The simulator queries the UAV equipment model for the phase type at runtime.

### Confidence
Applied to log-extracted segments. Reflects how reliably the mean power was measured:
- **High**: many samples, stable power → trust the number
- **Medium**: enough samples but variable
- **Low**: too few samples → BattSim sets power to `None` regardless of import mode
""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# 12. TROUBLESHOOTING
# ══════════════════════════════════════════════════════════════════════════════
_section("troubleshooting", "Troubleshooting", "🛠️")

st.markdown("""
### App won't start
- Ensure you have installed all dependencies: `pip install -r requirements.txt`
- Check that `battery_db.xlsx` exists in the project root
- Run from the project root: `streamlit run ui/Main_Dashboard.py`

### "Mission already exists" error
- Mission IDs must be unique. Choose a different ID or delete the existing mission first.

### Simulation shows no discharge / zero power
- The UAV configuration's equipment model may have zero power for the phase types used
- Or all mission phases have `power_override_w = 0`
- Check the UAV configurator and verify power levels are non-zero

### Log import fails / no segments
- The log file must contain ArduPilot `MODE` messages. BIN logs from APM/Cube include these by default.
- Very short logs (< 30 s) may produce only 1–2 segments
- Ensure the log contains battery monitor messages (CURR messages in .bin logs)

### PDF report is blank / missing charts
- This can happen if matplotlib is not installed: `pip install matplotlib`
- On headless servers, set the backend: `export MPLBACKEND=Agg` before starting the app

### Database file locked
- Only one instance of BattSim should write to `battery_db.xlsx` at a time
- Close Excel if you have the file open in a spreadsheet application

### ECM parameter estimation fails
- The estimation requires sufficient variation in current (the log must have different power states)
- A flat-current log (e.g., hover-only flight) does not provide enough excitation for parameter fitting

### Contacting Support
Report issues at: **https://github.com/your-org/BattSim/issues**
""")

_tip("Before reporting a bug, check that you are running the latest version: `git pull origin main`.")

st.divider()
st.caption("BattSim User Guide — generated by BattSim. For the latest version, check the project repository.")
