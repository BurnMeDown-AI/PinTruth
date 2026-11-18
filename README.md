# PinTruth

Cited pinout data for AI coding agents. AI assistants invent GPIO numbers; PinTruth gives them pins where
**every pin carries its source URL and a verbatim quote**, and CI re-checks each quote against the live source.

```bash
python3 pintruth.py show cyd          # pins an agent may use, with sources
python3 pintruth.py verify --online   # re-fetch every source, confirm every quote still appears
python3 -m unittest
```

Standard library only. Boards live in `boards/` (curated files at the top, imported ones in subfolders). To add a pin: add the source once, then the pin with its
exact quote. `verify --online` fails if the quote is not on the page. The agent skill is `skills/pintruth/SKILL.md`.

Boards so far: 1 curated (ESP32-2432S028R "CYD") plus 1,065 imported from open board-definition files, ~41,000 pins:
CircuitPython `pins.c` (651 boards, `tools/import_circuitpython.py`) and arduino-esp32 `pins_arduino.h` (414 boards,
`tools/import_arduino_esp32.py`). Each file is pinned to a source commit. Every pin is re-checked against its source by
`verify --online`; a pin resolved through other names (`SDA = PIN_SDA`) carries every line of that chain as evidence.

## What the data does and doesn't tell you

- Imported names (`D5`, `SDA`, `LED_BUILTIN`) are what one framework calls a pin, not electrical facts (input-only, strapping).
- Commented-out lines are skipped. Pins inside `#if` blocks keep their condition (`only if ...`). Under arduino-esp32's
  `BOARD_HAS_PIN_REMAP` the numbers are logical, not GPIOs, so that branch is ignored.
- **INVALID**: 8 arduino-esp32 pins name a GPIO that does not exist on the board's chip (per ESP-IDF's valid-GPIO mask at a
  pinned commit). These are upstream errors. 58 arduino-esp32 boards have no chip in `boards.txt` and are not range-checked.
  All 11,386 CircuitPython ESP pins are valid for their chip.
- **UNREACHABLE**: 7 CircuitPython boards list one name twice. CircuitPython's board table is ordered and looked up first-match
  (`py/map.c`), so the later entry can never be used.
- **DISAGREE**: on the 46 boards both sources define, 530 of 581 shared names agree. `errata.json` holds hand-researched
  verdicts with evidence, printed by `show` as `ERRATUM [confirmed|likely|convention|unresolved]`. Confirmed so far:
  CircuitPython's `lolin_s3_mini_pro` has MOSI/MISO swapped (WEMOS schematic). Disagreements without an erratum
  (several M5Stack, BPI and Qualia boards) look like different default buses but have not been reviewed.
- A quote proves what the source says, not that it is right.

## Security

`verify --online` only fetches `https://raw.githubusercontent.com/` URLs, caps each download at 5 MB, and reports
unreachable sources instead of crashing. `show` neutralises terminal control and text-direction characters. CI runs with a
read-only token and a pinned checkout action.

## Licenses

Code, curated boards and `errata.json`: MIT. Imported data keeps its source's license:
`boards/circuitpython/` (MIT, see its NOTICE), `boards/arduino-esp32/` (LGPL-2.1, see its LICENSE). The CYD file quotes
[witnessmenow/ESP32-Cheap-Yellow-Display](https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display) (MIT).
