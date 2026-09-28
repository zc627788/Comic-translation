"""Print truthful readiness information without loading or downloading models."""

import argparse
import json

from services.worker.capabilities import get_capabilities, is_pipeline_ready


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the local model worker foundation")
    parser.add_argument(
        "--check-ready", action="store_true", help="Fail if inference is unavailable"
    )
    arguments = parser.parse_args()
    ready = is_pipeline_ready()
    print(json.dumps({"ready": ready, "capabilities": get_capabilities()}, ensure_ascii=False))
    return 1 if arguments.check_ready and not ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
