#!/usr/bin/env python3
"""Generate boards/arduino-esp32/*.json from an arduino-esp32 checkout: python3 import_arduino_esp32.py <repo> <sha>"""
import json, pathlib, re, sys, urllib.request
from cpp_lines import lines

repo, sha = pathlib.Path(sys.argv[1]), sys.argv[2]
out = pathlib.Path(__file__).parent.parent / "boards" / "arduino-esp32"
out.mkdir(parents=True, exist_ok=True)
CONST = re.compile(r"static\s+(?:const|constexpr)\s+\w+\s+(\w+)\s*=\s*(\w+)\s*;")
DEFINE = re.compile(r"#define\s+(\w+)\s+(\w+)\s*$")
# a #define is a pin only if its name says so; CONST declarations always are
PIN_NAME = re.compile(r"(?:PIN|LED|BUTTON|BOOT|TX|RX|SDA|SCL|SS|MOSI|MISO|SCK)\w*$|\w*_PIN\w*$")


IDF = "https://raw.githubusercontent.com/espressif/esp-idf/ad20ded62a2d67a26e501fdc1905f43ba7ad6c81/components/soc/{}/include/soc/soc_caps.h"
_masks = {}


def valid_gpios(chip):
    """GPIO numbers that exist on this chip, per ESP-IDF's SOC_GPIO_VALID_GPIO_MASK (None if unknown)."""
    if chip not in _masks:
        try:
            t = urllib.request.urlopen(IDF.format(chip), timeout=30).read().decode()
            n = int(re.search(r"#define SOC_GPIO_PIN_COUNT\s+\(?(\d+)", t).group(1))
            mask = re.search(r"#define SOC_GPIO_VALID_GPIO_MASK\s+(.+)", t).group(1)
            _masks[chip] = set(range(n)) - {int(b) for b in re.findall(r"BIT(\d+)", mask)}
        except (OSError, AttributeError):
            _masks[chip] = None
    return _masks[chip]


def gpio(value, defs, chain, conds, depth=0):
    """Resolve 5, GPIO_NUM_5 or a name defined earlier in the file to an int; record the lines and #if conditions used."""
    if value.isdigit():
        return int(value)
    if m := re.fullmatch(r"GPIO_NUM_(\d+)", value):
        return int(m.group(1))
    if value in defs and depth < 8:
        v, quote, cond = defs[value]
        chain.append(quote)
        if cond:
            conds.append(cond)
        return gpio(v, defs, chain, conds, depth + 1)
    return None


# variant folder -> chip, from boards.txt (build.variant / build.mcu)
chips = {}
bt = (repo / "boards.txt").read_text(errors="replace")
props = dict(re.findall(r"^(\w+\.build\.(?:variant|mcu))=(\S+)", bt, re.M))
for k, v in props.items():
    if k.endswith(".build.variant") and (mcu := props.get(k[:-len("variant")] + "mcu")):
        chips.setdefault(v, set()).add(mcu)

done = skipped = invalid = 0
for h in sorted(repo.glob("variants/*/pins_arduino.h")):
    rel, name = h.relative_to(repo).as_posix(), h.parts[-2]
    chip = next(iter(chips[name])) if len(chips.get(name, ())) == 1 else None
    valid = valid_gpios(chip) if chip else None
    defs, pins = {}, []
    for raw, code, cond in lines(h.read_text(errors="replace")):
        m = CONST.search(code) or DEFINE.match(code)
        if not m:
            continue
        # under BOARD_HAS_PIN_REMAP the numbers are logical Arduino pins, not GPIOs (Nano Nora, Ozobot): ignore entirely
        if cond and "PIN_REMAP" in cond and not cond.startswith("not ("):
            continue
        key, value = m.groups()
        quote = " ".join(raw.split())
        defs.setdefault(key, (value, quote, cond))
        if m.re is DEFINE and not PIN_NAME.match(key):
            continue
        chain, conds = [], [cond] if cond else []
        n = gpio(value, defs, chain, conds)
        if n is None:
            continue
        pin = {"pin": f"GPIO{n}", "function": key, "group": "board", "source": "s1", "quote": quote}
        if chain:
            pin["also"] = chain
        if conds:
            pin["condition"] = " && ".join(dict.fromkeys(conds))
        if valid is not None and n not in valid:
            pin["invalid"] = f"GPIO{n} does not exist on {chip} (ESP-IDF SOC_GPIO_VALID_GPIO_MASK)"
            invalid += 1
        pins.append(pin)
    if not pins:
        skipped += 1; print("skipped (no numeric pins):", rel); continue
    board = {"board": name, "aliases": [name], "mcu": chip or "ESP32 family", "origin": "imported",
             "sources": {"s1": {"url": f"https://raw.githubusercontent.com/espressif/arduino-esp32/{sha}/{rel}", "retrieved": "2026-11-18"}},
             "pins": pins}
    (out / f"{name}.json").write_text(json.dumps(board, indent=1)); done += 1
print(f"imported {done}, skipped {skipped}, pins on non-existent GPIOs {invalid}")
