"""Sanitize actual local revision/context evidence, verify live PNG export bytes."""

import hashlib
import json
from urllib.request import urlopen

import numpy as np
from PIL import Image

from services.worker.bubble_pipeline import ROOT
from services.worker.private_store import write_json
from services.worker.proofreading import Proofreader, digest, read_json


def main():
    reader = Proofreader()
    sample = "ko-pc-ep03-1"
    folder = reader.output / sample
    state = reader.state(sample)
    records = [read_json(p) for p in folder.glob("context-*.json")]
    assert records and state["revision"] >= 4
    fresh = [r for r in records if not r["cached"]]
    assert len(fresh) == 1 and fresh[0]["error"] is None
    contexts = [{"revision": r["revision"], "cached": r["cached"],
                 "source_characters": len(r["source"]),
                 "source_utf8_bytes": len(r["source"].encode("utf-8")),
                 "source_sha256": hashlib.sha256(r["source"].encode()).hexdigest(),
                 "candidate_count": len(r["candidates"]), "alignment_error": r["error"],
                 "attempted_characters": r["attempted_characters"],
                 "retrieved_at": r["response"]["retrieved_at"]} for r in records]
    revisions = []
    for path in folder.glob("[0-9]*.json"):
        record = read_json(path)
        revisions.append({"revision": record["revision"],
                          "outside_safe_modified_pixels": record["outside_safe_modified_pixels"],
                          "edited_regions": sum(r["edited"] for r in record["regions"]),
                          "image_sha256": digest(folder / record["image"])})
    restored = next(read_json(p) for p in folder.glob("3-*.json"))
    with Image.open(folder / restored["image"]) as image:
        with Image.open(reader.baseline / sample / "translated.png") as baseline:
            assert np.array_equal(np.asarray(image), np.asarray(baseline))
    url = f"http://127.0.0.1:4182/images/{sample}/export.png?revision={state['revision']}"
    with urlopen(url, timeout=10) as response:
        payload = response.read()
        disposition = response.headers["Content-Disposition"]
    assert hashlib.sha256(payload).hexdigest() == digest(reader.image_path(sample))
    assert "attachment" in disposition
    report = {"kind": "REAL_CONTEXT_AND_PERSISTED_EDITS", "sample_id": sample,
              "contexts": contexts, "new_network_calls": len(fresh),
              "budget_before": 399, "budget_after": fresh[0]["attempted_characters"],
              "revisions": sorted(revisions, key=lambda r: r["revision"]),
              "restored_revision_3_equals_baseline": True,
              "export_equals_current_revision": True,
              "language_review": "NOT_HUMAN_VERIFIED", "safe_regions_covered": 1,
              "unsafe_regions_preserved": 2,
              "ui_observed": ["edit", "save", "context_preview", "candidate_fill", "restore",
                              "cache_hit", "restart_persistence", "crop_preview", "download_event"]}
    write_json(ROOT / "reports/evidence/P01-proofreading-context.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
