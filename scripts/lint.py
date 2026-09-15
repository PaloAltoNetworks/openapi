#!/usr/bin/env python3
"""Run Spectral and hold inherited defects at their current count.

The base specification arrived with real defects -- `$ref` siblings that
OpenAPI 3.0 silently ignores, arrays with no `items`, a duplicated enum entry.
Two bad options: fail CI from day one, or silence the rules and lose the signal.

So instead the counts are baselined. Existing debt is visible in
.spectral-baseline.json and in every run's output; a count going *up* fails.
Debt can only shrink.

Usage:
    scripts/lint.py                 # check against the baseline
    scripts/lint.py --update        # re-record the baseline (review the diff)
    scripts/lint.py --json out.json # also write raw Spectral findings
"""

from __future__ import annotations

import argparse
import collections
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "openapi.yaml"
BASELINE = ROOT / ".spectral-baseline.json"

SEVERITY = {0: "error", 1: "warn", 2: "info", 3: "hint"}


def run_spectral() -> list[dict]:
    if shutil.which("spectral"):
        cmd = ["spectral"]
    else:
        cmd = ["npx", "--yes", "@stoplight/spectral-cli@6.16.3"]
    cmd += ["lint", str(SPEC), "--format", "json", "--quiet"]

    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    stdout = proc.stdout.strip()
    if not stdout:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit("spectral produced no output")
    return json.loads(stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    findings = run_spectral()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(findings, indent=2) + "\n")

    counts = collections.Counter(f["code"] for f in findings)
    severities = {f["code"]: SEVERITY[f["severity"]] for f in findings}

    if args.update:
        BASELINE.write_text(
            json.dumps(
                {
                    "_comment": (
                        "Inherited defect counts. A count going up fails CI; debt can "
                        "only shrink. Regenerate with scripts/lint.py --update and "
                        "review the diff -- a number going down is the good case and "
                        "should be committed."
                    ),
                    "counts": dict(sorted(counts.items())),
                },
                indent=2,
            )
            + "\n"
        )
        print(f"baseline written: {sum(counts.values())} finding(s) across {len(counts)} rule(s)")
        return 0

    baseline = json.loads(BASELINE.read_text())["counts"] if BASELINE.exists() else {}

    regressions, improvements, novel = [], [], []
    for code in sorted(set(counts) | set(baseline)):
        now, was = counts.get(code, 0), baseline.get(code, 0)
        if code not in baseline and now:
            novel.append((code, now))
        elif now > was:
            regressions.append((code, was, now))
        elif now < was:
            improvements.append((code, was, now))

    total = sum(counts.values())
    print(f"spectral: {total} finding(s) across {len(counts)} rule(s)\n")
    for code, n in counts.most_common():
        base = baseline.get(code, 0)
        delta = "" if n == base else f"  (baseline {base})"
        print(f"  {n:5d}  {severities[code]:6}  {code}{delta}")

    if improvements:
        print("\nimproved -- run scripts/lint.py --update and commit the baseline:")
        for code, was, now in improvements:
            print(f"    {code}: {was} -> {now}")

    if novel or regressions:
        print()
        for code, n in novel:
            print(f"  FAIL  new rule violated: {code} ({n})")
        for code, was, now in regressions:
            print(f"  FAIL  {code} rose from {was} to {now}")
        print("\nInherited debt is allowed to stay; it is not allowed to grow.")
        return 1

    print("\nno regressions against the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
