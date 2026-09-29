"""Run real detection/OCR and optional cached pipeline on every frozen input."""

import argparse
import hashlib
import html
import json
import platform
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path

from PIL import Image

from services.worker.bubble_pipeline import OUTPUT, ROOT, BubblePipeline
from services.worker.bubble_vision import MangaOcr
from services.worker.quality_metrics import score_regions


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def diagnose(pipeline, image, language, folder):
    started = time.perf_counter()
    regions, _, _ = pipeline.detector.detect(image)
    rows, files = [], []
    for index, region in enumerate(regions):
        box = region["box"]
        x0, y0, x1, y1 = box
        crop = image.crop((max(0, x0 - 2), max(0, y0 - 2),
                           min(image.width, x1 + 2), min(image.height, y1 + 2)))
        path = folder / f"diagnostic-{index}.png"
        if language == "ko" and pipeline.korean_ocr == "tesseract":
            crop = crop.resize((crop.width * 3, crop.height * 3), Image.Resampling.LANCZOS)
        crop.save(path)
        files.append(str(path))
        rows.append({"box": box, "text": "", "status": "pending"})
    if language == "ko" and rows:
        if pipeline.korean_ocr == "paddle-v5":
            outputs = []
            for file in files:
                with Image.open(file) as crop:
                    outputs.append(pipeline.read_paddle(crop))
            write_json(folder / "diagnostic-ocr.json", outputs)
        else:
            write_json(folder / "diagnostic-crops.json", files)
            subprocess.run([shutil.which("node") or "node", "services/worker/ocr_korean.mjs",
                            str(folder / "diagnostic-crops.json"),
                            str(folder / "diagnostic-ocr.json")],
                           cwd=ROOT, check=True, timeout=120, capture_output=True)
            outputs = read_json(folder / "diagnostic-ocr.json")
        for row, output in zip(rows, outputs, strict=True):
            row.update(text=output["text"], confidence=output["confidence"],
                       status="recognized", line_warning=output.get("reason"))
    elif rows:
        if pipeline.japanese is None:
            pipeline.japanese = MangaOcr()
        for row, file in zip(rows, files, strict=True):
            try:
                row.update(text=pipeline.japanese.read(Image.open(file)), status="recognized")
            except ValueError as exc:
                row.update(status="failed", reason=str(exc))
    return {"preprocessing": f"raw-crop-plus-2px; ko={pipeline.korean_ocr}; no erasure gate",
            "regions": rows, "elapsed_ms": round((time.perf_counter() - started) * 1000)}


def render_review(manifest, rows, run_root):
    sections = []
    for sample, row in zip(manifest["samples"], rows, strict=True):
        sid = sample["id"]
        regions = row.get("diagnostics", {}).get("regions", [])
        items = "".join(f"<li>{html.escape(r.get('text', '')) or '（识别为空）'}</li>"
                        for r in regions)
        metrics = html.escape(json.dumps(row.get("gold_metrics"), ensure_ascii=False, indent=2))
        sections.append(f"<section id='{sid}'><h2>{sid} · {sample['language']} · "
                        f"{sample['kind']}</h2><p>{html.escape(sample['credit'])}</p>"
                        f"<p>覆盖 {row.get('covered', 0)}；保留 {row.get('preserved', 0)}；"
                        "原文诊断不等于人工真值，未命中缓存的译文未执行。</p>"
                        f"<div class='pair'><img loading='lazy' src='/images/{sid}.png' alt='原图'>"
                        f"<img loading='lazy' src='/results/{sid}/translated.png' "
                        "alt='处理结果；若任务失败则无输出'></div>"
                        f"<details><summary>原始 OCR 诊断（未人工纠错）</summary><ol>{items}</ol>"
                        f"<pre>{metrics}"
                        "</pre></details></section>")
    document = """<!doctype html><html lang='zh-CN'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>30 图质量基线 · 本地核对</title><style>
body{font:15px 'Microsoft YaHei',sans-serif;background:#f2f4ef;color:#24382e;
margin:30px auto;max-width:1200px;padding:20px}
section{background:white;border:1px solid #d9e0d5;border-radius:12px;padding:20px;margin:24px 0}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}
img{width:100%;height:auto}
li{white-space:pre-wrap}pre{overflow:auto}h1{font-size:30px}p{line-height:1.8}
</style><h1>固定 30 图 · 质量基线</h1>
<p>12 页日漫 / 12 页韩文译版 / 6 张原创夹具。默认离线，无新翻译请求。
真实页尚未独立标注，不能计算准确率。韩国原创韩漫样本仍缺。原图和完整 OCR 仅在本机。</p>
""" + "<p>本次配置：" + html.escape(manifest.get("run_label", "legacy")) + "</p>" \
        + "".join(sections) + "</html>"
    (run_root / "review.html").write_text(document, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=ROOT / "artifacts/private/quality-v1")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--run-id", default="baseline-v1")
    parser.add_argument("--korean-ocr", choices=["tesseract", "paddle-v5"], default="tesseract")
    args = parser.parse_args()
    if not args.run_id.replace("-", "").isalnum():
        parser.error("Use an alphanumeric run ID")
    corpus = args.corpus.resolve()
    manifest_path = corpus / "manifest.json"
    manifest = read_json(manifest_path)
    samples = manifest["samples"]
    if len(samples) != 30 or len({s["id"] for s in samples}) != 30:
        raise ValueError("CORPUS_REQUIRES_30_UNIQUE_IDS")
    for sample in samples:
        path = (corpus / sample["path"]).resolve()
        if not path.is_relative_to(corpus) or not sample["id"].replace("-", "").isalnum():
            raise ValueError("INVALID_SAMPLE_PATH_OR_ID")
        if hashlib.sha256(path.read_bytes()).hexdigest() != sample["sha256"]:
            raise ValueError("FROZEN_INPUT_CHANGED")
    run_root = corpus / "runs" / args.run_id
    if run_root.exists():
        raise ValueError("RUN_EXISTS: choose a new ID to preserve evidence")
    run_root.mkdir(parents=True)
    cache_path = OUTPUT / "translation-cache.json"
    cache_before = cache_path.read_bytes() if cache_path.exists() else b""
    started = time.perf_counter()
    pipeline = BubblePipeline(allow_network=args.allow_network, output_root=run_root,
                              korean_ocr=args.korean_ocr)
    rows = []
    for sample in samples:
        sid = sample["id"]
        row = {"id": sid, "kind": sample["kind"], "language": sample["language"],
               "gold_metrics": None, "state": "failed"}
        folder = run_root / sid
        folder.mkdir()
        try:
            with Image.open(corpus / sample["path"]) as image:
                diagnostic = diagnose(pipeline, image.convert("RGB"), sample["language"], folder)
            row["diagnostics"] = diagnostic
            row["gold_metrics"] = score_regions(sample["annotation"], diagnostic["regions"])
            result = pipeline.process(corpus / sample["path"], sid, sample["language"])
            row.update(state="completed", covered=result["covered"], preserved=result["preserved"],
                       detected_dialogues=len(result["regions"]), pipeline_ms=result["elapsed_ms"],
                       outside_safe_modified_pixels=result["outside_safe_modified_pixels"],
                       cache_hits=sum(r.get("cached", False) for r in result["regions"]),
                       reasons=dict(Counter(r["reason"] for r in result["regions"]
                                            if r["status"] == "preserved")))
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            row["failure_type"] = type(exc).__name__
        rows.append(row)
        write_json(folder / "baseline.json", row)
        print(sid, row["state"], "covered", row.get("covered", 0),
              "preserved", row.get("preserved", 0), flush=True)
    after = cache_path.read_bytes() if cache_path.exists() else b""
    if not args.allow_network and cache_before != after:
        raise ValueError("OFFLINE_RUN_CHANGED_TRANSLATION_CACHE")
    public_rows = [{k: v for k, v in row.items() if k != "diagnostics"} for row in rows]
    summary = {"corpus_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
               "run_id": args.run_id, "korean_ocr": args.korean_ocr,
               "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                 for name in ["services/worker/bubble_pipeline.py",
                                              "services/worker/korean_paddle.py",
                                              "scripts/run-quality-baseline.py"]},
               "mode": "network-enabled" if args.allow_network else "cache-only",
               "python": platform.python_version(), "platform": platform.system(),
               "code_base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                            cwd=ROOT, text=True).strip(),
               "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"],
                                                                   cwd=ROOT, text=True).strip()),
               "elapsed_ms": round((time.perf_counter() - started) * 1000),
               "translation_cache_unchanged": cache_before == after,
               "results": public_rows}
    write_json(run_root / "summary.json", summary)
    manifest["run_label"] = f"{args.run_id} / {args.korean_ocr} / {summary['mode']}"
    render_review(manifest, rows, run_root)
    print("COMPLETE", len(rows), "inputs; elapsed_ms", summary["elapsed_ms"], flush=True)


if __name__ == "__main__":
    main()
