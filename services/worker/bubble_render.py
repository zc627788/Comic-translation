"""Local bubble erasure and typesetting; unsupported regions fail before modification."""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def largest_rectangle(mask):
    heights = np.zeros(mask.shape[1], dtype=int)
    best, rectangle = 0, None
    for y, row in enumerate(mask):
        heights = np.where(row, heights + 1, 0)
        stack = []
        for x in range(len(heights) + 1):
            current = int(heights[x]) if x < len(heights) else 0
            start = x
            while stack and stack[-1][1] > current:
                left, height = stack.pop()
                if (x - left) * height > best:
                    best = (x - left) * height
                    rectangle = (left, y - height + 1, x, y + 1)
                start = left
            if current and (not stack or stack[-1][1] < current):
                stack.append((start, current))
    return rectangle


def prepare_region(image, region):
    pixels = np.asarray(image)
    height, width = pixels.shape[:2]
    x0, y0, x1, y1 = region["box"]
    bx0, by0, bx1, by1 = region["bubble"]
    bounds = (max(0, bx0 - 12), max(0, by0 - 12), min(width, bx1 + 12), min(height, by1 + 12))
    left, top, right, bottom = bounds
    roi = pixels[top:bottom, left:right].copy()
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    tx0, ty0 = max(0, x0 - left - 3), max(0, y0 - top - 3)
    tx1, ty1 = min(right - left, x1 - left + 3), min(bottom - top, y1 - top + 3)
    text_mask = np.zeros(gray.shape, np.uint8)
    text_mask[ty0:ty1, tx0:tx1] = 255
    background = np.percentile(roi[ty0:ty1, tx0:tx1].reshape(-1, 3), 80, axis=0)
    if float(background.min()) < 150:
        raise ValueError("DARK_OR_COMPLEX_BUBBLE")
    plain = background.min() >= 235 and np.ptp(background) < 18
    if plain:
        # Erode the white background to close tiny antialias gaps in drawn bubble outlines.
        white = (roi.min(axis=2) > 232).astype(np.uint8)
        white = cv2.erode(white, np.ones((3, 3), np.uint8))
        _, labels = cv2.connectedComponents(white)
        counts = np.bincount(labels[ty0:ty1, tx0:tx1].ravel())
        counts[0] = 0
        if not counts.any():
            raise ValueError("NO_BUBBLE_INTERIOR")
        component = (labels == counts.argmax()).astype(np.uint8)
        touches_edge = (component[0].any() or component[-1].any()
                        or component[:, 0].any() or component[:, -1].any())
        if touches_edge:
            # A tail can leave the detector ROI. Restrict fallback to the contained
            # text rectangle, never fill the open background or whole bubble box.
            if min(x0 - bx0, y0 - by0, bx1 - x1, by1 - y1) < 4:
                raise ValueError("OPEN_BUBBLE_BOUNDARY")
            corners = [roi[y, x].min() for y in (ty0, ty1 - 1) for x in (tx0, tx1 - 1)]
            if min(corners) < 235:
                raise ValueError("OPEN_BUBBLE_BOUNDARY")
            safe = text_mask.copy()
            method = "white-text-interior"
        else:
            contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            safe = np.zeros(gray.shape, np.uint8)
            cv2.drawContours(safe, contours, -1, 255, cv2.FILLED)
            safe = cv2.erode(safe, np.ones((5, 5), np.uint8))
            method = "white-interior"
        ink = ((gray < 210) & (text_mask > 0)).astype(np.uint8) * 255
    else:
        # For pale translucent balloons, only touch their contained text rectangle.
        # Do not turn the detector's whole bounding box into a white fill.
        if min(x0 - bx0, y0 - by0, bx1 - x1, by1 - y1) < 4:
            raise ValueError("INSUFFICIENT_BUBBLE_MARGIN")
        safe = text_mask.copy()
        threshold = min(150, float(np.percentile(gray[ty0:ty1, tx0:tx1], 80)) * .65)
        ink = ((gray < threshold) & (text_mask > 0)).astype(np.uint8) * 255
        method = "colored-text-mask-telea"
    # Bubble outlines/art crossing the text-box edge are not text to erase.
    count, labels = cv2.connectedComponents(ink)
    rejected = set(np.unique(labels[ty0, tx0:tx1])) | set(np.unique(labels[ty1 - 1, tx0:tx1]))
    rejected |= set(np.unique(labels[ty0:ty1, tx0])) | set(np.unique(labels[ty0:ty1, tx1 - 1]))
    ink = np.isin(labels, [i for i in range(1, count) if i not in rejected])
    ink = ink.astype(np.uint8) * 255
    ink = cv2.dilate(ink, np.ones((3, 3), np.uint8))
    if (np.count_nonzero(ink & (255 - safe)) / max(1, np.count_nonzero(ink))) > .02:
        raise ValueError("TEXT_OUTSIDE_SAFE_ZONE")
    ink &= safe
    ratio = np.count_nonzero(ink) / max(1, np.count_nonzero(text_mask))
    if ratio < .005 or ratio > .5:
        raise ValueError("UNRELIABLE_TEXT_MASK")
    layout = largest_rectangle(cv2.erode(safe, np.ones((7, 7), np.uint8)) > 0)
    if not layout or layout[2] - layout[0] < 20 or layout[3] - layout[1] < 20:
        raise ValueError("NO_LAYOUT_SPACE")
    return {"bounds": bounds, "roi": roi, "safe": safe, "ink": ink,
            "layout": layout, "method": method, "background": background}


def fit_text(text, rectangle, font_path, max_font_size=32):
    x0, y0, x1, y1 = rectangle
    width, height = x1 - x0, y1 - y0
    minimum = max(12, max_font_size * 3 // 8)
    for size in range(min(max_font_size, max(14, width // 3)), minimum - 1, -1):
        font = ImageFont.truetype(str(font_path), size)
        lines, line = [], ""
        for char in text:
            if char == "\n" or (line and font.getlength(line + char) > width - 4):
                if char in "，。！？、；：）】》…,.!?;:)" and len(line) > 1:
                    lines.append(line[:-1])
                    line = line[-1]
                    line += char
                    continue
                lines.append(line)
                line = ""
            if char != "\n":
                line += char
        if line:
            lines.append(line)
        line_height = size + 4
        if (lines and len(lines) * line_height <= height - 4
                and max(font.getlength(line) for line in lines) <= width - 4):
            return font, lines, line_height
    raise ValueError("TEXT_DOES_NOT_FIT")


def render_region(image, prepared, text, font_path):
    if not Path(font_path).is_file():
        raise ValueError("FONT_NOT_FOUND")
    max_font_size = max(32, min(64, round(image.width / 1200 * 32)))
    font, lines, line_height = fit_text(text, prepared["layout"], font_path, max_font_size)
    roi, ink, safe = prepared["roi"], prepared["ink"], prepared["safe"]
    if prepared["method"].startswith("white-"):
        cleaned = roi.copy()
        cleaned[ink > 0] = np.rint(prepared["background"]).astype(np.uint8)
    else:
        cleaned = cv2.inpaint(roi, ink, 3, cv2.INPAINT_TELEA)
    layer = Image.new("RGBA", (roi.shape[1], roi.shape[0]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = prepared["layout"]
    start_y = y0 + (y1 - y0 - len(lines) * line_height) // 2
    for index, line in enumerate(lines):
        x = x0 + (x1 - x0 - font.getlength(line)) / 2
        draw.text((x, start_y + index * line_height), line, font=font,
                  fill=(25, 28, 27, 255), anchor="lt")
    rgba = np.asarray(layer)
    if np.any((rgba[:, :, 3] > 0) & (safe == 0)):
        raise ValueError("LAYOUT_OUTSIDE_SAFE_ZONE")
    painted = Image.alpha_composite(Image.fromarray(cleaned).convert("RGBA"), layer).convert("RGB")
    before, after = roi, np.asarray(painted)
    if np.any(np.any(before != after, axis=2) & (safe == 0)):
        raise ValueError("PIXEL_OUTSIDE_SAFE_ZONE")
    result = image.copy()
    result.paste(painted, prepared["bounds"][:2])
    return result, {"method": prepared["method"], "font_size": font.size,
                    "layout_local": list(prepared["layout"]),
                    "modified_pixels": int(np.count_nonzero(np.any(before != after, axis=2))),
                    "outside_safe_modified_pixels": 0}
