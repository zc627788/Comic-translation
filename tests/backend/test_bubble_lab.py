"""Safety and geometry regression tests; fixtures/mocks are not model-quality evidence."""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from services.api import lab
from services.worker.bubble_pipeline import BubblePipeline
from services.worker.bubble_render import fit_text, prepare_region, render_region
from services.worker.bubble_vision import deduplicate, tile_ranges
from services.worker.translation import MyMemoryTranslator, TranslationError, query_provider

FONT = Path("C:/Windows/Fonts/msyh.ttc")


def test_long_tiles_cover_bottom_and_overlap_without_duplicate_regions():
    ranges = tile_ranges(800, 2900)
    assert ranges[0][0] == 0 and ranges[-1][1] == 2900
    assert all(a[1] > b[0] for a, b in zip(ranges, ranges[1:], strict=False))
    rows = [{"class": 0, "score": .9, "box": [5, 900, 90, 1100]},
            {"class": 0, "score": .8, "box": [6, 899, 90, 1101]},
            {"class": 1, "score": .8, "box": [6, 910, 70, 1090]}]
    assert len(deduplicate(rows)) == 2


def white_fixture():
    image = Image.new("RGB", (300, 230), "#345865")
    draw = ImageDraw.Draw(image)
    draw.ellipse((30, 20, 270, 210), fill="white", outline="black", width=4)
    for x in range(102, 190, 20):
        draw.rectangle((x, 84, x + 8, 139), fill="black")
    return image, {"box": [98, 79, 200, 145], "bubble": [28, 18, 272, 212]}


@pytest.mark.skipif(not FONT.is_file(), reason="Windows preview font is local, not redistributed")
def test_erasure_and_typesetting_preserve_every_pixel_outside_safe_area():
    image, region = white_fixture()
    prep = prepare_region(image, region)
    result, record = render_region(image, prep, "测试中文！", FONT)
    left, top, right, bottom = prep["bounds"]
    mask = np.zeros((image.height, image.width), np.uint8)
    mask[top:bottom, left:right] = prep["safe"]
    changed = np.any(np.asarray(result) != np.asarray(image), axis=2)
    assert changed.any() and not (changed & (mask == 0)).any()
    assert record["outside_safe_modified_pixels"] == 0
    # Original object is retained for one-click restoration.
    assert np.asarray(image)[100, 103].tolist() == [0, 0, 0]


@pytest.mark.skipif(not FONT.is_file(), reason="Windows preview font unavailable")
def test_overflow_fails_before_erasure_and_wrapping_keeps_punctuation():
    image, region = white_fixture()
    original = image.tobytes()
    prep = prepare_region(image, region)
    with pytest.raises(ValueError, match="TEXT_DOES_NOT_FIT"):
        render_region(image, prep, "字" * 2000, FONT)
    assert image.tobytes() == original
    _, lines, _ = fit_text("我们马上就到了！", (0, 0, 110, 200), FONT)
    assert "".join(lines) == "我们马上就到了！"
    assert not any(line.startswith("！") for line in lines)


def test_dark_complex_bubble_is_preserved():
    image = Image.new("RGB", (200, 200), "#222222")
    with pytest.raises(ValueError, match="DARK_OR_COMPLEX_BUBBLE"):
        prepare_region(image, {"box": [50, 50, 150, 150], "bubble": [20, 20, 180, 180]})


def test_open_white_background_without_bubble_margin_is_preserved():
    image = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(image).rectangle((80, 80, 90, 110), fill="black")
    with pytest.raises(ValueError, match="OPEN_BUBBLE_BOUNDARY"):
        prepare_region(image, {"box": [50, 50, 150, 150], "bubble": [48, 48, 152, 152]})


def test_korean_provider_receives_explicit_language_and_preserves_word_spaces(monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, _):
            return b'{"responseStatus":200,"responseData":{"translatedText":"test"}}'

    class Opener:
        def open(self, request, timeout):
            requests.append(parse_qs(urlparse(request.full_url).query))
            return Response()

    monkeypatch.setattr("services.worker.translation.build_opener", lambda _: Opener())
    query_provider("공원에서 만나요.", "ko")
    assert requests == [{"q": ["공원에서 만나요."], "langpair": ["ko|zh-CN"]}]
    with pytest.raises(TranslationError, match="UNSUPPORTED_LANGUAGE"):
        MyMemoryTranslator(source_language="xx")


def test_translation_cache_separates_languages_and_budget_survives_failures(tmp_path, monkeypatch):
    # No detector or provider is loaded; this is a cache/limit contract test only.
    client = BubblePipeline.__new__(BubblePipeline)
    client.allow_network = True
    client.cache_file = tmp_path / "cache.json"
    client.cache = {"entries": {}, "attempted_characters": 0}
    calls = []

    class FakeProvider:
        def __init__(self, source_language):
            self.language = source_language

        def translate(self, text):
            calls.append(self.language)
            return MyMemoryTranslator(transport=lambda _: {
                "responseStatus": 200, "responseData": {"translatedText": "测试"},
            }).translate(text)

    monkeypatch.setattr("services.worker.bubble_pipeline.MyMemoryTranslator", FakeProvider)
    assert client.translate("same", "ja")[1] is False
    assert client.translate("same", "ja")[1] is True
    assert client.translate("same", "ko")[1] is False
    assert calls == ["ja", "ko"] and client.cache["attempted_characters"] == 8
    client.cache["attempted_characters"] = 1000
    with pytest.raises(TranslationError, match="LOCAL_BUDGET_EXCEEDED"):
        client.translate("new", "ko")
    assert len(calls) == 2


HEADERS = {"Origin": "http://127.0.0.1:4176", "X-Comic-Lab": "1"}


def test_lab_rejects_cross_origin_paths_unknown_options_and_unavailable_results():
    with TestClient(lab.app) as client:
        assert client.post("/api/jobs", json={}).status_code == 403
        assert client.post("/api/jobs", headers={**HEADERS, "Origin": "https://evil.example"},
                           json={}).status_code == 403
        assert client.post("/api/jobs", headers=HEADERS, json={
            "sample_id": "x", "allow_translation": True, "path": "C:/private",
        }).status_code == 422
        assert client.post("/api/jobs", headers=HEADERS, json={
            "sample_id": "x", "allow_translation": False,
        }).status_code == 400
        assert client.get("/results/not-a-job/translated.png").status_code == 404
        assert client.get("/assets/.env").status_code == 404
        assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
        assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]


def test_lab_busy_prevents_duplicate_dispatch(monkeypatch, tmp_path):
    monkeypatch.setattr(lab, "SAMPLES", {"test": {"path": tmp_path}})
    monkeypatch.setattr(lab, "jobs", {"active": {"state": "running"}})
    file = tmp_path / "test.png"
    file.write_bytes(b"fixture")
    lab.SAMPLES["test"]["path"] = file
    with TestClient(lab.app) as client:
        response = client.post("/api/jobs", headers=HEADERS, json={
            "sample_id": "test", "allow_translation": True,
        })
        assert response.status_code == 409
        assert response.json()["detail"] == "PROCESSING_IN_PROGRESS"
