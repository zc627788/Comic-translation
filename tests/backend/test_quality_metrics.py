"""Independent metric contracts: failures must not inflate measured quality."""

import hashlib
import json

import pytest

from services.worker.bubble_pipeline import BubblePipeline
from services.worker.quality_metrics import distance, normalize, score_regions
from services.worker.translation import TranslationError


def gold(text, box=None):
    return {"text": text, "box": box or [0, 0, 100, 100], "legible": True, "role": "dialogue"}


def test_unknown_truth_is_not_a_perfect_score():
    assert score_regions(None, [{"box": [0, 0, 2, 2], "text": "a"}]) is None
    empty = score_regions([], [{"box": [0, 0, 2, 2], "text": "a"}])
    assert empty["detection_recall"] is None
    assert empty["end_to_end_cer"] is None
    assert empty["unmatched_predictions"] == 1


def test_missing_regions_count_as_deletions_not_zero_errors():
    result = score_regions([gold("가 나")], [])
    assert result["missed_regions"] == 1
    assert result["edit_errors"] == 3 and result["end_to_end_cer"] == 1
    assert result["conditional_cer"] is None


def test_one_box_cannot_match_two_dialogues():
    result = score_regions([gold("甲"), gold("乙", [110, 0, 200, 100])],
                           [{"box": [0, 0, 210, 100], "text": "甲乙"}])
    assert result["matched_regions"] == 1 and result["missed_regions"] == 1


def test_normalization_preserves_korean_word_spaces_and_scores_them():
    assert normalize("Ａ\n 가   나 ") == "A 가 나"
    result = score_regions([gold("가 나")], [{"box": [0, 0, 100, 100], "text": "가나"}])
    assert result["edit_errors"] == 1
    assert result["end_to_end_cer_without_spaces"] == 0
    assert distance("abc", "axc") == 1


def test_coverage_threshold_does_not_accept_a_small_partial_detection():
    result = score_regions([gold("가나다")], [{"box": [0, 0, 50, 100], "text": "가"}])
    assert result["matched_regions"] == 0
    assert result["end_to_end_cer"] == 1


def test_cache_only_never_calls_provider_or_changes_budget(tmp_path, monkeypatch):
    client = BubblePipeline.__new__(BubblePipeline)
    client.allow_network = False
    client.cache_file = tmp_path / "cache.json"
    client.cache = {"entries": {}, "attempted_characters": 264}
    client.cache_file.write_text(json.dumps(client.cache), encoding="utf-8")
    before = client.cache_file.read_bytes()

    def forbidden(*args, **kwargs):
        pytest.fail("Offline benchmark must never instantiate the provider")

    monkeypatch.setattr("services.worker.bubble_pipeline.MyMemoryTranslator", forbidden)
    with pytest.raises(TranslationError, match="NETWORK_NOT_AUTHORIZED"):
        client.translate("기다려 주세요", "ko")
    assert client.cache["attempted_characters"] == 264
    assert client.cache_file.read_bytes() == before
    key = hashlib.sha256("mymemory-v1:ko:zh-CN:기다려 주세요".encode()).hexdigest()
    client.cache["entries"][key] = {"text": "test-only cached payload"}
    assert client.translate("기다려 주세요", "ko")[1] is True
