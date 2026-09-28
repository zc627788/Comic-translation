"""Download the credited CC BY Korean sample only with an explicit setup flag."""

import argparse
import hashlib
from urllib.request import urlopen

from PIL import Image

from services.worker.bubble_pipeline import OUTPUT

URL = ("https://www.peppercarrot.com/0_sources/ep01_Potion-of-Flight/hi-res/"
       "kr_Pepper-and-Carrot_by-David-Revoy_E01P01.jpg")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-download", action="store_true")
    args = parser.parse_args()
    source = OUTPUT / "ko-1-hd.jpg"
    if not source.is_file():
        if not args.allow_download:
            parser.error("Use --allow-download to obtain the credited CC BY sample.")
        OUTPUT.mkdir(parents=True, exist_ok=True)
        temporary = source.with_suffix(".partial")
        with urlopen(URL, timeout=60) as response:
            temporary.write_bytes(response.read(30_000_001))
        if temporary.stat().st_size > 30_000_000:
            raise ValueError("SAMPLE_TOO_LARGE")
        with Image.open(temporary) as image:
            image.verify()
        temporary.replace(source)
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((2400, 4000))
        image.save(OUTPUT / "ko-1-2400.png")
    print("Sample SHA256:", hashlib.sha256(source.read_bytes()).hexdigest())
    print("Pepper&Carrot / David Revoy, CC BY 4.0; Korean translation initbar et al.")


if __name__ == "__main__":
    main()
