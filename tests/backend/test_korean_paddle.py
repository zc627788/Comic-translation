import json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from services.worker import korean_paddle
from services.worker.korean_paddle import decode_ctc, line_boxes, prepare_line


def test_ctc_blank_separates_repeated_letters_and_checks_dictionary():
    output = np.eye(3)[[1, 1, 0, 1, 2, 2]]
    assert decode_ctc(output, ['', '가', '나']) == ('가가나', 1.0)
    assert decode_ctc(np.eye(3)[[0, 0]], ['', '가', '나']) == ('', 0.0)
    with pytest.raises(ValueError, match='CTC_DICTIONARY'):
        decode_ctc(output, ['', '가'])


def test_line_proposals_preserve_top_to_bottom_order_and_reject_border_art():
    image = Image.new('RGB', (240, 160), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 10, 159), fill='black')
    draw.rectangle((35, 25, 200, 45), fill='black')
    draw.rectangle((55, 95, 190, 115), fill='black')
    boxes = line_boxes(image)
    assert len(boxes) == 2 and boxes[0][1] < boxes[1][1]
    assert all(box[0] > 10 for box in boxes)
    assert line_boxes(Image.new('RGB', (100, 100), 'white')) == []


def test_line_tensor_color_order_padding_and_input_limit():
    tensor = prepare_line(Image.new('RGB', (100, 50), (255, 0, 0)))
    assert tensor.shape == (1, 3, 48, 320)
    assert tensor[0, :, 0, 0].tolist() == [-1.0, -1.0, 1.0]
    assert not tensor[:, :, :, 96:].any()
    with pytest.raises(ValueError, match='LINE_TOO_WIDE'):
        prepare_line(Image.new('RGB', (1000, 2)))


def test_changed_weight_is_rejected_before_onnx_load(tmp_path, monkeypatch):
    models = tmp_path / 'models'
    (models / 'weights').mkdir(parents=True)
    (models / 'weights/bad.onnx').write_bytes(b'corrupt')
    (models / 'korean-ocr-candidates.json').write_text(json.dumps({
        'files': [{'path': 'bad.onnx', 'sha256': '0' * 64}],
    }), encoding='utf-8')
    monkeypatch.setattr(korean_paddle, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='MODEL_HASH_MISMATCH'):
        korean_paddle.KoreanPaddleOcr()
