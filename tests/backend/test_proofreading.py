"""Safety contracts only; fixtures/provider fakes are not language-quality evidence."""

import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from services.api import proofread
from services.worker.bubble_pipeline import FONT, BubblePipeline
from services.worker.private_store import exclusive, write_json
from services.worker.proofreading import Proofreader, context_payload, digest, parse_context
from services.worker.translation import MyMemoryTranslator, TranslationError

SAMPLE = "fx-ko-plain"
HEADERS = {"Origin": "http://127.0.0.1:4182", "X-Comic-Lab": "1"}


@pytest.fixture
def reader(tmp_path):
    base = tmp_path / "base" / SAMPLE
    base.mkdir(parents=True)
    image = Image.new("RGB", (300, 230), "#345865")
    draw = ImageDraw.Draw(image)
    draw.ellipse((30, 20, 270, 210), fill="white", outline="black", width=4)
    for x in range(102, 190, 20):
        draw.rectangle((x, 84, x + 8, 139), fill="black")
    image.save(base / "original.png")
    write_json(base / "result.json", {
        "language": "ko", "size": [300, 230], "regions": [
            {"id": 0, "box": [98, 79, 200, 145], "bubble": [28, 18, 272, 212],
             "status": "covered", "source": "안녕", "translation": "你好"},
            {"id": 1, "box": [0, 0, 10, 10], "bubble": [0, 0, 20, 20],
             "status": "preserved", "reason": "DARK_OR_COMPLEX_BUBBLE"},
        ],
    })
    return Proofreader(base.parent, tmp_path / "output", tmp_path / "diag",
                       tmp_path / "cache.json")


@pytest.mark.skipif(not FONT.is_file(), reason="Local Windows font unavailable")
def test_revisions_overflow_restart_restore_and_source_immutability(reader):
    original = digest(reader.baseline / SAMPLE / "original.png")
    first = reader.revise(SAMPLE, 0, {"0": {"translation": "我们走吧！"}})
    assert first["revision"] == 1 and first["outside_safe_modified_pixels"] == 0
    current = digest(reader.image_path(SAMPLE))
    pointer = (reader.output / SAMPLE / "current.json").read_bytes()
    with pytest.raises(ValueError, match="TEXT_DOES_NOT_FIT"):
        reader.revise(SAMPLE, 1, {"0": {"translation": "字" * 500}})
    assert (reader.output / SAMPLE / "current.json").read_bytes() == pointer
    assert digest(reader.image_path(SAMPLE)) == current
    restarted = Proofreader(reader.baseline, reader.output, reader.diagnostic)
    assert restarted.state(SAMPLE)["regions"][0]["translation"] == "我们走吧！"
    with pytest.raises(ValueError, match="REVISION_CONFLICT"):
        reader.revise(SAMPLE, 0, {"0": {"translation": "旧页"}})
    restored = restarted.revise(SAMPLE, 1, {}, restore=True)
    assert restored["regions"][0]["translation"] == "你好"
    assert restored["regions"][0]["edited"] is False
    assert digest(reader.baseline / SAMPLE / "original.png") == original


def test_unsafe_unknown_and_corrupt_baseline_rejected(reader):
    with pytest.raises(ValueError, match="UNSAFE_REGION"):
        reader.revise(SAMPLE, 0, {"1": {"translation": "覆盖"}})
    with pytest.raises(ValueError, match="INVALID_EDIT"):
        reader.revise(SAMPLE, 0, {"33": {"translation": "未知"}})
    with pytest.raises(ValueError, match="INVALID_TEXT"):
        reader.revise(SAMPLE, 0, {"0": {"translation": "  "}})
    with pytest.raises(ValueError, match="UNKNOWN_SAMPLE"):
        reader.state("../../outside")


@pytest.mark.parametrize("text", [
    "[[0]]你好", "[[1]]你好 [[0]]再见", "[[0]]你好 [[0]]再见", "序言 [[0]]你好 [[1]]再见",
    "[[00]]你好 [[1]]再见", "[[0]]你好 [[1]]안녕", "[[0]]你好 [[1]]", "[[0]]你好 [[1]]再见 [[x]]",
])
def test_context_mapping_fails_closed(text):
    with pytest.raises(ValueError):
        parse_context(text, [0, 1])


def test_context_order_limits_and_valid_mapping():
    text, ids = context_payload([{"id": 4, "source": "안녕"}, {"id": 7, "source": "가자"}])
    assert ids == [4, 7] and text.startswith("[[4]]")
    assert parse_context("[[4]]你好\n[[7]]走吧", ids) == {"4": "你好", "7": "走吧"}
    with pytest.raises(ValueError, match="CONTEXT_TOO_LONG"):
        context_payload([{"id": 0, "source": "가" * 200}, {"id": 1, "source": "나"}])


def test_cross_process_budget_reload_failure_and_lock(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    write_json(cache, {"entries": {}, "attempted_characters": 399})
    client = BubblePipeline.__new__(BubblePipeline)
    client.cache_file, client.allow_network = cache, True
    client.cache = {"entries": {}, "attempted_characters": 0}  # Deliberately stale.

    class Failing:
        def __init__(self, **kwargs):
            pass

        def translate(self, text):
            raise TranslationError("NETWORK_ERROR")

    monkeypatch.setattr("services.worker.bubble_pipeline.MyMemoryTranslator", Failing)
    with pytest.raises(TranslationError, match="NETWORK_ERROR"):
        client.translate("가나", "ko")
    assert json.loads(cache.read_text(encoding="utf-8"))["attempted_characters"] == 401
    with exclusive(cache.with_suffix(".lock")), pytest.raises(ValueError, match="RESOURCE_BUSY"):
        client.translate("가나", "ko")


def test_api_protects_edits_body_and_private_files(reader, monkeypatch):
    monkeypatch.setattr(proofread, "reader", reader)
    with TestClient(proofread.app) as client:
        assert client.post(f"/api/pages/{SAMPLE}/revision", json={}).status_code == 403
        assert client.post(f"/api/pages/{SAMPLE}/revision", headers=HEADERS, json={
            "revision": 0, "path": "C:/private",
        }).status_code == 422
        assert client.post(f"/api/pages/{SAMPLE}/revision", headers=HEADERS, json={
            "revision": 0, "edits": {"1": {"translation": "覆盖"}},
        }).json()["detail"] == "UNSAFE_REGION"
        assert client.post(f"/api/pages/{SAMPLE}/revision", headers=HEADERS,
                           json={"padding": "x" * 17000}).status_code == 413
        page = client.get(f"/api/pages/{SAMPLE}").json()
        assert "baseline_hash" not in page and "image" not in page
        assert client.get("/assets/cache.json").status_code == 404
        assert client.get("/", headers={"Host": "evil.example"}).status_code == 400


def test_context_is_only_candidate_and_repeated_request_uses_cache(reader, monkeypatch):
    # Fake provider validates plumbing only, never counted as real API evidence.
    original = reader.baseline / SAMPLE / "result.json"
    data = json.loads(original.read_text(encoding="utf-8"))
    data["regions"][1]["source"] = "가자"
    write_json(original, data)
    calls = []

    class Provider:
        def __init__(self, **kwargs):
            pass

        def translate(self, text):
            calls.append(text)
            return MyMemoryTranslator(transport=lambda _: {
                "responseStatus": 200,
                "responseData": {"translatedText": "[[0]]你好 [[1]]走吧"},
            }).translate(text)

    monkeypatch.setattr("services.worker.bubble_pipeline.MyMemoryTranslator", Provider)
    result = reader.context(SAMPLE, 0)
    assert result["candidates"] == {"0": "你好", "1": "走吧"}
    assert reader.state(SAMPLE)["revision"] == 0
    assert reader.context(SAMPLE, 0)["cached"] is True and len(calls) == 1
