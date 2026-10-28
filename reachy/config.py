"""Configuration and filesystem layout.

Secrets are never stored in configuration files. Provider credentials live in the
encrypted ``account_secrets`` table; the encryption key comes from
``REACHY_SECRET_KEY`` or a 0600 key file under the Reachy home directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional


DEFAULT_HOME = Path.home() / ".reachy"


def load_dotenv(path: Optional[str | Path] = None) -> None:
    """Load key-value pairs from a .env file into os.environ if not already present."""
    candidates = [Path(path)] if path else [Path(".env"), DEFAULT_HOME / ".env"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
            except Exception:
                pass


@dataclass(frozen=True)
class ReachyConfig:
    home: Path
    db_path: Path
    secret_key_path: Path
    log_path: Path
    test_recipient: Optional[str] = None
    allow_catch_all: bool = False
    catch_all_probe_enabled: bool = False
    reconcile_grace_seconds: int = 900
    unsubscribe_footer: str = (
        "Reply with 'unsubscribe' and we will remove you from all future messages."
    )

    @classmethod
    def load(
        cls,
        home: Optional[str | Path] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> "ReachyConfig":
        load_dotenv()
        env = dict(os.environ if env is None else env)
        root = Path(home or env.get("REACHY_HOME") or DEFAULT_HOME).expanduser().resolve()
        db_path = Path(env.get("REACHY_DB", root / "reachy.sqlite3")).expanduser()
        secret_path = Path(
            env.get("REACHY_SECRET_KEY_PATH", root / "secret.key")
        ).expanduser()
        log_path = Path(env.get("REACHY_LOG", root / "reachy.log")).expanduser()
        return cls(
            home=root,
            db_path=db_path,
            secret_key_path=secret_path,
            log_path=log_path,
            test_recipient=env.get("REACHY_TEST_RECIPIENT") or None,
            allow_catch_all=_as_bool(env.get("REACHY_ALLOW_CATCH_ALL")),
            catch_all_probe_enabled=_as_bool(env.get("REACHY_CATCH_ALL_PROBE")),
            reconcile_grace_seconds=int(env.get("REACHY_RECONCILE_GRACE", "900")),
            unsubscribe_footer=env.get("REACHY_UNSUBSCRIBE_FOOTER", cls.unsubscribe_footer),
        )

    def ensure_home(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.home, 0o700)
        except OSError:
            pass
        if self.db_path.parent and not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.log_path.parent and not self.log_path.parent.exists():
            self.log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    @property
    def secret_key_env(self) -> Optional[str]:
        return os.environ.get("REACHY_SECRET_KEY") or None


def _as_bool(value: Optional[str]) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"} if value else False
