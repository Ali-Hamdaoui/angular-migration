#!/usr/bin/env python3
"""Terminal lifecycle script (V2 F23-02): drive a migration setup -> seal via the API.

Usage:
    python3 scripts/terminal-lifecycle.py <base_url> <run_id> [--drive N]

The script drives the full lifecycle through the terminal/API surface only:
it prints the lifecycle sequence, evidence, and (optionally) advances the chain
a bounded number of steps.
"""

import json
import sys
import urllib.request


def _request(base: str, method: str, path: str, body: dict | None = None):
    url = f"{base}{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        return {"error_code": error.code, "body": error.read().decode()[:500]}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/")
    run_id = sys.argv[2]
    drive_steps = 0
    if "--drive" in sys.argv:
        drive_steps = int(sys.argv[sys.argv.index("--drive") + 1])

    print(f"== lifecycle sequence for run {run_id} ==")
    sequence = _request(base, "GET", f"/terminal/runs/{run_id}/lifecycle")
    print(json.dumps(sequence, indent=2, sort_keys=True))

    print(f"== lifecycle evidence for run {run_id} ==")
    evidence = _request(base, "GET", f"/terminal/runs/{run_id}/lifecycle/evidence")
    print(f"events: {len(evidence.get('events', []))}, seals: {len(evidence.get('seals', []))}")

    for step in range(drive_steps):
        print(f"== drive step {step + 1} ==")
        sequence = _request(base, "POST", f"/terminal/runs/{run_id}/lifecycle/drive", {})
        print(f"phase: {sequence.get('current_phase')} | chain: {sequence.get('chain_status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
