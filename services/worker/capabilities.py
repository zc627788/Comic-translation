"""One source of truth for implemented processing capabilities."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Capability:
    name: str
    available: bool
    reason: str


def get_capabilities() -> list[dict[str, str | bool]]:
    return [
        asdict(Capability(name, False, "not_implemented"))
        for name in ("detection", "ocr", "translation", "inpainting", "typesetting")
    ]


def is_pipeline_ready() -> bool:
    return all(item["available"] for item in get_capabilities())
