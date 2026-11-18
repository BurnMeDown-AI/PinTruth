#!/usr/bin/env python3
"""PinTruth: board pinouts where every pin carries its source URL and a verbatim quote."""
import collections, json, pathlib, re, sys, urllib.error, urllib.request

BOARDS = pathlib.Path(__file__).parent / "boards"
# verify fetches URLs taken from board files (which may come from a PR), so only these are allowed
ALLOWED_SOURCES = ("https://raw.githubusercontent.com/",)
MAX_BYTES = 5_000_000
norm = lambda s: " ".join(s.split())
safe = lambda s: re.sub(r"[\x00-\x1f\x7f-\x9f‎‏‪-‮⁦-⁩]", "?", str(s))  # terminal/bidi tricks


def load_all(name):
    """Every board whose file stem, board name or alias matches (case-insensitive)."""
    n, hits = name.lower(), []
    for f in sorted(BOARDS.rglob("*.json")):
        b = json.loads(f.read_text())
        if n in {f.stem.lower(), b["board"].lower(), *(a.lower() for a in b.get("aliases", []))}:
            hits.append(b)
    if not hits:
        raise SystemExit(f"unknown board: {name}")
    return hits


def load(name):
    return load_all(name)[0]


def fetch(url):
    if not url.startswith(ALLOWED_SOURCES):
        raise ValueError(f"source not allowed (must start with {' or '.join(ALLOWED_SOURCES)})")
    with urllib.request.urlopen(url, timeout=30) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("source larger than 5 MB")
    return norm(data.decode("utf-8", "replace"))


def check(b, online=False):
    """Return a list of problems; empty means the board file is sound."""
    if not isinstance(b, dict):
        return ["board file is not a JSON object"]
    errs = [f"missing '{k}'" for k in ("board", "mcu", "sources", "pins") if k not in b]
    cache = {}
    for p in b.get("pins", []):
        tag = f"{p.get('pin')} {p.get('function')}"
        if not p.get("pin") or not p.get("function") or not p.get("quote"):
            errs.append(f"{tag}: needs pin, function and quote")
            continue
        src = b.get("sources", {}).get(p.get("source"))
        if not src or not isinstance(src.get("url"), str):
            errs.append(f"{tag}: unknown source '{p.get('source')}'")
        elif online:
            if src["url"] not in cache:
                try:
                    cache[src["url"]] = fetch(src["url"])
                except (ValueError, urllib.error.URLError, OSError) as e:
                    cache[src["url"]] = e
            got = cache[src["url"]]
            if isinstance(got, Exception):
                errs.append(f"{tag}: cannot check {src['url']}: {got}")
            else:
                for q in [p["quote"], *p.get("also", [])]:
                    if norm(q) not in got:
                        errs.append(f"{tag}: quote not found at {src['url']}: {q[:60]}")
    return errs


def conflicts(b):
    """Names the source itself maps to more than one pin under the same condition."""
    d = collections.defaultdict(set)
    for p in b.get("pins", []):
        if not p.get("unreachable"):
            d[(p.get("function"), p.get("condition"))].add(p.get("pin"))
    return {k[0]: sorted(v) for k, v in d.items() if len(v) > 1}


def show(boards):
    for b in boards:
        print(safe(f"{b['board']} ({b['mcu']}) [{b.get('origin', '?')}] aliases: {', '.join(b.get('aliases', []))}"))
        for p in b["pins"]:
            cond = f"  only if {p['condition']}" if p.get("condition") else ""
            cond += f"  UNREACHABLE: {p['unreachable']}" if p.get("unreachable") else ""
            cond += f"  INVALID: {p['invalid']}" if p.get("invalid") else ""
            print(safe(f"{p['pin']:<7} {p['group']:<9} {p['function']}{cond}  <- {b['sources'][p['source']]['url']}"))
            for q in [p["quote"], *p.get("also", [])]:
                print(safe(f"        \"{q}\""))
        for name, pins in conflicts(b).items():
            print(safe(f"WARNING: this source maps {name} to {' and '.join(pins)}"))
    if len(boards) > 1:  # same board from several sources: say where they disagree
        maps = [{p["function"]: p["pin"] for p in b["pins"] if not p.get("condition") and not p.get("unreachable") and not p.get("invalid")} for b in boards]
        for name in sorted(set.intersection(*(set(m) for m in maps))):
            if len({m[name] for m in maps}) > 1:
                print(safe(f"DISAGREE: {name} = " + " vs ".join(f"{m[name]} ({b['sources']['s1']['url'].split('/')[4]})" for m, b in zip(maps, boards))))
    aliases = {a.lower() for b in boards for a in b.get("aliases", [])}
    for e in errata():
        if e["board"].lower() in aliases:
            print(safe(f"ERRATUM [{e['confidence']}] {'/'.join(e['names'])}: {e['verdict']}"))
            for ev in e["evidence"]:
                print(safe(f"        {ev['url']}: \"{ev['quote']}\"" + (f" ({ev['note']})" if ev.get("note") else "")))


def errata():
    """Hand-researched verdicts on cross-source disagreements (errata.json)."""
    f = BOARDS.parent / "errata.json"
    return json.loads(f.read_text()) if f.exists() else []


def check_errata(online):
    """Errata evidence on allowed hosts is re-checked like pins; other evidence (vendor PDFs) was checked by hand."""
    errs, by_hand, cache = [], 0, {}
    for e in errata():
        for ev in e.get("evidence", []):
            if not ev.get("url", "").startswith(ALLOWED_SOURCES):
                by_hand += 1
                continue
            if online:
                if ev["url"] not in cache:
                    try:
                        cache[ev["url"]] = fetch(ev["url"])
                    except (ValueError, urllib.error.URLError, OSError) as x:
                        cache[ev["url"]] = x
                got = cache[ev["url"]]
                if isinstance(got, Exception) or norm(ev["quote"]) not in got:
                    errs.append(f"erratum {e['board']}: evidence not found: {ev['quote'][:60]}")
    return errs, by_hand


def main(argv):
    if len(argv) >= 3 and argv[1] == "show":
        show(load_all(argv[2]))
    elif len(argv) >= 2 and argv[1] == "verify":
        online = "--online" in argv
        bad = warn = 0
        for f in sorted(BOARDS.rglob("*.json")):
            try:
                b = json.loads(f.read_text())
            except ValueError as e:
                b = None
                errs = [f"invalid JSON: {e}"]
            else:
                errs = check(b, online)
            bad += len(errs)
            c = conflicts(b) if isinstance(b, dict) else {}
            warn += len(c)
            if errs or c or "-v" in argv:
                print(f"{f.relative_to(BOARDS)}: {'OK' if not errs else ''}")
            for e in errs:
                print("  -", safe(e))
            for name, pins in c.items():
                print("  ! warning:", safe(f"source maps {name} to {' and '.join(pins)}"))
        errs, by_hand = check_errata(online)
        bad += len(errs)
        for e in errs:
            print("  -", safe(e))
        print(f"{bad} problems, {warn} warnings ({by_hand} errata quotes are from vendor PDFs, checked by hand)")
        return 1 if bad else 0
    else:
        print("usage: pintruth.py show <board> | verify [--online] [-v]")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
