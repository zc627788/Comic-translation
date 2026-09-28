"""Original Korean long-strip test artwork; contains no predefined Chinese outputs."""

from PIL import Image, ImageDraw, ImageFont

from services.worker.bubble_pipeline import OUTPUT


def main():
    image = Image.new("RGB", (800, 2900), "#e4e8ea")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 28)
    title = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 25)
    draw.text((40, 25), "原创韩文长条测试图 · 非真实商业韩漫", font=title, fill="#29404b")
    samples = [("안녕하세요!", "오늘 날씨가 좋아요."),
               ("같이 산책할까요?", "공원에서 만나요."),
               ("조금만 기다려 주세요.", "곧 도착해요!")]
    for index, lines in enumerate(samples):
        y = 150 + index * 900
        draw.rounded_rectangle((35, y, 765, y + 700), 22, fill="#b8d2d4")
        draw.ellipse((375, y + 80, 725, y + 330), fill="white", outline="#171e26", width=4)
        draw.polygon([(440, y + 299), (398, y + 382), (495, y + 314)], fill="white")
        draw.line([(440, y + 302), (398, y + 382), (495, y + 316)], fill="#171e26", width=4)
        for row, text in enumerate(lines):
            draw.text((550 - font.getlength(text) / 2, y + 163 + row * 44), text,
                      font=font, fill="#15191b")
        # Simple original character gives the detector a comic-style panel context.
        draw.ellipse((140, y + 350, 370, y + 560), fill="#ffdbb8", outline="#253c48", width=4)
        draw.ellipse((193, y + 428, 204, y + 443), fill="#253c48")
        draw.ellipse((301, y + 428, 312, y + 443), fill="#253c48")
        draw.arc((225, y + 459, 287, y + 495), 0, 180, fill="#253c48", width=4)
        draw.rectangle((192, y + 561, 325, y + 690), fill="#587e98")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT / "ko-longstrip.png")
    print("Original Korean fixture created locally.")


if __name__ == "__main__":
    main()
