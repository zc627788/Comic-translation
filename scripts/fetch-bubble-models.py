"""Explicit setup download. Runtime never downloads models or executes remote Python."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    registry = json.loads((ROOT / "models/bubble-lab.json").read_text(encoding="utf-8"))
    for item in registry["files"]:
        path = ROOT / "models/weights" / item["path"]
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]:
            print("Verified:", item["path"])
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        with urlopen(item["url"], timeout=90) as response, temporary.open("wb") as out:
            while block := response.read(1024 * 1024):
                out.write(block)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("MODEL_HASH_MISMATCH: incomplete file retained as .partial")
        temporary.replace(path)
        print("Downloaded and verified:", item["path"])


if __name__ == "__main__":
    main()
