"""
Fix analysis_config.json path resolution in notebooks 01, 02, 04, 06.
Also fix the hardcoded 5-color palette in notebook 06 PDF page 5.

Root cause:
  _os.path.dirname(_os.path.abspath('.')) navigates ABOVE the project root
  when Jupyter is started from the project root, so the config is never found
  and notebooks fall back to hardcoded 3-battery defaults.

Fix: search ['../analysis_config.json', 'analysis_config.json'] in order,
which is robust whether CWD is notebooks/ or the project root.
"""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')


def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])


GOOD_PATH_BLOCK = (
    "# Look for analysis_config.json: try ../  (notebooks/ CWD) then ./  (root CWD)\n"
    "for _p in ['../analysis_config.json', 'analysis_config.json']:\n"
    "    if _os.path.exists(_p):\n"
    "        _CFG_PATH = _p\n"
    "        break\n"
    "else:\n"
    "    _CFG_PATH = '../analysis_config.json'  # default write-path"
)

OLD_PATH_BLOCK = (
    "_CFG_PATH = _os.path.join(_os.path.dirname(_os.path.abspath('.')), 'analysis_config.json')\n"
    "if not _os.path.exists(_CFG_PATH):\n"
    "    _CFG_PATH = 'analysis_config.json'"
)

# ── Notebook 04: config cell a665107f ────────────────────────────────────────
with open('notebooks/04_simulation.ipynb', encoding='utf-8') as f:
    nb04 = json.load(f)

for i, c in enumerate(nb04['cells']):
    if c['id'] == 'a665107f':
        src = ''.join(c['source'])
        if OLD_PATH_BLOCK in src:
            src = src.replace(OLD_PATH_BLOCK, GOOD_PATH_BLOCK)
            nb04['cells'][i]['source'] = lines(src)
            print('Fixed path in nb04 cell a665107f')
        else:
            print('WARNING: old path block not found in nb04 a665107f')
        break

with open('notebooks/04_simulation.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb04, f, indent=1, ensure_ascii=False)


# ── Notebook 06: config cell 9a04bed2 ────────────────────────────────────────
with open('notebooks/06_reports.ipynb', encoding='utf-8') as f:
    nb06 = json.load(f)

for i, c in enumerate(nb06['cells']):
    if c['id'] == '9a04bed2':
        src = ''.join(c['source'])
        if OLD_PATH_BLOCK in src:
            src = src.replace(OLD_PATH_BLOCK, GOOD_PATH_BLOCK)
            nb06['cells'][i]['source'] = lines(src)
            print('Fixed path in nb06 cell 9a04bed2')
        else:
            print('WARNING: old path block not found in nb06 9a04bed2')

    # Fix hardcoded 5-color palette on PDF page 5
    if c['id'] == 'gy83obmtfr5':
        src = ''.join(c['source'])
        old_palette = (
            "    palette = [ACCENT, '#FF9800', '#4CAF50', '#E91E63', '#9C27B0']\n"
            "\n"
            "    for r, p, col in zip(compare_results, compare_packs, palette):"
        )
        new_palette = (
            "    import matplotlib.cm as _cm5\n"
            "    _cmap5 = _cm5.get_cmap('tab10', max(len(compare_results), 1))\n"
            "    _pal5  = [_cmap5(i) for i in range(len(compare_results))]\n"
            "\n"
            "    for r, p, col in zip(compare_results, compare_packs, _pal5):"
        )
        if old_palette in src:
            src = src.replace(old_palette, new_palette)
            nb06['cells'][i]['source'] = lines(src)
            print('Fixed hardcoded palette in nb06 PDF page 5')
        else:
            print('WARNING: old palette block not found in nb06 gy83obmtfr5')
            # Show what's actually there
            idx = src.find('palette = [')
            if idx >= 0:
                print('  Found:', repr(src[idx:idx+100]))

with open('notebooks/06_reports.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb06, f, indent=1, ensure_ascii=False)


# ── Notebook 02: fix CFG_PATH save location ───────────────────────────────────
with open('notebooks/02_configurator.ipynb', encoding='utf-8') as f:
    nb02 = json.load(f)

for i, c in enumerate(nb02['cells']):
    if c['id'] == 'cfg-imports':
        src = ''.join(c['source'])
        # Change the single-line CFG_PATH assignment to use ../
        old_cfg = "CFG_PATH  = 'analysis_config.json'"
        new_cfg  = (
            "# Save config to project root (one level up from notebooks/)\n"
            "CFG_PATH  = ('../analysis_config.json'\n"
            "             if not __import__('os').path.exists('analysis_config.json')\n"
            "             or __import__('os').path.exists('../analysis_config.json')\n"
            "             else 'analysis_config.json')"
        )
        if old_cfg in src:
            src = src.replace(old_cfg, new_cfg)
            nb02['cells'][i]['source'] = lines(src)
            print('Fixed CFG_PATH in nb02 cfg-imports')
        else:
            print('WARNING: CFG_PATH line not found in nb02 cfg-imports')
            for line in src.split('\n'):
                if 'CFG_PATH' in line:
                    print('  Found:', repr(line))
        break

with open('notebooks/02_configurator.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb02, f, indent=1, ensure_ascii=False)


# ── Notebook 01: fix save path ────────────────────────────────────────────────
with open('notebooks/01_battery_selector.ipynb', encoding='utf-8') as f:
    nb01 = json.load(f)

for i, c in enumerate(nb01['cells']):
    if c['id'] == 'nb08-save':
        src = ''.join(c['source'])
        old_save_path = (
            "CFG_PATH = 'analysis_config.json'\n"
            "if not os.path.exists(CFG_PATH):\n"
            "    CFG_PATH = os.path.join('..', 'analysis_config.json')"
        )
        new_save_path = (
            "# Save to project root: prefer ../ so it's always next to battery_db.xlsx\n"
            "CFG_PATH = ('../analysis_config.json'\n"
            "            if os.path.exists('../analysis_config.json')\n"
            "            or not os.path.exists('analysis_config.json')\n"
            "            else 'analysis_config.json')"
        )
        if old_save_path in src:
            src = src.replace(old_save_path, new_save_path)
            nb01['cells'][i]['source'] = lines(src)
            print('Fixed CFG_PATH in nb01 nb08-save')
        else:
            print('WARNING: save path block not found in nb01 nb08-save')
            for line in src.split('\n'):
                if 'CFG_PATH' in line:
                    print('  Found:', repr(line))
        break

with open('notebooks/01_battery_selector.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb01, f, indent=1, ensure_ascii=False)

print('\nDone.')
