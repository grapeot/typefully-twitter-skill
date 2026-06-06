"""Configuration and capability diagnostics."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigError


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file(path: Path, *, override: bool = False) -> bool:
    if not path.exists():
        return False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"\'')
        if key and (override or key not in os.environ):
            os.environ[key] = value
    return True


def load_dotenv(explicit_env_file: str | None = None) -> list[Path]:
    """Load .env files from explicit path, cwd parents, and project parents."""
    candidates: list[Path] = []
    if explicit_env_file:
        candidates.append(Path(explicit_env_file).expanduser().resolve())
    env_from_var = os.getenv("TYPEFULLY_TWITTER_ENV_FILE")
    if env_from_var:
        candidates.append(Path(env_from_var).expanduser().resolve())
    cwd = Path.cwd()
    candidates.extend(parent / ".env" for parent in [cwd, *cwd.parents])
    candidates.extend(parent / ".env" for parent in [PROJECT_ROOT, *PROJECT_ROOT.parents])

    loaded: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if _load_env_file(path):
            loaded.append(path)
    return loaded


def resolve_secret_reference(value: str | None) -> str | None:
    if not value or not value.startswith("op://"):
        return value

    result = subprocess.run(
        ["op", "read", value],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise ConfigError("1password", [], f"Failed to resolve 1Password reference: {result.stderr.strip()}")
    return result.stdout.strip()


def _mask(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def env_bool(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", ""}:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    typefully_api_key: str | None
    typefully_social_set_id: str | None
    typefully_authorization: str | None
    typefully_account: str | None
    typefully_session: str | None
    typefully_cookie: str | None
    typefully_base_url: str
    typefully_timeout: int
    x_auth_token: str | None
    x_csrf_token: str | None
    x_user_id: str | None
    data_dir: Path
    db_path: Path
    default_long_post: bool

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("TYPEFULLY_TWITTER_DATA_DIR", "data"))
        db_path = Path(os.getenv("TYPEFULLY_TWITTER_DB_PATH", str(data_dir / "twitter_analytics.db")))
        return cls(
            typefully_api_key=resolve_secret_reference(os.getenv("TYPEFULLY_API_KEY")),
            typefully_social_set_id=resolve_secret_reference(os.getenv("TYPEFULLY_SOCIAL_SET_ID")),
            typefully_authorization=resolve_secret_reference(os.getenv("TYPEFULLY_AUTHORIZATION")),
            typefully_account=resolve_secret_reference(os.getenv("TYPEFULLY_ACCOUNT")),
            typefully_session=resolve_secret_reference(os.getenv("TYPEFULLY_SESSION")),
            typefully_cookie=resolve_secret_reference(os.getenv("TYPEFULLY_COOKIE")),
            typefully_base_url=os.getenv("TYPEFULLY_BASE_URL", "https://typefully.com"),
            typefully_timeout=int(os.getenv("TYPEFULLY_TIMEOUT", "30")),
            x_auth_token=resolve_secret_reference(os.getenv("X_AUTH_TOKEN")),
            x_csrf_token=resolve_secret_reference(os.getenv("X_CSRF_TOKEN")),
            x_user_id=resolve_secret_reference(os.getenv("X_USER_ID")),
            data_dir=data_dir,
            db_path=db_path,
            default_long_post=env_bool("TYPEFULLY_TWITTER_DEFAULT_LONG_POST"),
        )

    def has_typefully_api(self) -> bool:
        return bool(self.typefully_api_key)

    def has_typefully_metrics(self) -> bool:
        return bool(self.typefully_authorization and self.typefully_account and self.typefully_session)

    def has_x_analytics(self) -> bool:
        return bool(self.x_auth_token and self.x_csrf_token)

    def available_workflows(self) -> list[str]:
        workflows = ["doctor.config", "post.count"]
        if self.has_typefully_api():
            workflows.extend(["post.draft", "post.create", "post.publish", "post.schedule", "post.list", "post.get", "post.delete"])
        if self.has_typefully_metrics():
            workflows.extend(["metrics.accounts", "metrics.metric", "metrics.snapshot"])
        if self.has_x_analytics():
            workflows.extend(["x.fetch", "x.summary", "x.hourly", "x.audience", "x.db-sync", "x.db-status"])
        else:
            workflows.extend(["x.summary", "x.db-status"])
        return sorted(set(workflows))

    def require_typefully_api(self) -> None:
        if not self.has_typefully_api():
            raise ConfigError("typefully_api", ["TYPEFULLY_API_KEY"], "Create a Typefully API key from Settings -> API and add it to .env.")

    def require_typefully_metrics(self) -> None:
        missing: list[str] = []
        if not self.typefully_authorization:
            missing.append("TYPEFULLY_AUTHORIZATION")
        if not self.typefully_account:
            missing.append("TYPEFULLY_ACCOUNT")
        if not self.typefully_session:
            missing.append("TYPEFULLY_SESSION")
        if missing:
            raise ConfigError("typefully_metrics", missing, "Configure optional Typefully web-session metrics credentials in .env.")

    def require_x_analytics(self) -> None:
        missing: list[str] = []
        if not self.x_auth_token:
            missing.append("X_AUTH_TOKEN")
        if not self.x_csrf_token:
            missing.append("X_CSRF_TOKEN")
        if missing:
            raise ConfigError("x_analytics", missing, "Configure X browser cookies in .env; see README: Get X Cookies for Advanced Analytics.")

    def doctor_payload(self) -> dict[str, Any]:
        return {
            "typefully_api": {
                "configured": self.has_typefully_api(),
                "api_key": _mask(self.typefully_api_key),
                "social_set_id": self.typefully_social_set_id,
            },
            "typefully_metrics": {
                "configured": self.has_typefully_metrics(),
                "authorization": _mask(self.typefully_authorization),
                "account": _mask(self.typefully_account),
                "session": _mask(self.typefully_session),
                "has_cookie": bool(self.typefully_cookie),
            },
            "x_analytics": {
                "configured": self.has_x_analytics(),
                "auth_token": _mask(self.x_auth_token),
                "csrf_token": _mask(self.x_csrf_token),
                "has_user_id": bool(self.x_user_id),
            },
            "data": {"data_dir": str(self.data_dir), "db_path": str(self.db_path)},
            "posting": {"default_long_post": self.default_long_post},
            "available_workflows": self.available_workflows(),
        }
