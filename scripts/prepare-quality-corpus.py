"""Prepare a frozen development corpus. Original images/annotations stay private."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "artifacts/private/quality-v1"
EPISODES = ["ep01_Potion-of-Flight", "ep02_Rainbow-potions",
            "ep03_The-secret-ingredients", "ep04_Stroke-of-genius"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def acquire(url, destination, allow_network):
    if destination.exists():
        return
    if not allow_network:
        raise ValueError("DOWNLOAD_NOT_AUTHORIZED")
    for attempt in range(3):
        try:
            download(url, destination)
            return
        except (OSError, ValueError):
            if attempt == 2:
                raise


def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    with urlopen(url, timeout=60) as response, temporary.open("wb") as output:
        expected = response.headers.get("Content-Length")
        total = 0
        while block := response.read(1024 * 1024):
            total += len(block)
            if total > 30_000_000:
                raise ValueError("DOWNLOAD_TOO_LARGE")
            output.write(block)
    if expected is not None and total != int(expected):
        raise ValueError("DOWNLOAD_TRUNCATED")
    if destination.suffix == ".jpg":
        with Image.open(temporary) as image:
            image.load()
    temporary.replace(destination)


def add_record(records, sample_id, language, family, kind, tags, source, credit, license_url,
               original_hash=None, transform=None, annotation=None):
    path = CORPUS / "images" / f"{sample_id}.png"
    with Image.open(path) as image:
        size = list(image.size)
    records.append({"id": sample_id, "language": language, "family": family,
                    "kind": kind, "split": "development", "tags": tags,
                    "path": f"images/{sample_id}.png", "sha256": digest(path), "size": size,
                    "source": source, "credit": credit, "license_url": license_url,
                    "original_sha256": original_hash, "transform": transform,
                    "annotation_status": "generated_ground_truth" if annotation is not None
                    else "not_annotated", "annotation": annotation})


def fixtures(records):
    font_path = Path("C:/Windows/Fonts/malgun.ttf")
    jp_path = Path("C:/Windows/Fonts/YuGothM.ttc")
    if not jp_path.exists():
        jp_path = Path("C:/Windows/Fonts/msyh.ttc")
    configs = [
        ("fx-ko-plain", "ko", (800, 900), 32, ["white", "irregular"],
         [(120, 180, ["안녕하세요!", "오늘은 함께 걸어요."])]),
        ("fx-ko-small", "ko", (800, 900), 17, ["small_text", "low_resolution"],
         [(120, 180, ["기차는 오후 세 시에 출발해요.", "시간을 꼭 확인해 주세요."])]),
        ("fx-ko-dark", "ko", (800, 900), 30, ["dark_bubble"],
         [(120, 180, ["불을 켜 주세요.", "아무것도 보이지 않아요."])]),
        ("fx-ko-seam", "ko", (800, 2900), 30, ["long_strip", "tile_seam"],
         [(130, 1190, ["잠깐 기다려 주세요.", "같이 공원에 가요."]),
          (160, 2170, ["여기에서 쉬어 갈까요?", "물이 필요해요."])]),
        ("fx-ja-ruby", "ja", (800, 900), 34, ["vertical", "furigana"], []),
        ("fx-empty", "ko", (800, 900), 30, ["blank_negative"], []),
    ]
    for sample_id, lang, size, font_size, tags, texts in configs:
        image = Image.new("RGB", size, "#aac5c4")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(str(font_path if lang == "ko" else jp_path), font_size)
        gold = []
        for index, (x, y, lines) in enumerate(texts):
            width = max(font.getlength(text) for text in lines)
            bubble = (x - 50, y - 70, x + width + 55, y + 180)
            dark = "dark_bubble" in tags
            fill = "#222222" if dark else "white"
            if "irregular" in tags:
                a, b, c, d = bubble
                draw.polygon([(a, b + 20), (a + 50, b), (c - 20, b + 5), (c, b + 70),
                              (c - 12, d - 15), (a + 60, d), (a, d - 50)],
                             fill=fill, outline="black", width=4)
            else:
                draw.rounded_rectangle(bubble, 55, fill=fill, outline="black", width=4)
            bounds = []
            for row, text in enumerate(lines):
                pos = (x, y + row * (font_size + 18))
                draw.text(pos, text, font=font, fill="white" if dark else "black")
                bounds.append(draw.textbbox(pos, text, font=font))
            box = [min(b[0] for b in bounds), min(b[1] for b in bounds),
                   max(b[2] for b in bounds), max(b[3] for b in bounds)]
            gold.append({"id": f"g{index}", "box": box, "text": " ".join(lines),
                         "role": "dialogue", "legible": True})
        if sample_id == "fx-ja-ruby":
            draw.ellipse((250, 80, 570, 730), fill="white", outline="black", width=4)
            text = "明日も学校へ行こう。"
            bounds = []
            for i, char in enumerate(text):
                draw.text((395, 160 + i * 43), char, font=font, fill="black")
                bounds.append(draw.textbbox((395, 160 + i * 43), char, font=font))
            ruby = ImageFont.truetype(str(jp_path), 15)
            for i, char in enumerate("がっこう"):
                draw.text((434, 288 + i * 16), char, font=ruby, fill="black")
                bounds.append(draw.textbbox((434, 288 + i * 16), char, font=ruby))
            box = [min(b[0] for b in bounds), min(b[1] for b in bounds),
                   max(b[2] for b in bounds), max(b[3] for b in bounds)]
            gold.append({"id": "g0", "box": box, "text": text,
                         "role": "dialogue", "legible": True,
                         "ruby_policy": "body excludes furigana; detection/erase includes it"})
        if sample_id == "fx-empty":
            draw.ellipse((100, 150, 700, 580), fill="white", outline="black", width=4)
        if "low_resolution" in tags:
            # Controlled degradation belongs to the same synthetic family, not a new real page.
            image = image.resize((400, 450), Image.Resampling.BILINEAR).resize(size)
        image.save(CORPUS / "images" / f"{sample_id}.png")
        add_record(records, sample_id, lang, "project-original-fixtures", "synthetic", tags,
                   "project-generated", "Comic Translation original test fixture",
                   None, transform={"generator": "quality-fixtures-v1", "font_size": font_size,
                                    "font_sha256": digest(font_path if lang == "ko" else jp_path)},
                   annotation=gold)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--pdftoppm", required=True)
    args = parser.parse_args()
    manifest = CORPUS / "manifest.json"
    if manifest.exists():
        raise ValueError("CORPUS_ALREADY_FROZEN: use a new version, never overwrite the baseline")
    (CORPUS / "images").mkdir(parents=True, exist_ok=True)
    (CORPUS / "sources").mkdir(exist_ok=True)
    pdf = ROOT / "artifacts/private/free-api-probe/volume-1.pdf"
    pdf_hash = digest(pdf)
    if pdf_hash != "a2ad133db82a21cefce1acccb5548de10d2d74118c1519d86ede8566b02ca8b4":
        raise ValueError("SOURCE_PDF_CHANGED")
    subprocess.run([args.pdftoppm, "-f", "4", "-l", "15", "-scale-to", "1400", "-png",
                    str(pdf), str(CORPUS / "sources/ja")], check=True, timeout=120)
    records = []
    for page in range(4, 16):
        sample_id = f"ja-bj-{page:03}"
        shutil.copyfile(CORPUS / "sources" / f"ja-{page:03}.png",
                        CORPUS / "images" / f"{sample_id}.png")
        add_record(records, sample_id, "ja", "blackjack-volume1", "japanese_original",
                   ["black_white", "real_page", "tags_pending_visual_review"],
                   "https://www.densho810.com/free/", "ブラックジャックによろしく / 佐藤秀峰",
                   "https://www.densho810.com/free/", pdf_hash,
                   {"pdf_file_page": page, "longest_edge": 1400})
    for episode in EPISODES:
        source_url = f"https://www.peppercarrot.com/kr/webcomic/{episode}.html"
        html_path = CORPUS / "sources" / f"{episode}.html"
        acquire(source_url, html_path, args.allow_download)
        html = html_path.read_text(encoding="utf-8")
        hd_links = re.findall(r'href=[\"\']([^\"\']+__hd\.html)[\"\']', html)
        if not hd_links:
            raise ValueError("HD_PAGE_LINK_MISSING")
        hd_url = urljoin(source_url, hd_links[0])
        hd_path = CORPUS / "sources" / f"{episode}-hd.html"
        acquire(hd_url, hd_path, args.allow_download)
        html = hd_path.read_text(encoding="utf-8")
        urls = sorted(set(re.findall(
            r'[\"\']([^\"\']*/hi-res/kr_[^\"\']+_E\d+P0[1-3]\.jpg)[\"\']', html)))
        if len(urls) != 3:
            raise ValueError(f"EXPECTED_THREE_KOREAN_PAGES: {episode}")
        for page, image_url in enumerate(urls, 1):
            sample_id = f"ko-pc-{episode[:4]}-{page}"
            image_url = urljoin(source_url, image_url)
            original = CORPUS / "sources" / f"{sample_id}.jpg"
            acquire(image_url, original, args.allow_download)
            with Image.open(original) as image:
                image = image.convert("RGB")
                original_size = image.size
                image.thumbnail((2400, 10000))
                image.save(CORPUS / "images" / f"{sample_id}.png")
            add_record(records, sample_id, "ko", "peppercarrot", "korean_translation",
                       ["color", "real_page", "tags_pending_visual_review"], source_url,
                       "Pepper&Carrot / David Revoy; Korean translation credits on source page",
                       "https://www.peppercarrot.com/en/about/index.html#license", digest(original),
                       {"image_url": image_url, "original_size": original_size, "max_width": 2400})
        print("Prepared:", episode, flush=True)
    fixtures(records)
    payload = {"version": "quality-v1", "status": "DEVELOPMENT_ONLY",
               "coordinate_system": "xyxy-original-image-pixels",
               "representativeness_gaps": ["Korean-origin manhwa not yet authorized",
                                           "real-page independent annotations pending"],
               "samples": records}
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Frozen:", len(records), "samples; manifest SHA256", digest(manifest))


if __name__ == "__main__":
    main()
