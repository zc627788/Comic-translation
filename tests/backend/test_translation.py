"""Fault-injection contract tests, not translation-quality evidence."""

from importlib import import_module

import pytest

from services.worker.translation import MyMemoryTranslator, TranslationError


def ok(text):
    return {"responseStatus": 200, "responseData": {"translatedText": text}}


def test_multibyte_limit_and_budget_do_not_make_extra_calls():
    seen = []

    def transport(text):
        seen.append(text)
        return ok("测试输出")

    client = MyMemoryTranslator(character_budget=2, transport=transport)
    with pytest.raises(TranslationError, match="TEXT_TOO_LONG"):
        client.translate("あ" * 151)
    client.translate("はい")
    with pytest.raises(TranslationError, match="LOCAL_BUDGET_EXCEEDED"):
        client.translate("はい")
    assert seen == ["はい"]


@pytest.mark.parametrize("body,code", [
    ({"responseStatus": 200, "quotaFinished": True}, "QUOTA_EXCEEDED"),
    ({"responseStatus": "429"}, "QUOTA_EXCEEDED"),
    ({"responseStatus": 403}, "PROVIDER_REJECTED"),
    ({"responseStatus": 200, "responseData": {}}, "INVALID_RESPONSE"),
    ([], "INVALID_RESPONSE"),
])
def test_provider_failures_are_not_reported_as_success(body, code):
    client = MyMemoryTranslator(transport=lambda _: body)
    with pytest.raises(TranslationError, match=code):
        client.translate("はい")
    assert client.attempted_characters == 2


def test_untranslated_response_has_quality_warnings():
    result = MyMemoryTranslator(transport=lambda text: ok(text)).translate("はい")
    assert {"UNCHANGED_TEXT", "JAPANESE_REMAINS"} <= set(result.warnings)


def test_escaped_text_is_returned_as_text_not_html():
    result = MyMemoryTranslator(transport=lambda _: ok("&lt;译文&gt;")).translate("はい")
    assert result.text == "<译文>"


def test_non_chinese_result_is_flagged():
    result = MyMemoryTranslator(transport=lambda _: ok("Hello")).translate("はい")
    assert "NO_CHINESE_CHARACTERS" in result.warnings


def test_chunking_preserves_unicode_without_exceeding_byte_limit():
    probe = import_module("scripts.probe-free-translation")
    source = "日本語。" * 200
    parts = probe.segments(source)
    assert "".join(parts) == source
    assert all(len(part.encode("utf-8")) <= 450 for part in parts)


def test_report_escapes_provider_markup():
    probe = import_module("scripts.probe-free-translation")
    result = {
        "created_at": "test-only", "network_requests": 0, "attempted_characters": 0,
        "samples": [{
            "image": "test.png", "ocr_ms": 0, "mode": "auto", "raw_ocr": "<script>",
            "translations": [{"source": "<script>", "result": {"text": "<script>"}}],
        }],
    }
    rendered = probe.render_report(result)
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
