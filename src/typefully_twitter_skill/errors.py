"""Typed exceptions for the Typefully Twitter skill."""

from __future__ import annotations


class TypefullyTwitterError(Exception):
    """Base error for expected CLI failures."""


class ConfigError(TypefullyTwitterError):
    """Raised when a command is missing its required credential family."""

    def __init__(self, capability: str, missing_env: list[str], setup_hint: str) -> None:
        self.capability = capability
        self.missing_env = missing_env
        self.setup_hint = setup_hint
        super().__init__(f"{capability} is not configured: missing {', '.join(missing_env)}")

    def to_payload(self, available_workflows: list[str]) -> dict[str, object]:
        return {
            "error": f"{self.capability}_not_configured",
            "capability": self.capability,
            "missing_env": self.missing_env,
            "available_workflows": available_workflows,
            "setup_hint": self.setup_hint,
        }


class ApiError(TypefullyTwitterError):
    """HTTP error with response body preserved for agent debugging."""

    def __init__(self, service: str, status_code: int, body: str) -> None:
        self.service = service
        self.status_code = status_code
        self.body = body
        super().__init__(f"{service} HTTP {status_code}: {body}")

    def to_payload(self) -> dict[str, object]:
        return {"error": "http_error", "service": self.service, "status_code": self.status_code, "body": self.body}


class MediaProcessingError(TypefullyTwitterError):
    """Raised when uploaded media fails processing or does not become ready in time."""

    def __init__(self, media_id: str, status: str, reason: str | None) -> None:
        self.media_id = media_id
        self.status = status
        self.reason = reason
        super().__init__(f"media {media_id} is {status}: {reason}")

    def to_payload(self) -> dict[str, object]:
        return {"error": "media_not_ready", "media_id": self.media_id, "status": self.status, "reason": self.reason}
