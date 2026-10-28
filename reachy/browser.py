"""Playwright-based browser diagnostics and a local interactive worker.

Browser automation is deliberately isolated from email credentials: this module
has no access to account secrets, tokens, or campaign execution. Reachy does
not bypass CAPTCHAs, access controls, rate limits, or site restrictions.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

MISSING_DEP_PATTERNS = [
    r"libnss3",
    r"libatk",
    r"libgbm",
    r"libasound",
    r"libxkbcommon",
    r"Host system is missing dependencies",
    r"error while loading shared libraries",
    r"cannot open shared object file",
]


@dataclass
class BrowserReport:
    playwright_available: bool = False
    playwright_version: Optional[str] = None
    chromium_installed: bool = False
    browser_version: Optional[str] = None
    launch_ok: bool = False
    headless: bool = True
    page_title: Optional[str] = None
    missing_dependencies: list[str] = field(default_factory=list)
    error: Optional[str] = None
    remediation: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.launch_ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "playwright_available": self.playwright_available,
            "playwright_version": self.playwright_version,
            "chromium_installed": self.chromium_installed,
            "browser_version": self.browser_version,
            "launch_ok": self.launch_ok,
            "headless": self.headless,
            "page_title": self.page_title,
            "missing_dependencies": self.missing_dependencies,
            "error": self.error,
            "remediation": self.remediation,
            "success": self.success,
        }


def check_browser(
    headless: bool = True,
    target_url: Optional[str] = None,
    playwright_factory=None,
) -> BrowserReport:
    report = BrowserReport(headless=headless)
    try:
        if playwright_factory is None:
            from playwright.sync_api import sync_playwright as playwright_factory
        manager = playwright_factory()
        playwright = manager.__enter__() if hasattr(manager, "__enter__") else manager
    except Exception as exc:  # noqa: BLE001
        report.error = f"Playwright is not installed: {exc}"
        report.remediation.append("pip install 'reachy[browser]'")
        report.remediation.append("python -m playwright install chromium")
        return report

    report.playwright_available = True
    try:
        try:
            from importlib.metadata import version as package_version

            report.playwright_version = package_version("playwright")
        except Exception:
            report.playwright_version = getattr(playwright, "version", None)
        try:
            executable = playwright.chromium.executable_path
            report.chromium_installed = bool(executable and Path(executable).exists())
        except Exception:
            report.chromium_installed = False

        browser = playwright.chromium.launch(headless=headless, timeout=30_000)
        try:
            report.launch_ok = True
            report.browser_version = browser.version
            page = browser.new_page()
            try:
                if target_url:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30_000)
                else:
                    page.set_content("<title>Reachy browser check</title><body>ok</body>")
                report.page_title = page.title()
            finally:
                page.close()
        finally:
            browser.close()
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        report.error = message
        report.missing_dependencies = [
            pattern for pattern in MISSING_DEP_PATTERNS if re.search(pattern, message, re.I)
        ]
        if re.search(r"Executable doesn't exist|playwright install", message, re.I):
            report.remediation.append("python -m playwright install chromium")
        if report.missing_dependencies or re.search(r"missing dependencies", message, re.I):
            report.remediation.append("sudo python -m playwright install --with-deps chromium")
        if not report.remediation:
            report.remediation.append("Run with --headed to inspect; check chrome/chromium availability.")
    finally:
        try:
            manager.__exit__(None, None, None)  # type: ignore[attr-defined]
        except Exception:
            pass
    return report


class PlaywrightDriver:
    """Driver used by the scraper and the interactive authentication worker."""

    def __init__(
        self,
        headed: bool = True,
        user_data_dir: Optional[str | Path] = None,
        viewport: tuple[int, int] = (1920, 1080),
        timeout_ms: int = 30_000,
    ):
        self.headed = headed
        self.user_data_dir = str(user_data_dir or (Path.home() / ".reachy" / "browser-profile"))
        self.viewport = viewport
        self.timeout_ms = timeout_ms
        self._manager = None
        self._context = None
        self._page = None

    def _ensure(self):
        if self._page is not None:
            return self._page
        from playwright.sync_api import sync_playwright

        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
        self._manager = sync_playwright().start()
        self._context = self._manager.chromium.launch_persistent_context(
            self.user_data_dir,
            headless=not self.headed,
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        return self._page

    def open(self, url: str) -> None:
        self._ensure().goto(url, wait_until="domcontentloaded")

    def eval(self, js: str) -> Any:
        return self._ensure().evaluate(js)

    def wait(self, milliseconds: int) -> None:
        self._ensure().wait_for_timeout(milliseconds)

    def get_url(self) -> str:
        return self._ensure().url

    def title(self) -> str:
        return self._ensure().title()

    def screenshot(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._ensure().screenshot(path=str(target), full_page=True)
        return target

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._manager is not None:
            try:
                self._manager.stop()
            except Exception:
                pass
            self._manager = None
        self._page = None


def run_interactive_session(url: str, user_data_dir: Optional[str | Path] = None) -> None:
    """Open a visible browser that keeps cookies for manual authentication.

    The operator completes any normal login/consent step personally. Reachy
    waits; it does not solve or bypass challenges.
    """
    driver = PlaywrightDriver(headed=True, user_data_dir=user_data_dir)
    try:
        driver.open(url)
        print("Browser open. Complete any sign-in or consent step, then press Enter here.")
        input()
    finally:
        driver.close()
