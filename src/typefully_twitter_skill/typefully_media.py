"""Local media checks for Typefully uploads to X.

Limits mirror Typefully's published X media rules
(https://support.typefully.com/en/articles/8717768-supported-media-formats)
and the upload filename pattern in the Typefully v2 OpenAPI spec
(https://api.typefully.com/v2/openapi.json). Everything here is local: no
function in this module talks to the network.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Typefully upload filename rule (OpenAPI MediaUploadRequest.file_name).
FILE_NAME_RE = re.compile(r"^[a-zA-Z0-9_.()\-]+\.(jpg|jpeg|png|webp|gif|mp4|mov|pdf)$", re.IGNORECASE)
MAX_FILE_NAME_LENGTH = 255

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov"})
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
GIF_EXTENSIONS = frozenset({".gif"})
PDF_EXTENSIONS = frozenset({".pdf"})
ALLOWED_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | GIF_EXTENSIONS | PDF_EXTENSIONS

MIB = 1024 * 1024
# X video through Typefully: MP4/MOV, <= 512 MB, <= 10 minutes, <= 60 fps,
# <= 30 Mbps, aspect ratio between 1:2.39 and 2.39:1.
X_VIDEO_MAX_BYTES = 512 * MIB
X_VIDEO_MAX_SECONDS = 600.0
X_VIDEO_MAX_FPS = 60.0
X_VIDEO_MAX_BITRATE = 30_000_000
X_VIDEO_MIN_ASPECT = 1 / 2.39
X_VIDEO_MAX_ASPECT = 2.39
X_GIF_MAX_BYTES = 15 * MIB
DEFAULT_IMAGE_MAX_MB = 5  # free plan; paid plans allow 20 MB

X_MAX_IMAGES_PER_POST = 4


@dataclass
class MediaCheck:
    path: str
    upload_name: str
    kind: str
    size_bytes: int
    probe: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "upload_name": self.upload_name,
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "probe": self.probe,
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def media_kind(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in GIF_EXTENSIONS:
        return "gif"
    if ext in PDF_EXTENSIONS:
        return "pdf"
    return "unsupported"


def kind_from_mime(mime: str | None) -> str:
    if not mime:
        return "unknown"
    if mime == "image/gif":
        return "gif"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("image/"):
        return "image"
    if mime == "application/pdf":
        return "pdf"
    return "unknown"


def safe_upload_name(path: str | Path) -> str:
    """Return a filename that satisfies Typefully's upload pattern."""
    p = Path(path)
    ext = p.suffix.lower()
    stem = re.sub(r"[^a-zA-Z0-9_.()\-]+", "_", p.stem).strip("_.") or "media"
    max_stem = MAX_FILE_NAME_LENGTH - len(ext)
    return f"{stem[:max_stem]}{ext}"


def _parse_rate(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            return float(num) / float(den) if float(den) else None
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_ffprobe(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce ffprobe JSON to the fields the X limits care about."""
    fmt = payload.get("format") or {}
    video = next((s for s in payload.get("streams", []) if s.get("codec_type") == "video"), None) or {}
    def _num(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return {
        "duration_s": _num(fmt.get("duration")),
        "bit_rate": _num(fmt.get("bit_rate")),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": _parse_rate(video.get("avg_frame_rate")) or _parse_rate(video.get("r_frame_rate")),
        "video_codec": video.get("codec_name"),
    }


def probe_media(path: str | Path) -> dict[str, Any] | None:
    """Run ffprobe if it is installed; return None when unavailable."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    result = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip()[:300]}
    return parse_ffprobe(json.loads(result.stdout or "{}"))


def _image_max_bytes() -> int:
    raw = os.getenv("TYPEFULLY_MEDIA_IMAGE_MAX_MB")
    try:
        return int(float(raw) * MIB) if raw else DEFAULT_IMAGE_MAX_MB * MIB
    except ValueError:
        return DEFAULT_IMAGE_MAX_MB * MIB


def check_media(path: str | Path, *, probe: dict[str, Any] | None | bool = True) -> MediaCheck:
    """Validate a local file against Typefully's X media limits.

    ``probe=True`` runs ffprobe when available; pass a dict to inject probe
    results (used by tests) or ``False``/``None`` to skip probing.
    """
    p = Path(path)
    kind = media_kind(p)
    upload_name = safe_upload_name(p)
    size = p.stat().st_size if p.exists() else 0
    check = MediaCheck(path=str(p), upload_name=upload_name, kind=kind, size_bytes=size)

    if not p.is_file():
        check.errors.append(f"File not found: {p}")
        return check
    if kind == "unsupported":
        check.errors.append(f"Unsupported extension {p.suffix!r}; allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
        return check
    if not FILE_NAME_RE.match(upload_name):
        check.errors.append(f"Could not derive a valid upload filename from {p.name!r}")
    if size == 0:
        check.errors.append("File is empty")

    if kind == "video" and size > X_VIDEO_MAX_BYTES:
        check.errors.append(f"Video is {size / MIB:.1f} MB; Typefully's X limit is 512 MB")
    if kind == "gif" and size > X_GIF_MAX_BYTES:
        check.errors.append(f"GIF is {size / MIB:.1f} MB; X limit is 15 MB")
    if kind == "image" and size > _image_max_bytes():
        check.errors.append(
            f"Image is {size / MIB:.1f} MB; limit is {_image_max_bytes() / MIB:.0f} MB "
            "(set TYPEFULLY_MEDIA_IMAGE_MAX_MB=20 on paid Typefully plans)"
        )
    if kind == "pdf":
        check.warnings.append("PDF attachments are not supported on X; use them only for other platforms")

    if kind != "video":
        return check

    if probe is True:
        info = probe_media(p)
    elif isinstance(probe, dict):
        info = probe
    else:
        info = None
    check.probe = info
    if info is None:
        check.warnings.append("ffprobe not available; duration, fps, bitrate, and aspect ratio were not checked")
        return check
    if "error" in info:
        check.errors.append(f"ffprobe failed: {info['error']}")
        return check

    duration = info.get("duration_s")
    if duration is not None and duration > X_VIDEO_MAX_SECONDS:
        check.errors.append(
            f"Video is {duration:.1f} s; Typefully's X limit is {X_VIDEO_MAX_SECONDS:.0f} s (10 minutes). "
            "Longer videos must be uploaded natively on x.com, or cut a shorter clip."
        )
    fps = info.get("fps")
    if fps is not None and fps > X_VIDEO_MAX_FPS + 0.01:
        check.errors.append(f"Frame rate {fps:.2f} fps exceeds {X_VIDEO_MAX_FPS:.0f} fps")
    bit_rate = info.get("bit_rate")
    if bit_rate is not None and bit_rate > X_VIDEO_MAX_BITRATE:
        check.errors.append(f"Bitrate {bit_rate / 1e6:.1f} Mbps exceeds 30 Mbps")
    width, height = info.get("width"), info.get("height")
    if width and height:
        aspect = width / height
        if not (X_VIDEO_MIN_ASPECT - 1e-3 <= aspect <= X_VIDEO_MAX_ASPECT + 1e-3):
            check.errors.append(f"Aspect ratio {width}x{height} is outside 1:2.39 to 2.39:1")
    codec = info.get("video_codec")
    if codec and codec != "h264":
        check.warnings.append(f"Video codec is {codec}; H.264 is recommended")
    return check


def validate_post_media_kinds(kinds: list[str]) -> list[str]:
    """Return errors if one X post's media mix breaks X's attachment rules."""
    errors: list[str] = []
    videos = kinds.count("video")
    gifs = kinds.count("gif")
    images = kinds.count("image")
    if videos + gifs > 1:
        errors.append("An X post can carry at most one video or GIF")
    if (videos or gifs) and images:
        errors.append("An X post cannot mix a video or GIF with images")
    if images > X_MAX_IMAGES_PER_POST:
        errors.append(f"An X post can carry at most {X_MAX_IMAGES_PER_POST} images")
    if "pdf" in kinds:
        errors.append("PDF attachments are not supported on X posts")
    return errors
