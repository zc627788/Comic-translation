"""Translate actual OCR JSON files only after an explicit --allow-network flag.

Run from repository root: .venv/Scripts/python -m scripts.probe-free-translation ...
Images and raw results remain in the ignored local evidence directory.
"""

import argparse
import hashlib
import html
import json
import struct
from datetime import UTC, datetime
from pathlib import Path

from services.worker.translation import MAX_BYTES, MyMemoryTranslator, TranslationError

OUTPUT = Path("artifacts/private/free-api-probe")


def segments(text: str) -> list[str]:
    # Only whitespace is normalized. No manual correction or supplied transcript.
    text = "".join(text.split())
    result, current = [], ""
    for char in text:
        if len((current + char).encode("utf-8")) > MAX_BYTES:
            result.append(current)
            current = ""
        current += char
    if current:
        result.append(current)
    return result


def render_report(result: dict) -> str:
    esc = html.escape
    sections = []
    for item in result["samples"]:
        region = item.get("rectangle")
        highlight = ""
        if region:
            width, height = item["image_size"]
            highlight = (
                '<span class="region" aria-label="人工框选区域" style="'
                f'left:{region["left"] / width * 100}%;'
                f'top:{region["top"] / height * 100}%;'
                f'width:{region["width"] / width * 100}%;'
                f'height:{region["height"] / height * 100}%"></span>'
            )
        parts = []
        for part in item["translations"]:
            output = part.get("result", {}).get("text", part.get("error", ""))
            elapsed = part.get("result", {}).get("elapsed_ms", "—")
            request_label = "本地缓存" if part.get("cached") else (
                "本次网络请求" if part.get("attempted", "result" in part) else "没有发起网络请求"
            )
            parts.append(
                f'<div class="pair"><p class="label">OCR 原文 · 自动识别</p>'
                f'<p lang="ja">{esc(part["source"])}</p><p class="label">免费接口原始译文</p>'
                f'<p class="translation">{esc(output)}</p><small>接口耗时 {elapsed} ms'
                f' · {request_label}</small></div>'
            )
        if not parts:
            parts.append('<p class="warning">未识别到文字；没有调用翻译接口。</p>')
        sections.append(
            f'<article><h2>{esc(item.get("label", item["image"]))}</h2>'
            f'<p>OCR：{item["ocr_ms"]} ms · {esc(item["mode"])} 模式 · '
            f'预处理：{esc(item.get("preprocessing", "无"))}</p>'
            f'<p class="warning">人工核对：{esc(item.get("review", "尚未核对"))}</p>'
            f'<div class="comparison"><figure><a class="original" href="{esc(item["image"])}">'
            f'<img src="{esc(item["image"])}" alt="日文漫画原图，点击查看原始尺寸">'
            f'{highlight}</a>'
            '<figcaption>Give My Regards to Black Jack · SHUHO SATO<br>'
            'ブラックジャックによろしく · 佐藤秀峰</figcaption></figure>'
            f'<div>{"".join(parts)}</div></div><details><summary>查看未经整理的 OCR 输出</summary>'
            f'<pre>{esc(item["raw_ocr"])}</pre></details></article>'
        )
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>漫画翻译 · 免费接口实测</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f4ef;color:#202b29;font:16px/1.65 system-ui}}
main{{max-width:1200px;margin:auto;padding:36px 24px}}h1{{font-size:34px;line-height:1.2}}
h2{{font-size:21px}}header,article{{background:white;padding:28px;border-radius:18px;margin-bottom:24px}}
.badge{{color:#216d54;font-weight:650}}.warning{{background:#fff1cf;padding:14px;border-radius:10px}}
.comparison{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px}}
figure{{margin:0}}img{{display:block;width:100%;height:auto;border:1px solid #dde3dc}}
.original{{position:relative;display:block}}.region{{position:absolute;border:2px solid #2e8964;
background:#19c17b18;pointer-events:none}}
figcaption,small,.label{{color:#5d6d64;font-size:13px}}
.pair{{border-bottom:1px solid #e2e9e2;padding:10px 0 22px}}
.pair p{{margin:8px 0}}.translation{{font-size:20px}}a{{color:#216d54}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere}}details{{margin-top:20px}}
@media(max-width:720px){{.comparison{{grid-template-columns:1fr}}main{{padding:16px}}}}
</style><main><header><span class="badge">P01 · 真实请求记录</span>
<h1>免费翻译，效果到底如何？</h1>
<p>下方是本地 OCR 与 MyMemory 返回的真实结果。译文没有人工润色。
生成时间：{esc(result["created_at"])}</p>
<p class="warning">这是实验结果对照，不代表插件已完成原位覆盖、擦字或导出。
Tesseract 只是轻量对照，尚未使用 manga-ocr。</p>
<p>本次请求：{result["network_requests"]} 条 · 发出原文：{result["attempted_characters"]} 字符
· 未配置支付凭据。图片仅在本机识别，只有文字发送给 MyMemory。</p>
<p><a href="https://www.densho810.com/free/">作者官方原作与使用条件</a> ·
<a href="https://www.tadapic.com/blackjack.php">空白气泡对照来源</a></p></header>
{"".join(sections)}<footer>小样本不能代表整章质量。网页兼容、广告排除和扩展运行另行验收。</footer></main></html>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path, help="Local JSON list with image/ocr filenames")
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cache_path = OUTPUT / "translation-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    translator = MyMemoryTranslator()
    result = {"created_at": datetime.now(UTC).isoformat(), "samples": [], "network_requests": 0}
    for sample in manifest:
        # Private manifest is local developer input, not an HTTP-supplied path.
        for name in (sample["image"], sample["ocr"]):
            if Path(name).name != name or "\\" in name or "/" in name:
                raise ValueError("Manifest filenames must be basenames")
        ocr = json.loads((OUTPUT / sample["ocr"]).read_text(encoding="utf-8"))
        image_bytes = (OUTPUT / sample["image"]).read_bytes()
        if image_bytes[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("This evidence renderer accepts PNG only")
        digest = hashlib.sha256(image_bytes).hexdigest()
        if digest != ocr["source_sha256"]:
            raise ValueError("OCR evidence does not match the image")
        item = {**sample, "raw_ocr": ocr["text"], "ocr_ms": ocr["elapsed_ms"],
                "mode": ocr["mode"], "rectangle": ocr.get("rectangle"),
                "image_size": struct.unpack(">II", image_bytes[16:24]), "translations": []}
        for source in segments(ocr["text"]):
            key = hashlib.sha256(("mymemory:ja:zh-CN:v1:" + source).encode()).hexdigest()
            part = {"source": source, "cached": key in cache, "attempted": False}
            if key in cache:
                part["result"] = cache[key]
            elif not args.allow_network:
                part["error"] = "NETWORK_NOT_AUTHORIZED"
            else:
                before = translator.attempted_characters
                try:
                    part["result"] = translator.translate(source).to_dict()
                    cache[key] = part["result"]
                    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
                except TranslationError as exc:
                    part["error"] = exc.code
                if translator.attempted_characters > before:
                    part["attempted"] = True
                    result["network_requests"] += 1
            item["translations"].append(part)
        result["samples"].append(item)
    result["attempted_characters"] = translator.attempted_characters
    (OUTPUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    (OUTPUT / "index.html").write_text(render_report(result), encoding="utf-8")
    print(json.dumps({key: val for key, val in result.items() if key != "samples"}))


if __name__ == "__main__":
    main()
