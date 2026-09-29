"""Opt-in local prototype; every displayed translation originates from the real provider."""

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from services.worker.bubble_render import prepare_region, render_region
from services.worker.bubble_vision import BubbleDetector, MangaOcr
from services.worker.translation import MyMemoryTranslator, TranslationError

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts/private/bubble-overlay"
FONT = Path("C:/Windows/Fonts/msyh.ttc")  # Existing Windows font; never redistributed.


class BubblePipeline:
    def __init__(self, *, allow_network=False, output_root=OUTPUT, cache_file=None,
                 korean_ocr="tesseract"):
        if korean_ocr not in {"tesseract", "paddle-v5"}:
            raise ValueError("INVALID_KOREAN_OCR")
        self.korean_ocr = korean_ocr
        self.korean_model = None
        self.detector = BubbleDetector()
        self.japanese = None
        self.allow_network = allow_network
        self.output_root = Path(output_root)
        self.cache_file = Path(cache_file) if cache_file else OUTPUT / "translation-cache.json"
        self.cache = json.loads(self.cache_file.read_text(encoding="utf-8")) \
            if self.cache_file.exists() else {"entries": {}, "attempted_characters": 0}

    def read_paddle(self, image):
        if self.korean_model is None:
            from services.worker.korean_paddle import KoreanPaddleOcr
            self.korean_model = KoreanPaddleOcr()
        output = self.korean_model.read(image)
        lines = output["lines"]
        reason = None
        if not lines or any(not line["text"].strip() for line in lines):
            reason = "OCR_LINE_UNREADABLE"
        confidence = min((line["confidence"] for line in lines), default=0.0) * 100
        return {**output, "confidence": confidence, "reason": reason}

    def save_cache(self):
        temporary = self.cache_file.with_suffix(".partial")
        temporary.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.cache_file)

    def translate(self, text, language):
        key = hashlib.sha256(f"mymemory-v1:{language}:zh-CN:{text}".encode()).hexdigest()
        if key in self.cache["entries"]:
            return self.cache["entries"][key], True
        if not self.allow_network:
            raise TranslationError("NETWORK_NOT_AUTHORIZED")
        if self.cache["attempted_characters"] + len(text) > 1000:
            raise TranslationError("LOCAL_BUDGET_EXCEEDED")
        self.cache["attempted_characters"] += len(text)
        self.save_cache()
        result = MyMemoryTranslator(source_language=language).translate(text).to_dict()
        self.cache["entries"][key] = result
        self.save_cache()
        return result, False

    def process(self, source, sample_id, language, progress=lambda _: None):
        if language not in {"ja", "ko"} or not re.fullmatch(r"[a-z0-9-]{1,40}", sample_id):
            raise ValueError("INVALID_OPTIONS")
        started = time.perf_counter()
        image = Image.open(source)
        if image.width * image.height > 25_000_000 or image.width > 2400 or image.height > 16000:
            raise ValueError("IMAGE_TOO_LARGE")
        image = image.convert("RGB")
        folder = self.output_root / sample_id
        folder.mkdir(parents=True, exist_ok=True)
        progress("正在自动检测气泡与文字")
        regions, detections, tiles = self.detector.detect(image)
        regions.sort(key=lambda r: (r["box"][1] // 100,
                                   -r["box"][0] if language == "ja" else r["box"][0]))
        prepared, crops = {}, []
        debug = image.copy()
        draw = ImageDraw.Draw(debug)
        for index, region in enumerate(regions):
            region.update(id=index, status="pending")
            draw.rectangle(region["bubble"], outline="#238b65", width=3)
            draw.rectangle(region["box"], outline="#f28732", width=2)
            try:
                prepared[index] = prepare_region(image, region)
                x0, y0, x1, y1 = region["box"]
                crop = image.crop((max(0, x0 - 2), max(0, y0 - 2),
                                   min(image.width, x1 + 2), min(image.height, y1 + 2)))
                path = folder / f"crop-{index}.png"
                if (language == "ko" and self.korean_ocr == "tesseract"
                        and not prepared[index]["method"].startswith("white-")):
                    # Separate dark text strokes from translucent artwork before OCR.
                    prep = prepared[index]
                    left, top, _, _ = prep["bounds"]
                    crop = Image.fromarray(255 - prep["ink"]).crop((
                        max(0, x0 - left - 4), max(0, y0 - top - 4),
                        min(prep["ink"].shape[1], x1 - left + 4),
                        min(prep["ink"].shape[0], y1 - top + 4)))
                if language == "ko" and self.korean_ocr == "tesseract":
                    crop = crop.resize((crop.width * 3, crop.height * 3), Image.Resampling.LANCZOS)
                crop.save(path)
                crops.append((index, path))
            except ValueError as exc:
                region.update(status="preserved", reason=str(exc))
        debug.save(folder / "detection.png")
        progress(f"正在识别{len(crops)}个气泡内的文字")
        if language == "ko" and crops:
            if self.korean_ocr == "paddle-v5":
                outputs = []
                for _, path in crops:
                    with Image.open(path) as crop:
                        outputs.append(self.read_paddle(crop))
                (folder / "ocr.json").write_text(
                    json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                manifest = folder / "crops.json"
                manifest.write_text(json.dumps([str(path) for _, path in crops]), encoding="utf-8")
                subprocess.run([shutil.which("node") or "node", "services/worker/ocr_korean.mjs",
                                str(manifest), str(folder / "ocr.json")], cwd=ROOT,
                               check=True, timeout=90, capture_output=True)
                outputs = json.loads((folder / "ocr.json").read_text(encoding="utf-8"))
            for (index, _), output in zip(crops, outputs, strict=True):
                regions[index].update(source=output["text"], ocr_confidence=output["confidence"])
                if output.get("reason"):
                    regions[index].update(status="preserved", reason=output["reason"])
                elif output["confidence"] < 65 or re.search(r"[ㄱ-ㅣ]", output["text"]):
                    regions[index].update(status="preserved", reason="LOW_OCR_CONFIDENCE")
        elif language == "ja" and crops:
            if self.japanese is None:
                self.japanese = MangaOcr()
            for index, path in crops:
                try:
                    regions[index]["source"] = self.japanese.read(Image.open(path))
                except ValueError as exc:
                    regions[index].update(status="preserved", reason=str(exc))
        result_image = image.copy()
        evidence_masks = np.zeros((image.height, image.width), np.uint8)
        for region in regions:
            if region["status"] == "preserved":
                continue
            index, text = region["id"], region.get("source", "").strip()
            try:
                if not text or (language == "ko" and not re.search(r"[가-힣]", text)):
                    raise ValueError("EMPTY_OR_INVALID_OCR")
                progress(f"正在翻译并排版第 {index + 1}/{len(regions)} 个气泡")
                translated, cached = self.translate(text, language)
                region.update(translation=translated["text"], cached=cached,
                              translation_ms=translated["elapsed_ms"])
                if set(translated["warnings"]) & {
                    "NO_CHINESE_CHARACTERS", "UNCHANGED_TEXT", "JAPANESE_REMAINS", "KOREAN_REMAINS",
                }:
                    raise ValueError("TRANSLATION_NEEDS_REVIEW")
                # Restore current pixels so overlapping regions never revert earlier changes.
                current = dict(prepared[index])
                current["roi"] = np.asarray(result_image.crop(current["bounds"]))
                result_image, render = render_region(
                    result_image, current, translated["text"], FONT)
                region.update(status="covered", render=render)
                region["quality"] = "UNREVIEWED_MACHINE_TRANSLATION"
                left, top, right, bottom = current["bounds"]
                evidence_masks[top:bottom, left:right] |= current["safe"]
            except (TranslationError, ValueError) as exc:
                region.update(status="preserved", reason=str(exc))
        image.save(folder / "original.png")
        result_image.save(folder / "translated.png")
        Image.fromarray(evidence_masks).save(folder / "safe-mask.png")
        diff = np.any(np.asarray(result_image) != np.asarray(image), axis=2)
        outside = int(np.count_nonzero(diff & (evidence_masks == 0)))
        if outside:
            raise ValueError("OUTSIDE_MASK_CHANGE")
        result = {
            "sample_id": sample_id, "language": language, "size": image.size,
            "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            "detector": "RT-DETR-v2-int8", "ocr": "manga-ocr-onnx-int8" if language == "ja"
            else self.korean_ocr, "regions": regions, "tiles": tiles,
            "text_free_count": sum(d["class"] == 2 for d in detections),
            "covered": sum(r["status"] == "covered" for r in regions),
            "preserved": sum(r["status"] != "covered" for r in regions),
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "outside_safe_modified_pixels": outside, "modified_pixels": int(diff.sum()),
        }
        (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
        return result
