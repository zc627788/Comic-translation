import pytest
from PIL import Image

from services.worker import bubble_pipeline, korean_paddle
from services.worker.bubble_pipeline import BubblePipeline


def test_default_and_explicit_selection_do_not_eagerly_load_candidate(monkeypatch, tmp_path):
    monkeypatch.setattr(bubble_pipeline, 'BubbleDetector', lambda: object())
    for option in ({}, {'korean_ocr': 'paddle-v5'}):
        pipeline = BubblePipeline(cache_file=tmp_path / 'empty.json', **option)
        assert pipeline.korean_ocr == option.get('korean_ocr', 'tesseract')
        assert pipeline.korean_model is None
        assert pipeline.allow_network is False
    with pytest.raises(ValueError, match='INVALID_KOREAN_OCR'):
        BubblePipeline(korean_ocr='unknown')


def test_candidate_is_reused_and_weakest_line_controls_confidence(monkeypatch, tmp_path):
    monkeypatch.setattr(bubble_pipeline, 'BubbleDetector', lambda: object())
    created = []

    class Candidate:
        def __init__(self):
            created.append(self)

        def read(self, image):
            assert image.size == (30, 40)
            return {'text': '가 나', 'lines': [
                {'text': '가', 'confidence': .95}, {'text': '나', 'confidence': .6}],
                'status': 'recognized'}

    monkeypatch.setattr(korean_paddle, 'KoreanPaddleOcr', Candidate)
    pipeline = BubblePipeline(korean_ocr='paddle-v5', cache_file=tmp_path / 'empty.json')
    for _ in range(2):
        output = pipeline.read_paddle(Image.new('RGB', (30, 40)))
        assert output['confidence'] == 60 and output['reason'] is None
    assert len(created) == 1


def test_empty_candidate_line_is_not_hidden_by_other_successful_lines(monkeypatch, tmp_path):
    monkeypatch.setattr(bubble_pipeline, 'BubbleDetector', lambda: object())
    pipeline = BubblePipeline(korean_ocr='paddle-v5', cache_file=tmp_path / 'empty.json')

    class Candidate:
        def read(self, image):
            return {'text': '가', 'lines': [
                {'text': '가', 'confidence': .99}, {'text': '', 'confidence': 0}],
                'status': 'recognized'}

    pipeline.korean_model = Candidate()
    assert pipeline.read_paddle(Image.new('RGB', (30, 40)))['reason'] == 'OCR_LINE_UNREADABLE'
