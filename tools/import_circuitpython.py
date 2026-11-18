#!/usr/bin/env python3
"""Generate boards/circuitpython/*.json from a CircuitPython checkout: python3 import_circuitpython.py <repo> <sha>"""
import json, pathlib, re, sys
from cpp_lines import lines

repo, sha = pathlib.Path(sys.argv[1]), sys.argv[2]
out = pathlib.Path(__file__).parent.parent / "boards" / "circuitpython"
out.mkdir(parents=True, exist_ok=True)
ENTRY = re.compile(r"(?:MP_ROM_QSTR|MP_OBJ_NEW_QSTR)\(MP_QSTR_(\w+)\),\s*MP_(?:ROM|OBJ_FROM)_PTR\(&pin_(\w+)\)")
NAME = re.compile(r'#define\s+(MICROPY_HW_BOARD_NAME|MICROPY_HW_MCU_NAME)\s+"([^"]*)"')
done = skipped = 0
for pins_c in sorted(repo.glob("ports/*/boards/*/pins.c")):
    port, dirname = pins_c.parts[-4], pins_c.parts[-2]
    rel = pins_c.relative_to(repo).as_posix()
    pins = [{"pin": m.group(2), "function": m.group(1), "group": "board", "source": "s1", "quote": " ".join(raw.split()),
             **({"condition": cond} if cond else {})}
            for raw, code, cond in lines(pins_c.read_text(errors="replace")) if (m := ENTRY.search(code))]
    # board tables are ordered and looked up first-match (py/map.c, is_ordered), so later duplicates are unreachable
    seen = set()
    for p in pins:
        key = (p["function"], p.get("condition"))
        if key in seen:
            p["unreachable"] = "an earlier entry with this name wins in CircuitPython"
        seen.add(key)
    if not pins:
        skipped += 1; print("skipped (no pins):", rel); continue
    names = dict(NAME.findall((pins_c.parent / "mpconfigboard.h").read_text(errors="replace"))) if (pins_c.parent / "mpconfigboard.h").exists() else {}
    board = {"board": names.get("MICROPY_HW_BOARD_NAME", dirname), "aliases": [dirname], "mcu": names.get("MICROPY_HW_MCU_NAME", port),
             "origin": "imported", "sources": {"s1": {"url": f"https://raw.githubusercontent.com/adafruit/circuitpython/{sha}/{rel}", "retrieved": "2026-11-18"}},
             "pins": pins}
    (out / f"{port}-{dirname}.json").write_text(json.dumps(board, indent=1)); done += 1
print(f"imported {done}, skipped {skipped}")
