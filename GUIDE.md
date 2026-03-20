# UAV Battery Tool — Setup & Usage Guide

---

## Part 1: Prerequisites

Before starting, confirm you have the following installed on your machine.

### 1.1 Check Python version

Open a terminal and run:

```bash
python3 --version
```

You need **Python 3.10 or newer**. If you have an older version:
- **Windows/Mac**: Download from https://python.org/downloads
- **Ubuntu/Debian**: `sudo apt install python3.11 python3.11-venv`

### 1.2 Check Git is installed

```bash
git --version
```

If not installed:
- **Windows**: Download from https://git-scm.com
- **Mac**: `xcode-select --install`
- **Ubuntu**: `sudo apt install git`

### 1.3 Set up Git identity (first-time only)

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

---

## Part 2: GitHub Repository Setup

### 2.1 Create the repository on GitHub

1. Go to https://github.com and sign in
2. Click the **+** button (top right) → **New repository**
3. Fill in:
   - **Repository name**: `uav-battery-tool`
   - **Description**: `UAV battery analysis, simulation and flight log analysis`
   - **Visibility**: Private (recommended while developing)
   - **Do NOT** tick "Add a README" — the project already has one
4. Click **Create repository**
5. GitHub will show you a page with setup commands — keep it open

### 2.2 Set up SSH authentication (recommended)

Check if you already have an SSH key:

```bash
ls ~/.ssh/id_ed25519.pub
```

If the file does not exist, create one:

```bash
ssh-keygen -t ed25519 -C "you@example.com"
# Press Enter three times to accept defaults
```

Copy the public key to your clipboard:

```bash
# Mac
cat ~/.ssh/id_ed25519.pub | pbcopy

# Linux
cat ~/.ssh/id_ed25519.pub | xsel --clipboard

# Windows (Git Bash)
cat ~/.ssh/id_ed25519.pub | clip
```

Add it to GitHub:
1. Go to https://github.com/settings/keys
2. Click **New SSH key**
3. Title: e.g. "My laptop"
4. Paste the key
5. Click **Add SSH key**

Test the connection:

```bash
ssh -T git@github.com
# Expected: "Hi username! You've successfully authenticated..."
```

---

## Part 3: Get the Project Files onto Your Machine

### 3.1 Download from Claude

Download the zip file Claude provided (`uav_battery_tool_phase4.zip`) to your **Downloads** folder (or anywhere convenient).

### 3.2 Extract and rename

```bash
# Mac / Linux
cd ~/Downloads
unzip uav_battery_tool_phase4.zip
mv uav_battery_tool uav-battery-tool

# Windows (PowerShell)
cd $env:USERPROFILE\Downloads
Expand-Archive uav_battery_tool_phase4.zip -DestinationPath .
Rename-Item uav_battery_tool uav-battery-tool
```

### 3.3 Initialise the Git repository

```bash
cd ~/Downloads/uav-battery-tool      # or wherever you extracted

git init
git add .
git commit -m "Initial commit: UAV battery tool Phase 4"
```

### 3.4 Push to GitHub

Replace `YOUR_USERNAME` with your actual GitHub username:

```bash
git remote add origin git@github.com:YOUR_USERNAME/uav-battery-tool.git
git branch -M main
git push -u origin main
```

Refresh your GitHub repository page — all files should now be visible.

---

## Part 4: Python Environment Setup

Working in a virtual environment keeps this project's dependencies isolated from everything else on your machine.

### 4.1 Create and activate a virtual environment

```bash
cd ~/Downloads/uav-battery-tool

# Create
python3 -m venv .venv

# Activate — Mac / Linux
source .venv/bin/activate

# Activate — Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Activate — Windows (Command Prompt)
.venv\Scripts\activate.bat
```

Your terminal prompt will change to show `(.venv)` when activated.

### 4.2 Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs: `openpyxl`, `pandas`, `matplotlib`, `numpy`, `scipy`, `jupyter`, `notebook`, `ipykernel`.

Expected output ends with something like:
```
Successfully installed jupyter-7.x.x notebook-7.x.x ...
```

### 4.3 Optional: install pymavlink for binary logs

Only needed if you have ArduPilot `.bin` log files:

```bash
pip install pymavlink
```

### 4.4 Verify the installation

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from batteries.database import BatteryDatabase
db = BatteryDatabase('battery_db.xlsx').load()
print(db.summary())
print('Installation OK')
"
```

Expected output:
```
Battery Database Summary
  Chemistries       : 9
  Cells             : 11
  Battery packs     : 8
  ...
Installation OK
```

---

## Part 5: Running the Notebooks

### 5.1 Start Jupyter

```bash
# Make sure your virtual environment is still active (you see (.venv))
cd ~/Downloads/uav-battery-tool/notebooks
jupyter notebook
```

A browser window opens showing the notebooks folder. If it doesn't open automatically, look for the URL printed in the terminal (starts with `http://127.0.0.1:8888`).

### 5.2 Notebook run order

Run notebooks **in order** the first time through. Each one builds on the previous.

---

### Notebook 01 — Battery Database

**File**: `01_battery_database.ipynb`

**What it does**: Lets you explore the chemistry library, cell catalog, and battery pack catalog. Builds custom packs. Plots discharge curves.

**How to run**:
1. Click `01_battery_database.ipynb` to open it
2. Click **Kernel → Restart & Run All**
3. Wait for all cells to finish (green tick beside each cell)

**What to check**:
- Cell 1 (imports): should print the database summary — 9 chemistries, 11 cells, 8 packs
- Chemistry comparison bar charts should appear
- The custom pack builder cell (Section 5) should print a pack summary

**First customisation**: In Section 5, change `CELL_ID` to any cell in your catalog. Change `SERIES` and `PARALLEL` to your target configuration. Re-run that cell.

---

### Notebook 02 — Equipment & Power Profile

**File**: `02_equipment_power_profile.ipynb`

**What it does**: Shows equipment power by category. Builds a custom mission from flight parameters. Generates a power profile chart. Checks which packs can complete the mission.

**How to run**: Kernel → Restart & Run All

**First customisation** — define your own mission (Section 4):

```python
MISSION_ID   = 'MY_MISSION_01'
MISSION_NAME = 'Custom Grid Survey'
UAV_ID       = 'HEX_SURVEY_900'   # match a UAV in your database

PHASES = [
    ('Pre-arm',    'IDLE',    90,   0,   0,  0, None),
    ('Takeoff',    'TAKEOFF', 25,   0,  20,  3, None),
    ('Climb',      'CLIMB',   55, 150,  80,  4, None),
    ('Survey',     'CRUISE', 600,4000,  80,  8, None),
    ('Return',     'CRUISE', 160, 800,  80,  8, None),
    ('Descend',    'DESCEND', 55,   0,  10,  3, None),
    ('Land',       'LAND',    20,   0,   0,  1, None),
]
```

The bottom table shows which catalog packs pass the energy and power requirements.

---

### Notebook 03 — Simulation

**File**: `03_simulation.ipynb`

**What it does**: Runs discharge simulations with the full voltage sag model. Temperature sweep. Multi-battery comparison. Chemistry cold-weather comparison.

**How to run**: Kernel → Restart & Run All

**Key parameters to change** (top of Section 3):

```python
SIM_PACK_ID    = 'BAT_MID_6S2P'    # pack to simulate
SIM_MISSION_ID = 'SURVEY_STD'       # mission to simulate
SIM_UAV_ID     = 'HEX_SURVEY_900'
AMBIENT_TEMP_C = 25.0               # change to your operating temperature
```

**Temperature sweep** (Section 4): change `TEMPS_SWEEP` to the range relevant to you. Results appear as a table and four-panel chart. Depleted runs show red dots.

**What to look for**:
- Section 2: three stack-area charts showing how sag splits between ohmic, charge-transfer, and concentration components at 25°C, 0°C, and −15°C
- Section 4: the temperature at which the pack depletes before completing the mission (the "minimum operating temperature" for your mission)

---

### Notebook 04 — Flight Log Analysis

**File**: `04_log_analysis.ipynb`

**Using synthetic data first (default)**:

The notebook defaults to `USE_SYNTHETIC = True`, which generates a simulated ArduPilot log with sensor noise. Run all cells to confirm the fitting pipeline works before using a real log.

**Using a real ArduPilot log**:

1. Copy your `.bin` or `.log` file into the `logs/` folder inside the project
2. Change these variables in Section 1:

```python
USE_SYNTHETIC = False
LOG_PATH      = '../logs/your_flight.bin'   # or .log or .csv
PACK_ID       = 'BAT_MID_6S2P'             # closest matching pack in your catalog
AMBIENT_TEMP_C = 22.0                       # actual temperature during the flight
```

3. If using a `.bin` file and pymavlink isn't installed, run `pip install pymavlink` first
4. Run all cells

**What the fitting pipeline produces**:
- `R_internal_mohm` — measured pack internal resistance at 25°C
- `OCV curve` — reconstructed open-circuit voltage vs SoC
- `Peukert k` — capacity correction exponent
- `Arrhenius B` — temperature coefficients (requires ≥8°C variation in the log)

**Saving fitted parameters**:

At the bottom of the notebook, set `SAVE_FITTED_PACK = True` to write the fitted pack back to `battery_db.xlsx`. It will appear as `YOUR_PACK_ID_FITTED` in the catalog and can then be selected in notebooks 03 and 05.

---

### Notebook 05 — Reports

**File**: `05_reports.ipynb`

**What it does**: Runs the full analysis and generates a formatted Excel report.

**How to run**: Kernel → Restart & Run All

**Change the output filename** (Section 1):

```python
OUT_PATH = 'My_UAV_Battery_Report.xlsx'
```

The report contains:
- **Cover** — run metadata
- **Mission_Summary** — per-phase energy and power table
- **Battery_Scorecard** — PASS/MARGINAL/FAIL for each pack with all key metrics
- **Temp_Sensitivity** — temperature sweep results matrix
- **Log_vs_Sim** — real log vs simulation chart (if a log was provided)
- **Fitted_Params** — reverse-engineered parameters with deviation from catalog

The file is saved in the `notebooks/` folder. Open it in Excel.

---

## Part 6: Adding Your Company's Equipment

The `Equipment_DB` sheet in `battery_db.xlsx` is where your company's UAV components live. Each item needs per-phase power estimates.

**How to add a motor + ESC pair**:

1. Open `battery_db.xlsx`
2. Go to the `Equipment_DB` sheet
3. Add a row. Key fields:
   - `Equip_ID`: e.g. `MOT_MY_MOTOR_KV400`
   - `Category`: `Propulsion`
   - `Hover_Power_W`: measure from a thrust stand, or use manufacturer data at hover thrust
   - `Cruise_Power_W`: typically 65–75% of hover power for multirotors
   - `Climb_Power_W`: typically 110–120% of hover power
   - `Max_Power_W`: full throttle figure
   - `Weight_g`: motor + ESC combined weight
4. Add your motor to `UAV_Configurations`, referencing the `Equip_ID` and quantity

After saving the Excel file, reload the database in Python:

```python
db.reload()
```

---

## Part 7: Ongoing Git Workflow

After making changes to the project (adding equipment, custom cells, etc.):

```bash
# See what changed
git status

# Stage your changes
git add battery_db.xlsx                    # if you edited the database
git add batteries/models.py               # if you changed Python files
git add .                                  # to stage everything

# Commit with a descriptive message
git commit -m "Add company motor to Equipment_DB"

# Push to GitHub
git push
```

**Recommended commit messages**:
```
Add 5 company motors and ESCs to Equipment_DB
Add MY_PAYLOAD_01 to Equipment_DB with hover/cruise power
Add custom LiPo pack to Battery_Catalog from flight log fitting
Fix UAV_CONFIG for 6-motor heavy-lift build
```

---

## Part 8: Troubleshooting

### "ModuleNotFoundError: No module named 'batteries'"

Make sure you are running Jupyter from inside the `notebooks/` folder, and the `sys.path.insert(0, '..')` at the top of each notebook is present and has run.

```bash
cd ~/Downloads/uav-battery-tool/notebooks
jupyter notebook
```

### "No BAT messages found in log file"

Your ArduPilot log has battery logging disabled. On the flight controller:
- Set `LOG_BITMASK` to include bit 9 (value 512), or use the full logging preset (4095)
- Set `BAT_MONITOR` to your sensor type (1 = analog, 4 = I2C)
- Refly and collect a new log

### "scipy not found — fitting will use numpy fallback"

Install scipy:
```bash
pip install scipy
```

### Jupyter notebook shows "Kernel dead"

The Python kernel crashed, usually due to a memory issue. Try:
- Kernel → Restart
- Increase `dt_s` in simulation cells (e.g. `dt_s=5.0` instead of `dt_s=1.0`)

### Excel file opens but shows no data

Make sure you extracted the zip file properly. The `battery_db.xlsx` file must be in the **root** of the project (same level as `requirements.txt`), not inside `notebooks/`.

### `.bin` file parse returns empty log

Install pymavlink and try again:
```bash
pip install pymavlink
```

If it still fails, export from Mission Planner as `.csv` (File → Log Analysis → Export CSV) and use that instead.

---

## Part 9: Jupyter Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Shift + Enter` | Run current cell, move to next |
| `Ctrl + Enter` | Run current cell, stay |
| `Esc` then `A` | Insert cell above |
| `Esc` then `B` | Insert cell below |
| `Esc` then `DD` | Delete cell |
| `Esc` then `M` | Change cell to Markdown |
| `Esc` then `Y` | Change cell to Code |
| `Ctrl + Shift + P` | Command palette |

Run all cells in order: **Kernel → Restart & Run All**

