"""Offline six-image re-render/restore regression; does not call a provider."""

import json
from uuid import uuid4

import numpy as np
from PIL import Image

from services.worker.bubble_pipeline import OUTPUT, ROOT
from services.worker.private_store import write_json
from services.worker.proofreading import SAMPLES, Proofreader, digest


def main():
    cache = OUTPUT / "translation-cache.json"
    before = digest(cache)
    output = ROOT / "artifacts/private" / ("proofreading-check-" + uuid4().hex)
    reader = Proofreader(output=output)
    records = []
    for sample in SAMPLES:
        initial = reader.state(sample)
        original_hash = digest(reader.image_path(sample, original=True))
        saved = reader.revise(sample, 0, {}, restore=True)
        with Image.open(reader.baseline / sample / "translated.png") as old:
            with Image.open(reader.image_path(sample)) as new:
                changed = int(np.count_nonzero(np.any(
                    np.asarray(old.convert("RGB")) != np.asarray(new.convert("RGB")), axis=2)))
        assert changed == 0 and saved["outside_safe_modified_pixels"] == 0
        assert digest(reader.image_path(sample, original=True)) == original_hash
        records.append({"sample_id": sample, "regions": len(initial["regions"]),
                        "covered": sum(r["status"] == "covered" for r in initial["regions"]),
                        "restored_vs_baseline_changed_pixels": changed,
                        "outside_safe_modified_pixels": 0,
                        "original_unchanged": True})
    assert digest(cache) == before
    report = {"kind": "REAL_SIX_IMAGE_RERENDER_NO_NETWORK", "samples": records,
              "cache_unchanged": True, "runtime_source_sha256": {
                  p: digest(ROOT / p) for p in [
                      "services/worker/proofreading.py", "services/worker/bubble_render.py"]}}
    write_json(ROOT / "reports/evidence/P01-proofreading-regression.json", report)
    write_json(output / "summary.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
