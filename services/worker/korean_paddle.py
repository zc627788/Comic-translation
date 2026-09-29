"""Local research adapter for the official Korean PP-OCRv5 line recognizer."""

import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import yaml

ROOT = Path(__file__).resolve().parents[2]


def decode_ctc(probabilities, characters):
    if probabilities.ndim != 2 or probabilities.shape[1] != len(characters):
        raise ValueError("CTC_DICTIONARY_MISMATCH")
    indices = probabilities.argmax(axis=1)
    text, scores, previous = [], [], -1
    for index, token in enumerate(indices):
        if token != 0 and token != previous:
            text.append(characters[token])
            scores.append(float(probabilities[index, token]))
        previous = token
    return ''.join(text), float(np.mean(scores)) if scores else 0.0


def line_boxes(image):
    """Projection-based line proposals from pixels only, never annotation text."""
    gray = np.asarray(image.convert('L'))
    threshold = min(180, float(np.percentile(gray, 80)) * .65)
    mask = (gray < threshold).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    keep = []
    for i in range(1, count):
        x, y, width, height, area = stats[i]
        if area >= 6 and x > 0 and y > 0 and x + width < image.width \
                and y + height < image.height:
            keep.append(i)
    mask = np.isin(labels, keep)
    active = (mask.sum(axis=1) >= max(2, image.width * .008)).astype(np.uint8)
    active = cv2.morphologyEx(active[:, None], cv2.MORPH_CLOSE,
                             np.ones((7, 1), np.uint8)).ravel()
    edges = np.diff(np.r_[0, active, 0].astype(int))
    boxes = []
    for top, bottom in zip(np.where(edges == 1)[0], np.where(edges == -1)[0], strict=True):
        if bottom - top < 5:
            continue
        columns = np.where(mask[top:bottom].any(axis=0))[0]
        if not len(columns):
            continue
        boxes.append([max(0, int(columns[0]) - 3), max(0, int(top) - 3),
                      min(image.width, int(columns[-1]) + 4), min(image.height, int(bottom) + 3)])
    return boxes


def prepare_line(image):
    if image.width < 2 or image.height < 2 or image.width * image.height > 4_000_000:
        raise ValueError("INVALID_LINE_SIZE")
    resized_width = math.ceil(48 * image.width / image.height)
    if resized_width > 3200:
        raise ValueError("LINE_TOO_WIDE")
    width = max(320, resized_width)
    bgr = np.asarray(image.convert('RGB'))[:, :, ::-1]
    resized = cv2.resize(bgr, (resized_width, 48)).astype(np.float32)
    tensor = np.zeros((1, 3, 48, width), dtype=np.float32)
    tensor[0, :, :, :resized_width] = resized.transpose(2, 0, 1) / 127.5 - 1
    return tensor


class KoreanPaddleOcr:
    def __init__(self):
        registry = json.loads((ROOT / 'models/korean-ocr-candidates.json').read_text('utf-8'))
        paths = []
        for file in registry['files']:
            path = ROOT / 'models/weights' / file['path']
            if hashlib.sha256(path.read_bytes()).hexdigest() != file['sha256']:
                raise ValueError("MODEL_HASH_MISMATCH")
            paths.append(path)
        config_path = next(p for p in paths if p.suffix == '.yml')
        config = yaml.safe_load(config_path.read_text('utf-8'))
        self.characters = [''] + config['PostProcess']['character_dict'] + [' ']
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        model_path = next(p for p in paths if p.suffix == '.onnx')
        self.session = ort.InferenceSession(str(model_path), options,
                                           providers=['CPUExecutionProvider'])
        if self.session.get_outputs()[0].shape[-1] != len(self.characters):
            raise ValueError("MODEL_DICTIONARY_MISMATCH")

    def read(self, image, *, split_lines=True):
        boxes = line_boxes(image) if split_lines else [[0, 0, image.width, image.height]]
        lines = []
        for box in boxes:
            tensor = prepare_line(image.crop(box))
            output = self.session.run(None, {self.session.get_inputs()[0].name: tensor})[0][0]
            text, confidence = decode_ctc(output, self.characters)
            lines.append({'box': box, 'text': text, 'confidence': confidence})
        return {'text': ' '.join(row['text'] for row in lines).strip(), 'lines': lines,
                'status': 'recognized' if lines else 'NO_LINE_PROPOSALS'}
