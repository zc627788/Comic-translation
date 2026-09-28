"""CPU model adapters. Weights are local, hash-verified, never downloaded on requests."""

import hashlib
import unicodedata
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

WEIGHTS = Path(__file__).resolve().parents[2] / "models/weights"
HASHES = {
    "detector/detector_int8.onnx":
        "b5022ad46416b6fe4f88b0cc082cfd2ff5b1cfc624088c2f19879485493f5913",
    "manga-ocr/encoder_model_int8.onnx":
        "0eaf2b867292a44700ce38ef028b90639a2e36fc4c18c2bcdd1de7409488adb3",
    "manga-ocr/decoder_model_int8.onnx":
        "3ff0d4c34c4a66613d98ff93e0b17f22a7b09dfbeec195c3e4d6f595af3a6b6c",
    "manga-ocr/vocab.txt":
        "5cb5c5586d98a2f331d9f8828e4586479b0611bfba5d8c3b6dadffc84d6a36a3",
}


def load_model(name):
    path = WEIGHTS / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != HASHES[name]:
        raise ValueError("MODEL_HASH_MISMATCH")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


def tile_ranges(width, height):
    if height <= width * 2:
        return [(0, height)]
    size, overlap = int(width * 1.6), int(width * .35)
    starts = list(range(0, max(1, height - size + 1), size - overlap))
    if starts[-1] + size < height:
        starts.append(height - size)
    return [(start, min(height, start + size)) for start in starts]


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def intersection(a, b):
    return area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def deduplicate(detections):
    kept = []
    for item in sorted(detections, key=lambda d: d["score"], reverse=True):
        if any(item["class"] == other["class"] and
               intersection(item["box"], other["box"]) /
               max(1, area(item["box"]) + area(other["box"]) -
                   intersection(item["box"], other["box"])) > .45 for other in kept):
            continue
        kept.append(item)
    return kept


class BubbleDetector:
    def __init__(self):
        self.session = load_model("detector/detector_int8.onnx")

    def detect(self, image):
        width, height = image.size
        detections = []
        tiles = tile_ranges(width, height)
        for top, bottom in tiles:
            crop = image.crop((0, top, width, bottom))
            pixels = np.asarray(crop.resize((640, 640), Image.Resampling.BILINEAR))
            pixels = pixels.astype(np.float32).transpose(2, 0, 1)[None] / 255
            labels, boxes, scores = self.session.run(None, {
                "images": pixels, "orig_target_sizes": np.array([crop.size], dtype=np.int64),
            })
            for label, box, score in zip(labels[0], boxes[0], scores[0], strict=True):
                if score < .5:
                    continue
                # Discard clipped detections on internal tile seams; overlaps cover them.
                if (top > 0 and box[1] < 3) or (bottom < height and box[3] > bottom - top - 3):
                    continue
                x0, y0, x1, y1 = box
                box = [max(0, int(x0)), max(0, int(y0) + top),
                       min(width, int(np.ceil(x1))), min(height, int(np.ceil(y1)) + top)]
                if area(box) > 20:
                    detections.append({"class": int(label), "box": box, "score": float(score)})
        detections = deduplicate(detections)
        bubbles = [d for d in detections if d["class"] == 0]
        regions = []
        for text in [d for d in detections if d["class"] == 1]:
            matches = [b for b in bubbles if intersection(b["box"], text["box"]) /
                       area(text["box"]) > .97]
            if matches:
                bubble = min(matches, key=lambda b: area(b["box"]))
                regions.append({"box": text["box"], "bubble": bubble["box"],
                                "score": text["score"]})
        # Merge two detected text boxes belonging to the same bubble before OCR/erasure.
        merged = {}
        for region in regions:
            key = tuple(region["bubble"])
            if key in merged:
                a, b = merged[key]["box"], region["box"]
                merged[key]["box"] = [min(a[0], b[0]), min(a[1], b[1]),
                                      max(a[2], b[2]), max(a[3], b[3])]
            else:
                merged[key] = region
        return list(merged.values()), detections, tiles


class MangaOcr:
    def __init__(self):
        self.encoder = load_model("manga-ocr/encoder_model_int8.onnx")
        self.decoder = load_model("manga-ocr/decoder_model_int8.onnx")
        vocab = (WEIGHTS / "manga-ocr/vocab.txt").read_bytes()
        if hashlib.sha256(vocab).hexdigest() != HASHES["manga-ocr/vocab.txt"]:
            raise ValueError("MODEL_HASH_MISMATCH")
        self.vocab = vocab.decode("utf-8").splitlines()

    def read(self, crop):
        crop = crop.convert("L").convert("RGB").resize((224, 224), Image.Resampling.BILINEAR)
        pixels = np.asarray(crop).astype(np.float32).transpose(2, 0, 1)[None] / 127.5 - 1
        hidden = self.encoder.run(None, {"pixel_values": pixels})[0]
        ids = [2]  # Original manga-ocr BERT CLS / SEP token IDs.
        for _ in range(160):
            logits = self.decoder.run(None, {
                "input_ids": np.array([ids], dtype=np.int64), "encoder_hidden_states": hidden,
            })[0]
            token = int(logits[0, -1].argmax())
            if token == 3:
                text = "".join(self.vocab[i] for i in ids[1:] if i > 4).replace("##", "")
                if 1 in ids:
                    raise ValueError("OCR_UNKNOWN_TOKEN")
                return unicodedata.normalize("NFKC", text)
            ids.append(token)
        raise ValueError("OCR_TRUNCATED")
