#!/usr/bin/env python3
"""Autonomous Browser Installer & Setup Tool for CLI Agents.

Allows an AI agent running in headless, VPS, or local environments to:
1. Detect or download Chromium / Google Chrome binaries automatically.
2. Install agent-browser or Playwright browser automation engines.
3. Verify headless execution, DOM navigation, and web interaction without a GUI.
4. Run errands or web tasks autonomously.
"""

import argparse
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("browser_installer")


def find_system_chrome() -> str | None:
    """Locates existing Chrome/Chromium installation."""
    candidates = [
        # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        # Linux
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
    ]
    for c in candidates:
        if os.path.exists(c) and os.access(c, os.X_OK):
            return c
    
    # Path lookups
    for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
        found = shutil.which(name)
        if found:
            return found
            
    return None


def install_browser(with_deps: bool = True) -> bool:
    """Installs Chromium for Playwright (preferred), with legacy fallbacks."""
    system = platform.system()
    logger.info(f"[*] Detected operating system: {system} ({platform.machine()})")

    # Step 1: Playwright-managed Chromium
    try:
        cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
        if with_deps and system == "Linux":
            cmd.append("--with-deps")
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            logger.info("✓ Playwright Chromium installed successfully.")
            return True
        logger.warning(f"Playwright install output: {result.stdout} {result.stderr}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Playwright install failed: {exc}")

    # Step 2: Legacy agent-browser fallback
    agent_browser = shutil.which("agent-browser")
    if agent_browser:
        logger.info("[*] Executing 'agent-browser install'...")
        cmd = [agent_browser, "install"]
        if with_deps and system == "Linux":
            cmd.append("--with-deps")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0:
                logger.info("✓ agent-browser browser binaries installed successfully.")
                return True
            else:
                logger.warning(f"agent-browser install output: {res.stdout} {res.stderr}")
        except Exception as e:
            logger.warning(f"Error running agent-browser install: {e}")

    # Step 3: Platform specific installation for Linux VPS / headless environments
    if system == "Linux":
        logger.info("[*] Attempting Linux package manager installation (apt-get)...")
        if shutil.which("apt-get"):
            try:
                subprocess.run(["sudo", "apt-get", "update", "-y"], check=False)
                install_res = subprocess.run(
                    ["sudo", "apt-get", "install", "-y", "chromium-browser", "chromium"],
                    check=False
                )
                if install_res.returncode == 0:
                    logger.info("✓ Chromium installed via apt-get.")
                    return True
            except Exception as e:
                logger.warning(f"apt-get installation attempt returned: {e}")

    return find_system_chrome() is not None or agent_browser is not None


def run_autonomous_errand(url: str, task: str = "snapshot", headless: bool = True) -> dict:
    """Executes a navigation/inspection errand via Playwright."""
    logger.info(f"[*] Commencing autonomous errand on: {url} (Action: {task})")
    report = {"url": url, "task": task, "success": False, "output": ""}
    try:
        from reachy.browser import PlaywrightDriver

        driver = PlaywrightDriver(headed=not headless)
        try:
            driver.open(url)
            if task == "snapshot":
                data = driver.eval(
                    "({title: document.title, url: location.href, text: (document.body?.innerText || '').slice(0, 2000)})"
                )
                report["output"] = json.dumps(data, ensure_ascii=False)[:2000]
            elif task == "eval":
                data = driver.eval("({title: document.title, url: window.location.href})")
                report["output"] = json.dumps(data, ensure_ascii=False)
            elif task == "screenshot":
                path = driver.screenshot("browser_errand_screenshot.png")
                report["output"] = f"Saved screenshot to {path}"
            else:
                report["output"] = f"Unknown task: {task}"
                return report
            report["success"] = True
        finally:
            driver.close()
    except Exception as exc:  # noqa: BLE001
        report["output"] = str(exc)
        logger.error(f"Errand execution error: {exc}")
    return report


def main():
    parser = argparse.ArgumentParser(description="Autonomous Browser Installer & Setup for AI Agents")
    parser.add_argument("--install", action="store_true", help="Download and install browser binaries")
    parser.add_argument("--test", action="store_true", help="Run a verification errand after install")
    parser.add_argument("--url", type=str, default="https://www.google.com/maps", help="URL to run errand on")
    parser.add_argument("--headed", action="store_true", help="Run in headed mode with display")
    parser.add_argument("--task", type=str, default="eval", choices=["eval", "snapshot", "screenshot"], help="Errand task to execute")
    args = parser.parse_args()

    print("=" * 60)
    print("🤖 Reachy Autonomous Browser Installer & Errand Runner")
    print("   Engineered by ISIRA Automations for AI CLI Agents")
    print("=" * 60)

    if args.install or not find_system_chrome():
        logger.info("[*] Running browser binary verification/installation...")
        installed = install_browser(with_deps=True)
        if installed:
            logger.info("✓ Browser binaries verified and operational.")
        else:
            logger.warning("! Could not automatically download browser; checking fallback runners.")

    # Run errand / diagnostic
    errand_res = run_autonomous_errand(url=args.url, task=args.task, headless=not args.headed)
    print("\n--- Errand Execution Report ---")
    print(f"Target URL : {errand_res['url']}")
    print(f"Action     : {errand_res['task']}")
    print(f"Success    : {'✓ YES' if errand_res['success'] else '✗ NO'}")
    print(f"Output     : {errand_res['output'][:300]}")
    print("=" * 60)

    if not errand_res["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
