from __future__ import annotations

import json
from pathlib import Path

import pytest

from typefully_twitter_skill import cli
from typefully_twitter_skill.errors import ApiError, MediaProcessingError
from typefully_twitter_skill.typefully_media import (
    check_media,
    kind_from_mime,
    parse_ffprobe,
    safe_upload_name,
    validate_post_media_kinds,
)
from typefully_twitter_skill.typefully_post import TypefullyPostClient, build_x_posts, compact_draft_summary

from test_typefully_clients import base_settings

UPLOAD_URL = "https://uploads.example.com/bucket/clip.mp4?X-Amz-Signature=secret-signature"


class Resp:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else (json.dumps(payload) if payload is not None else "")

    def json(self):
        return self._payload


# ---------------------------------------------------------------- local checks

def test_safe_upload_name_replaces_disallowed_characters():
    assert safe_upload_name("/tmp/视频 片段 teaser v3.MP4") == "teaser_v3.mp4"
    assert safe_upload_name("/tmp/clip(1).mov") == "clip(1).mov"
    assert safe_upload_name("/tmp/中文.png") == "media.png"


def test_parse_ffprobe_extracts_limits_fields():
    info = parse_ffprobe({
        "format": {"duration": "90.0", "bit_rate": "1300000"},
        "streams": [
            {"codec_type": "audio", "codec_name": "aac"},
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "25/1"},
        ],
    })
    assert info == {"duration_s": 90.0, "bit_rate": 1300000.0, "width": 1920, "height": 1080, "fps": 25.0, "video_codec": "h264"}


def _video(tmp_path: Path, name: str = "clip.mp4") -> Path:
    path = tmp_path / name
    path.write_bytes(b"\x00" * 1024)
    return path


def test_check_media_accepts_short_1080p_clip(tmp_path):
    probe = {"duration_s": 97.3, "bit_rate": 1.3e6, "width": 1920, "height": 1080, "fps": 25.0, "video_codec": "h264"}
    check = check_media(_video(tmp_path), probe=probe)
    assert check.ok, check.errors
    assert check.kind == "video"


def test_check_media_rejects_video_longer_than_ten_minutes(tmp_path):
    probe = {"duration_s": 900.0, "bit_rate": 0.7e6, "width": 1920, "height": 1080, "fps": 25.0, "video_codec": "h264"}
    check = check_media(_video(tmp_path), probe=probe)
    assert not check.ok
    assert any("600 s" in e and "x.com" in e for e in check.errors)


@pytest.mark.parametrize(
    "probe, fragment",
    [
        ({"duration_s": 30, "fps": 120.0, "width": 1920, "height": 1080}, "fps"),
        ({"duration_s": 30, "bit_rate": 40e6, "width": 1920, "height": 1080}, "Mbps"),
        ({"duration_s": 30, "width": 3000, "height": 1000}, "Aspect"),
    ],
)
def test_check_media_rejects_other_video_limits(tmp_path, probe, fragment):
    check = check_media(_video(tmp_path), probe=probe)
    assert any(fragment in e for e in check.errors)


def test_check_media_rejects_unsupported_extension_and_missing_file(tmp_path):
    bad = tmp_path / "clip.webm"
    bad.write_bytes(b"x")
    assert "Unsupported extension" in check_media(bad).errors[0]
    assert "File not found" in check_media(tmp_path / "missing.mp4").errors[0]


def test_check_media_warns_when_ffprobe_is_missing(tmp_path):
    check = check_media(_video(tmp_path), probe=None)
    assert check.ok
    assert any("ffprobe not available" in w for w in check.warnings)


def test_post_media_mix_rules():
    assert validate_post_media_kinds(["video"]) == []
    assert validate_post_media_kinds(["image"] * 4) == []
    assert validate_post_media_kinds(["video", "video"])
    assert validate_post_media_kinds(["video", "image"])
    assert validate_post_media_kinds(["image"] * 5)
    assert kind_from_mime("video/mp4") == "video"
    assert kind_from_mime("image/gif") == "gif"


# ---------------------------------------------------------------- payloads

def test_build_x_posts_without_media_is_unchanged():
    assert build_x_posts(["a", "b"]) == [{"text": "a"}, {"text": "b"}]


def test_build_x_posts_attaches_media_and_ai_label_to_the_right_post():
    posts = build_x_posts(["main", "reply"], media={0: ["m1"]}, made_with_ai={0})
    assert posts == [{"text": "main", "media_ids": ["m1"], "made_with_ai": True}, {"text": "reply"}]


def test_build_x_posts_rejects_out_of_range_index():
    with pytest.raises(ValueError):
        build_x_posts(["only"], media={1: ["m1"]})


def test_compact_summary_lists_media_per_post():
    draft = {"id": 1, "platforms": {"x": {"posts": [
        {"text": "hook line\nmore", "media_ids": ["m1"], "made_with_ai": True},
        {"text": "reply", "media_ids": []},
    ]}}}
    summary = compact_draft_summary(draft)
    assert summary["posts"][0] == {"index": 1, "first_line": "hook line", "media_ids": ["m1"], "made_with_ai": True}
    assert summary["posts"][1]["media_ids"] == []


# ---------------------------------------------------------------- client flow

def test_upload_flow_puts_without_headers_and_waits_until_ready(monkeypatch, tmp_path):
    calls = []
    statuses = iter(["processing", "processing", "ready"])

    def fake_request(method, url, **kwargs):
        calls.append(("api", method, url, kwargs))
        if url.endswith("/media/upload"):
            return Resp(201, {"media_id": "m-1", "upload_url": UPLOAD_URL})
        return Resp(200, {"media_id": "m-1", "status": next(statuses), "mime": "video/mp4"})

    def fake_put(url, **kwargs):
        calls.append(("put", "PUT", url, kwargs))
        return Resp(200, text="")

    monkeypatch.setattr("requests.request", fake_request)
    monkeypatch.setattr("requests.put", fake_put)
    monkeypatch.setattr("time.sleep", lambda s: None)
    client = TypefullyPostClient(base_settings())
    info = client.upload_media(_video(tmp_path), file_name="clip.mp4", alt_text="alt")

    assert info["status"] == "ready" and info["media_id"] == "m-1"
    assert "upload_url" not in info
    create = calls[0]
    assert create[2].endswith("/social-sets/123/media/upload")
    assert create[3]["json"] == {"file_name": "clip.mp4", "alt_text": "alt"}
    put = calls[1]
    assert put[0] == "put" and put[2] == UPLOAD_URL
    assert "headers" not in put[3]
    assert sum(1 for c in calls if c[0] == "api" and c[1] == "GET") == 3


def test_wait_media_ready_raises_with_reason_on_failure(monkeypatch):
    monkeypatch.setattr("requests.request", lambda m, u, **k: Resp(200, {"status": "failed", "error_reason": "Unsupported file format"}))
    client = TypefullyPostClient(base_settings())
    with pytest.raises(MediaProcessingError) as exc:
        client.wait_media_ready("m-1", sleep=lambda s: None)
    assert exc.value.reason == "Unsupported file format"


def test_wait_media_ready_times_out(monkeypatch):
    monkeypatch.setattr("requests.request", lambda m, u, **k: Resp(200, {"status": "processing"}))
    ticks = iter([0, 5, 11])
    client = TypefullyPostClient(base_settings())
    with pytest.raises(MediaProcessingError) as exc:
        client.wait_media_ready("m-1", timeout=10, sleep=lambda s: None, clock=lambda: next(ticks))
    assert exc.value.status == "processing"


def test_failed_put_redacts_upload_url(monkeypatch, tmp_path):
    monkeypatch.setattr("requests.put", lambda url, **k: Resp(403, text=f"SignatureDoesNotMatch for {UPLOAD_URL}"))
    client = TypefullyPostClient(base_settings())
    with pytest.raises(ApiError) as exc:
        client.put_presigned(UPLOAD_URL, _video(tmp_path))
    assert "secret-signature" not in str(exc.value)
    assert "uploads.example.com" not in str(exc.value)


# ---------------------------------------------------------------- CLI

def _cli_env(monkeypatch):
    monkeypatch.setenv("TYPEFULLY_API_KEY", "tf_test")
    monkeypatch.setenv("TYPEFULLY_SOCIAL_SET_ID", "123")
    monkeypatch.setenv("TYPEFULLY_TWITTER_ENV_FILE", "/nonexistent/.env")


def test_cli_draft_with_media_checks_ready_and_builds_payload(monkeypatch, capsys):
    _cli_env(monkeypatch)
    sent = {}

    def fake_request(method, url, **kwargs):
        if method == "GET" and "/media/" in url:
            return Resp(200, {"media_id": "m-1", "status": "ready", "mime": "video/mp4"})
        if method == "POST" and url.endswith("/drafts"):
            sent["json"] = kwargs["json"]
            return Resp(201, {"id": 7, "status": "draft", "platforms": kwargs["json"]["platforms"]})
        raise AssertionError((method, url))

    monkeypatch.setattr("requests.request", fake_request)
    code = cli.main([
        "post", "draft", "--text", "main", "--media", "m-1", "--made-with-ai-post", "1", "--format", "json",
    ])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert sent["json"]["platforms"]["x"]["posts"] == [{"text": "main", "media_ids": ["m-1"], "made_with_ai": True}]
    assert out["posts"][0]["media_ids"] == ["m-1"]


def test_cli_refuses_media_that_is_not_ready(monkeypatch, capsys):
    _cli_env(monkeypatch)

    def fake_request(method, url, **kwargs):
        if method == "GET":
            return Resp(200, {"media_id": "m-1", "status": "processing", "mime": "video/mp4"})
        raise AssertionError("draft must not be created")

    monkeypatch.setattr("requests.request", fake_request)
    code = cli.main(["post", "draft", "--text", "main", "--media", "m-1", "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["error"] == "media_not_ready"


def test_cli_rejects_two_videos_on_one_post(monkeypatch, capsys):
    _cli_env(monkeypatch)

    def fake_request(method, url, **kwargs):
        if method == "GET":
            return Resp(200, {"status": "ready", "mime": "video/mp4"})
        raise AssertionError("draft must not be created")

    monkeypatch.setattr("requests.request", fake_request)
    code = cli.main(["post", "draft", "--text", "main", "--media", "a", "--media", "b", "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["error"] == "invalid_post_media"


def test_cli_post_media_index_out_of_range(monkeypatch):
    _cli_env(monkeypatch)
    with pytest.raises(SystemExit):
        cli.main(["post", "draft", "--text", "main", "--post-media", "2=m-1"])


def test_cli_media_file_fails_locally_before_any_request(monkeypatch, tmp_path, capsys):
    _cli_env(monkeypatch)
    monkeypatch.setattr("requests.request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    bad = tmp_path / "clip.webm"
    bad.write_bytes(b"x")
    code = cli.main(["post", "draft", "--text", "main", "--media-file", str(bad), "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["error"] == "media_check_failed"


def test_cli_media_check_is_local(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("requests.request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
    path = tmp_path / "pic.png"
    path.write_bytes(b"\x89PNG" + b"\x00" * 10)
    code = cli.main(["media", "check", str(path), "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["kind"] == "image"


def test_put_network_error_does_not_leak_url(monkeypatch, tmp_path):
    import requests

    def boom(url, **kwargs):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}")

    monkeypatch.setattr("requests.put", boom)
    client = TypefullyPostClient(base_settings())
    with pytest.raises(ApiError) as exc:
        client.put_presigned(UPLOAD_URL, _video(tmp_path))
    assert "secret-signature" not in str(exc.value)
    assert "ConnectionError" in str(exc.value)


def test_put_s3_error_keeps_only_code_and_message(monkeypatch, tmp_path):
    body = (
        "<Error><Code>SignatureDoesNotMatch</Code><Message>The request signature we calculated does not match"
        "</Message><AWSAccessKeyId>AKIAFAKEKEY</AWSAccessKeyId><StringToSign>AWS4 secret</StringToSign></Error>"
    )
    monkeypatch.setattr("requests.put", lambda url, **k: Resp(403, text=body))
    client = TypefullyPostClient(base_settings())
    with pytest.raises(ApiError) as exc:
        client.put_presigned(UPLOAD_URL, _video(tmp_path))
    assert "SignatureDoesNotMatch" in str(exc.value)
    assert "AKIAFAKEKEY" not in str(exc.value) and "StringToSign" not in str(exc.value)


def test_put_sends_file_handle_as_data(monkeypatch, tmp_path):
    seen = {}

    def fake_put(url, **kwargs):
        seen.update(kwargs)
        return Resp(204, text="")

    monkeypatch.setattr("requests.put", fake_put)
    TypefullyPostClient(base_settings()).put_presigned(UPLOAD_URL, _video(tmp_path))
    assert set(seen) == {"data", "timeout"}
    assert hasattr(seen["data"], "read")


def test_cli_null_mime_falls_back_to_file_name(monkeypatch, capsys):
    _cli_env(monkeypatch)

    def fake_request(method, url, **kwargs):
        if method == "GET":
            return Resp(200, {"status": "ready", "mime": None, "file_name": "clip.mp4"})
        raise AssertionError("draft must not be created")

    monkeypatch.setattr("requests.request", fake_request)
    code = cli.main(["post", "draft", "--text", "main", "--media", "a", "--media", "b", "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and out["error"] == "invalid_post_media"


def test_cli_media_file_uploads_and_attaches_after_existing_ids(monkeypatch, tmp_path, capsys):
    _cli_env(monkeypatch)
    sent = {}
    image = tmp_path / "pic.png"
    image.write_bytes(b"\x89PNG" + b"\x00" * 10)

    def fake_request(method, url, **kwargs):
        if url.endswith("/media/upload"):
            sent["upload"] = kwargs["json"]
            return Resp(201, {"media_id": "new", "upload_url": UPLOAD_URL})
        if method == "GET" and "/media/" in url:
            return Resp(200, {"status": "ready", "mime": "image/png"})
        if method == "POST" and url.endswith("/drafts"):
            sent["draft"] = kwargs["json"]
            return Resp(201, {"id": 9, "platforms": kwargs["json"]["platforms"]})
        raise AssertionError((method, url))

    monkeypatch.setattr("requests.request", fake_request)
    monkeypatch.setattr("requests.put", lambda url, **k: Resp(200, text=""))
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("main\n---\nreply"))
    code = cli.main([
        "post", "draft", "--thread-stdin", "--post-media", "2=old", "--post-media-file", f"2={image}",
        "--alt-text", "a chart", "--made-with-ai", "--format", "json",
    ])
    assert code == 0, capsys.readouterr().out
    assert sent["upload"] == {"file_name": "pic.png", "alt_text": "a chart"}
    posts = sent["draft"]["platforms"]["x"]["posts"]
    assert posts[0] == {"text": "main", "made_with_ai": True}
    assert posts[1] == {"text": "reply", "media_ids": ["old", "new"], "made_with_ai": True}


def test_cli_mix_violation_stops_before_upload(monkeypatch, tmp_path, capsys):
    _cli_env(monkeypatch)
    image = tmp_path / "pic.png"
    image.write_bytes(b"\x89PNG" + b"\x00" * 10)

    def fake_request(method, url, **kwargs):
        if method == "GET":
            return Resp(200, {"status": "ready", "mime": "video/mp4"})
        raise AssertionError("no upload or draft expected")

    monkeypatch.setattr("requests.request", fake_request)
    code = cli.main(["post", "draft", "--text", "main", "--media", "vid", "--media-file", str(image), "--format", "json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and out["error"] == "invalid_post_media"


def test_cli_check_urls_rejects_bad_expected_counts(monkeypatch):
    with pytest.raises(SystemExit):
        cli.main(["post", "check-urls", "--text", "a https://example.com", "--post-expected-urls", "2=1"])
    with pytest.raises(SystemExit):
        cli.main(["post", "check-urls", "--text", "a https://example.com", "--expected-urls", "-1"])
