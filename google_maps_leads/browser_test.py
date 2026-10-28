#!/usr/bin/env python3
"""Browser self-test for CLI agents and operators.

Playwright is the supported backend. The legacy ``agent-browser`` CLI is
reported as an optional fallback. No process is killed and no challenge is
bypassed.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("browser_test")


def agent_browser_available() -> tuple[bool, str]:
    binary = shutil.which("agent-browser")
    if not binary:
        return False, "not installed"
    try:
        result = subprocess.run(["agent-browser", "--version"], capture_output=True, text=True, timeout=10)
        return True, result.stdout.strip() or "installed"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def test_browser_diagnostics(headless: bool = True, target_url: str | None = None) -> dict:
    from reachy.browser import check_browser

    report = check_browser(headless=headless, target_url=target_url).as_dict()
    available, version = agent_browser_available()
    report["agent_browser_fallback"] = {"available": available, "version": version}
    report["success"] = bool(report["launch_ok"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Reachy browser diagnostic (Playwright preferred)")
    parser.add_argument("--headed", action="store_true", help="Launch in headed mode (default: headless)")
    parser.add_argument("--url", type=str, default=None, help="Optional target URL")
    args = parser.parse_args()

    results = test_browser_diagnostics(headless=not args.headed, target_url=args.url)
    print("\n" + "=" * 58)
    print("BROWSER DIAGNOSTIC AUDIT REPORT")
    print("=" * 58)
    print(json.dumps(results, indent=2))
    print("=" * 58)
    if results["success"]:
        print("BROWSER ENVIRONMENT IS READY.")
        sys.exit(0)
    print("BROWSER VERIFICATION FAILED.")
    for step in results.get("remediation") or []:
        print(f"  remediation: {step}")
    sys.exit(1)


if __name__ == "__main__":
    main()
