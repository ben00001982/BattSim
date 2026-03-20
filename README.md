# UAV Battery Analysis & Simulation Toolset

A Python + Excel toolset for analysing, simulating, and reverse-engineering UAV battery performance. Supports multiple battery chemistries, custom pack configurations, ArduPilot flight log import, and Excel report generation.

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/uav-battery-tool.git
cd uav-battery-tool
pip install -r requirements.txt
cd notebooks
jupyter notebook
```

Open `01_battery_database.ipynb` and run all cells to verify the installation.

## Features

- 9 battery chemistries, 11 cells, 8 UAV packs — all editable in `battery_db.xlsx`
- Custom pack builder: any cell + S×P → full pack spec
- Physics-based voltage sag model with per-chemistry Arrhenius temperature dependence
- UAV mission simulation: define flight phases → SoC/voltage/temperature time-series
- ArduPilot `.bin` / `.log` / `.csv` flight log import
- Parameter reverse-engineering: fit R_internal, OCV curve, Peukert k, Arrhenius B from real data
- Excel report generation: scorecard, temperature sensitivity matrix, log vs simulation overlay

## Project Structure

```
uav-battery-tool/
├── battery_db.xlsx          ← Master data store (open directly in Excel)
├── requirements.txt
├── batteries/
│   ├── models.py            ← Dataclasses for all entities
│   ├── database.py          ← Excel read/write layer
│   ├── builder.py           ← Custom S×P pack calculator
│   ├── discharge.py         ← Peukert + PCHIP discharge curves
│   ├── voltage_model.py     ← Three-component sag model
│   ├── log_importer.py      ← ArduPilot log parser
│   └── parameter_fitter.py  ← Battery parameter reverse-engineering
├── mission/
│   ├── simulator.py         ← Time-step simulation engine
│   └── report_generator.py  ← Excel report builder
├── notebooks/
│   ├── 01_battery_database.ipynb
│   ├── 02_equipment_power_profile.ipynb
│   ├── 03_simulation.ipynb
│   ├── 04_log_analysis.ipynb
│   └── 05_reports.ipynb
└── logs/                    ← Place ArduPilot flight logs here
```

## Using Real ArduPilot Logs

1. Copy your `.bin` or `.log` file into `logs/`
2. `pip install pymavlink` (for `.bin` files)
3. Open `04_log_analysis.ipynb`, set `USE_SYNTHETIC = False` and `LOG_PATH`
4. Run all cells — fitted parameters can be saved back to the database

See full documentation in [GUIDE.md](GUIDE.md).

## Requirements

Python 3.10+ with: `openpyxl pandas matplotlib numpy scipy jupyter`

Optional: `pymavlink` for binary `.bin` log files.
