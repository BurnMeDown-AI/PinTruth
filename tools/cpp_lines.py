"""Yield (raw_line, code, condition) for C source: comments removed, enclosing #if condition tracked."""
import re

GUARD = re.compile(r"#\s*ifndef\s+\w+_H_?\s*$", re.I)  # include guard, not a real condition


def lines(text):
    stripped = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group().count("\n"), text, flags=re.S)  # keep line count
    stack = []
    for raw, code in zip(text.splitlines(), stripped.splitlines()):
        code = code.split("//", 1)[0].strip()
        d = re.match(r"#\s*(if|ifdef|ifndef|elif|else|endif)\b\s*(.*)", code)
        if d:
            kind, cond = d.groups()
            if kind in ("if", "ifdef", "ifndef"):
                stack.append(None if GUARD.match(code) else f"{'!' if kind == 'ifndef' else ''}{cond}".strip())
            elif stack and kind == "elif":
                stack[-1] = cond
            elif stack and kind == "else" and stack[-1]:
                stack[-1] = f"not ({stack[-1]})"
            elif stack and kind == "endif":
                stack.pop()
            continue
        yield raw, code, " && ".join(c for c in stack if c) or None
