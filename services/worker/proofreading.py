"""Versioned local proofreading: immutable inputs, atomic revisions, explicit candidates."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image

from services.worker.bubble_pipeline import FONT, OUTPUT, ROOT, BubblePipeline
from services.worker.bubble_render import prepare_region, render_region
from services.worker.private_store import exclusive, write_json
from services.worker.translation import MAX_BYTES

SAMPLES = (
    "ko-pc-ep01-1", "ko-pc-ep01-2", "ko-pc-ep03-1",
    "fx-ko-plain", "fx-ko-small", "fx-ko-seam",
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_text(text):
    if (not isinstance(text, str) or not text.strip() or len(text) > 500
            or any(ord(c) < 32 and c != "\n" for c in text)):
        raise ValueError("INVALID_TEXT")
    return text.strip()


def context_payload(regions):
    items = [r for r in regions if r.get("source", "").strip()]
    if len(items) < 2:
        raise ValueError("INSUFFICIENT_CONTEXT")
    if any("[[" in r["source"] or "]]" in r["source"] for r in items):
        raise ValueError("INVALID_CONTEXT_MARKER")
    text = "\n".join(f'[[{r["id"]}]] {r["source"]}' for r in items)
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("CONTEXT_TOO_LONG")
    return text, [r["id"] for r in items]


def parse_context(text, ids):
    matches = list(re.finditer(r"\[\[(\d+)\]\]", text))
    if (not matches or text[:matches[0].start()].strip()
            or [m.group(1) for m in matches] != [str(i) for i in ids]):
        raise ValueError("CONTEXT_ALIGNMENT_FAILED")
    output = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = checked_text(text[match.end():end])
        if ("[[" in value or "]]" in value
                or not any("\u3400" <= c <= "\u9fff" for c in value)
                or any("\u3040" <= c <= "\u30ff" or "\uac00" <= c <= "\ud7af" for c in value)):
            raise ValueError("CONTEXT_TRANSLATION_NEEDS_REVIEW")
        output[str(ids[index])] = value
    return output


class Proofreader:
    def __init__(self, baseline=None, output=None, diagnostic=None, cache_file=None):
        self.baseline = Path(baseline or ROOT / "artifacts/private/paddle-live-v1")
        self.output = Path(output or ROOT / "artifacts/private/proofreading-v1")
        self.diagnostic = Path(diagnostic or ROOT / (
            "artifacts/private/quality-v1/runs/paddle-polarity-v1"))
        self.cache_file = Path(cache_file or OUTPUT / "translation-cache.json")

    def paths(self, sample):
        if sample not in SAMPLES:
            raise ValueError("UNKNOWN_SAMPLE")
        return self.baseline / sample, self.output / sample

    def state(self, sample):
        base, folder = self.paths(sample)
        result = read_json(base / "result.json")
        baseline_hash = digest(base / "result.json") + ":" + digest(base / "original.png")
        regions = result["regions"]
        diag_path = self.diagnostic / sample
        if (diag_path / "diagnostic-ocr.json").exists():
            diagnostics = read_json(diag_path / "diagnostic-ocr.json")
            boxes = read_json(diag_path / "result.json")["regions"]
            # Diagnostics may include unsafe crops, but cannot authorize erasure.
            if (len(diagnostics) == len(regions) == len(boxes)
                    and all(a["box"] == b["box"] for a, b in zip(regions, boxes, strict=True))):
                for region, diag in zip(regions, diagnostics, strict=True):
                    if not region.get("source"):
                        region["source"] = diag.get("text", "")
                        region["source_origin"] = "UNREVIEWED_DIAGNOSTIC_OCR"
        revision = 0
        filename = None
        if (folder / "current.json").exists():
            pointer = read_json(folder / "current.json")
            saved = read_json(folder / pointer["record"])
            if saved["baseline_hash"] != baseline_hash:
                raise ValueError("BASELINE_CHANGED")
            regions, revision, filename = saved["regions"], saved["revision"], saved["image"]
        else:
            for region in regions:
                region["machine_translation"] = region.get("translation", "")
                region["original_source"] = region.get("source", "")
                region["edited"] = False
        return {"sample_id": sample, "revision": revision, "regions": regions,
                "size": result["size"], "language": result["language"],
                "baseline_hash": baseline_hash, "image": filename,
                "outside_safe_modified_pixels": 0}

    def image_path(self, sample, revision=None, original=False):
        base, folder = self.paths(sample)
        if original or revision == 0:
            return base / ("original.png" if original else "translated.png")
        current = self.state(sample)
        if revision is not None and revision != current["revision"]:
            raise ValueError("REVISION_CONFLICT")
        return folder / current["image"] if current["image"] else base / "translated.png"

    def revise(self, sample, expected, edits, restore=False):
        base, folder = self.paths(sample)
        with exclusive(self.output / "render.lock"), exclusive(folder / "revision.lock"):
            state = self.state(sample)
            if state["revision"] != expected:
                raise ValueError("REVISION_CONFLICT")
            if restore and edits:
                raise ValueError("INVALID_EDIT")
            ids = {str(r["id"]): r for r in state["regions"]}
            for key, edit in edits.items():
                if key not in ids or not isinstance(edit, dict) or not edit:
                    raise ValueError("INVALID_EDIT")
                region = ids[key]
                if set(edit) - {"source", "translation"}:
                    raise ValueError("INVALID_EDIT")
                if "translation" in edit and region["status"] != "covered":
                    raise ValueError("UNSAFE_REGION")
                for field, value in edit.items():
                    region[field] = checked_text(value)
                region["edited"] = True
                region["quality"] = "EDITED_NOT_LANGUAGE_VERIFIED"
            if restore:
                for region in state["regions"]:
                    region["source"] = region["original_source"]
                    region["translation"] = region["machine_translation"]
                    region["edited"] = False
                    region["quality"] = "UNREVIEWED_MACHINE_TRANSLATION"
            with Image.open(base / "original.png") as source:
                original = source.convert("RGB")
            image = original.copy()
            union = np.zeros((image.height, image.width), dtype=bool)
            for region in state["regions"]:
                if region["status"] != "covered":
                    continue
                prepared = prepare_region(original, region)
                x0, y0, x1, y1 = prepared["bounds"]
                union[y0:y1, x0:x1] |= prepared["safe"] > 0
                prepared["roi"] = np.asarray(image.crop(prepared["bounds"]))
                image, region["render"] = render_region(
                    image, prepared, region["translation"], FONT)
            changed = np.any(np.asarray(original) != np.asarray(image), axis=2)
            outside = int(np.count_nonzero(changed & ~union))
            if outside:
                raise ValueError("PIXEL_OUTSIDE_SAFE_ZONE")
            version = f'{expected + 1}-{uuid4().hex}'
            filename = version + ".png"
            image.save(folder / filename)
            state.update(revision=expected + 1, image=filename,
                         outside_safe_modified_pixels=outside,
                         saved_at=datetime.now(UTC).isoformat())
            write_json(folder / (version + ".json"), state)
            # Commit pointer last: failed rendering/writes never replace the current revision.
            write_json(folder / "current.json", {"record": version + ".json"})
            return state

    def context(self, sample, expected):
        state = self.state(sample)
        if state["revision"] != expected:
            raise ValueError("REVISION_CONFLICT")
        text, ids = context_payload(state["regions"])
        # No detector/OCR is loaded. Reuse the serialized, persistent provider budget.
        client = BubblePipeline.__new__(BubblePipeline)
        client.allow_network = True
        client.cache_file = self.cache_file
        client.cache = {"entries": {}, "attempted_characters": 0}
        translated, cached = client.translate(text, state["language"])
        result = {"revision": expected, "source": text, "response": translated,
                  "cached": cached, "attempted_characters": client.cache["attempted_characters"],
                  "quality": "UNREVIEWED_CONTEXT_CANDIDATE", "candidates": {}, "error": None}
        try:
            result["candidates"] = parse_context(translated["text"], ids)
        except ValueError as exc:
            result["error"] = str(exc)
        _, folder = self.paths(sample)
        write_json(folder / ("context-" + uuid4().hex + ".json"), result)
        if self.state(sample)["revision"] != expected:
            raise ValueError("REVISION_CONFLICT")
        return result
