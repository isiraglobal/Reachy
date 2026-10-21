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
    """Installs required browser binaries for autonomous CLI execution."""
    system = platform.system()
    logger.info(f"[*] Detected operating system: {system} ({platform.machine()})")

    # Step 1: Check if Chrome or Chromium already exists
    existing = find_system_chrome()
    if existing:
        logger.info(f"✓ Found existing browser binary at: {existing}")

    # Step 2: Use agent-browser install if available
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
    """Executes a web errand or navigation task autonomously via CLI agent tools."""
    logger.info(f"[*] Commencing autonomous errand on: {url} (Action: {task})")
    report = {"url": url, "task": task, "success": False, "output": ""}

    agent_browser = shutil.which("agent-browser")
    if not agent_browser:
        logger.error("✗ agent-browser CLI binary is not available.")
        report["output"] = "agent-browser binary missing"
        return report

    # 1. Open the page
    open_args = [agent_browser, "open", url]
    if not headless:
        open_args.append("--headed")
    
    try:
        subprocess.run(open_args, capture_output=True, text=True, timeout=25, check=False)
        time.sleep(2)

        # 2. Perform requested errand
        if task == "snapshot":
            res = subprocess.run([agent_browser, "snapshot", "-i"], capture_output=True, text=True, timeout=15)
            report["output"] = res.stdout.strip()[:1000]
            report["success"] = (res.returncode == 0)
        elif task == "eval":
            res = subprocess.run(
                [agent_browser, "eval", "JSON.stringify({ title: document.title, url: window.location.href })"],
                capture_output=True,
                text=True,
                timeout=15
            )
            report["output"] = res.stdout.strip()
            report["success"] = (res.returncode == 0)
        elif task == "screenshot":
            screenshot_path = "browser_errand_screenshot.png"
            res = subprocess.run([agent_browser, "screenshot", screenshot_path], capture_output=True, text=True, timeout=15)
            report["output"] = f"Saved screenshot to {screenshot_path}"
            report["success"] = (res.returncode == 0)
        else:
            report["output"] = f"Unknown task: {task}"
    except Exception as e:
        report["output"] = str(e)
        logger.error(f"Errand execution error: {e}")

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
