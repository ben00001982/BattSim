"""Add Section 5 (Bulk Brand Scraper) cells to 00_bulk_data_entry.ipynb."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

with open('notebooks/00_bulk_data_entry.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

# ── New cells to append ───────────────────────────────────────────────────────

hdr_src = """\
---
## 5 · Bulk Scrape from Tattu / Grepow

Automatically fetch and parse all UAV battery listings from manufacturer websites.
Results are shown as a DataFrame before anything is saved — review and confirm first.

**Run the cells below in order:**
1. Configure options
2. Run the scraper (takes 1-3 minutes — polite 1.5 s delay between requests)
3. Review the preview table
4. Save to database if the data looks good"""

cfg_src = """\
import sys, os
sys.path.insert(0, os.path.abspath('..'))

# ── Configure the bulk scraper ─────────────────────────────────────────────────
SCRAPE_BRAND    = 'all'     # 'tattu' | 'grepow' | 'all'
MAX_PER_BRAND   = 50        # max product pages to visit per brand
VERBOSE         = True      # print progress line-by-line

# ─────────────────────────────────────────────────────────────────────────────
print(f'Brand: {SCRAPE_BRAND}  |  Max per brand: {MAX_PER_BRAND}')
print('Ready — run the next cell to start scraping.')"""

run_src = """\
from scripts.scrape_batteries import scrape_tattu, scrape_grepow, scrape_all
import pandas as pd

if SCRAPE_BRAND == 'tattu':
    scraped_rows = scrape_tattu(max_products=MAX_PER_BRAND, verbose=VERBOSE)
elif SCRAPE_BRAND == 'grepow':
    scraped_rows = scrape_grepow(max_products=MAX_PER_BRAND, verbose=VERBOSE)
else:
    scraped_rows = scrape_all(max_per_brand=MAX_PER_BRAND, verbose=VERBOSE)

print(f'\\nTotal packs scraped: {len(scraped_rows)}')"""

preview_src = """\
# Preview the scraped results before saving
if not scraped_rows:
    print('No data scraped — check the warnings above.')
else:
    df_scraped = pd.DataFrame(scraped_rows)[[
        'battery_id', 'name', 'cells_series', 'cells_parallel',
        'pack_capacity_ah', 'pack_voltage_nom', 'pack_energy_wh',
        'cont_c_rate', 'max_cont_discharge_a',
        'pack_weight_g', 'specific_energy_wh_kg',
    ]]
    df_scraped['pack_capacity_ah'] = (df_scraped['pack_capacity_ah'] * 1000).round(0).astype(int)
    df_scraped = df_scraped.rename(columns={'pack_capacity_ah': 'capacity_mah'})
    pd.set_option('display.max_rows', 100)
    pd.set_option('display.max_colwidth', 40)
    pd.set_option('display.width', 160)
    print(df_scraped.to_string(index=False))
    print(f'\\n{len(df_scraped)} packs ready to save.')
    print('Set SAVE_SCRAPED = True in the next cell and re-run to write to battery_db.xlsx.')"""

save_src = """\
# ── Set SAVE_SCRAPED = True to write results to battery_db.xlsx ───────────────
SAVE_SCRAPED   = False      # <── change to True when you are happy with the preview
SKIP_EXISTING  = True       # skip battery_ids already in the database
DB_PATH_SCRAPE = '../battery_db.xlsx'

# ─────────────────────────────────────────────────────────────────────────────
if SAVE_SCRAPED and scraped_rows:
    from scripts.scrape_batteries import save_to_db
    n = save_to_db(scraped_rows, db_path=DB_PATH_SCRAPE,
                   skip_existing=SKIP_EXISTING, verbose=True)
    print(f'\\nWrote {n} new pack(s) to {DB_PATH_SCRAPE}')
    print('Reload the BatteryDatabase in other notebooks to see the new packs.')
elif not SAVE_SCRAPED:
    print('SAVE_SCRAPED is False — nothing written.')
    print('Set SAVE_SCRAPED = True and re-run this cell to save.')
else:
    print('No data to save.')"""

new_cells = [
    {'id': 'de-bulk-hdr',     'cell_type': 'markdown', 'source': lines(hdr_src),     'metadata': {}},
    {'id': 'de-bulk-cfg',     'cell_type': 'code',     'source': lines(cfg_src),     'metadata': {}, 'outputs': [], 'execution_count': None},
    {'id': 'de-bulk-run',     'cell_type': 'code',     'source': lines(run_src),     'metadata': {}, 'outputs': [], 'execution_count': None},
    {'id': 'de-bulk-preview', 'cell_type': 'code',     'source': lines(preview_src), 'metadata': {}, 'outputs': [], 'execution_count': None},
    {'id': 'de-bulk-save',    'cell_type': 'code',     'source': lines(save_src),    'metadata': {}, 'outputs': [], 'execution_count': None},
]

# Check none already exist
existing_ids = {c['id'] for c in nb['cells']}
for nc in new_cells:
    if nc['id'] in existing_ids:
        print(f'Cell {nc["id"]} already exists — skipping')
        new_cells = [c for c in new_cells if c['id'] != nc['id']]

nb['cells'].extend(new_cells)

with open('notebooks/00_bulk_data_entry.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f'Added {len(new_cells)} cells to 00_bulk_data_entry.ipynb')
print('Done')
