"""Browser driver abstraction for Google Maps extraction.

Playwright is preferred. The legacy external ``agent-browser`` CLI is retained
as a fallback so existing installations keep working. Neither driver attempts
to bypass CAPTCHAs, access controls, or rate limits.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any, Optional, Protocol


class BrowserDriver(Protocol):
    def open(self, url: str) -> None:
        ...

    def eval(self, js: str) -> Any:
        ...

    def wait(self, milliseconds: int) -> None:
        ...

    def get_url(self) -> str:
        ...

    def set_viewport(self, width: int, height: int) -> None:
        ...

    def close(self) -> None:
        ...


class AgentBrowserDriver:
    name = "agent-browser"

    def __init__(self, headed: bool = True, proxy: Optional[str] = None, timeout: int = 35):
        self.headed = headed
        self.proxy = proxy
        self.timeout = timeout
        if not shutil.which("agent-browser"):
            raise RuntimeError("agent-browser CLI is not installed")

    def _run(self, args: list[str], timeout: Optional[int] = None) -> tuple[str, int]:
        try:
            result = subprocess.run(
                ["agent-browser", *args],
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
                check=False,
            )
            return result.stdout.strip(), result.returncode
        except subprocess.TimeoutExpired:
            return "", 1
        except OSError:
            return "", 1

    def open(self, url: str) -> None:
        args = ["open", url]
        if self.headed:
            args.append("--headed")
        if self.proxy:
            args.extend(["--proxy", self.proxy])
        self._run(args, timeout=25)

    def eval(self, js: str) -> Any:
        output, code = self._run(["eval", js])
        if code != 0 or not output:
            return None
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output

    def wait(self, milliseconds: int) -> None:
        value = str(max(1, int(milliseconds / 1000)))
        self._run(["wait", value], timeout=int(milliseconds / 1000) + 10)

    def get_url(self) -> str:
        output, _ = self._run(["get", "url"], timeout=5)
        return output

    def set_viewport(self, width: int, height: int) -> None:
        self._run(["set", "viewport", str(width), str(height)])

    def close(self) -> None:
        return None


class PlaywrightDriver:
    name = "playwright"

    def __init__(self, headed: bool = True, viewport: tuple[int, int] = (1920, 1080), user_data_dir=None):
        from reachy.browser import PlaywrightDriver as _Driver

        self._driver = _Driver(headed=headed, viewport=viewport, user_data_dir=user_data_dir)

    def open(self, url: str) -> None:
        self._driver.open(url)

    def eval(self, js: str) -> Any:
        return self._driver.eval(js)

    def wait(self, milliseconds: int) -> None:
        self._driver.wait(milliseconds)

    def get_url(self) -> str:
        return self._driver.get_url()

    def set_viewport(self, width: int, height: int) -> None:
        self._driver.viewport = (width, height)

    def close(self) -> None:
        self._driver.close()


def build_driver(
    backend: str = "auto",
    headed: bool = True,
    proxy: Optional[str] = None,
    viewport: tuple[int, int] = (1920, 1080),
) -> BrowserDriver:
    errors = []
    if backend in {"auto", "playwright"}:
        try:
            return PlaywrightDriver(headed=headed, viewport=viewport)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"playwright: {exc}")
            if backend == "playwright":
                raise RuntimeError("; ".join(errors)) from exc
    if backend in {"auto", "agent-browser"}:
        return AgentBrowserDriver(headed=headed, proxy=proxy)
    raise RuntimeError("no browser driver available: " + "; ".join(errors))
