"""Opt-in, bounded MyMemory probe. Not enabled in the production batch pipeline."""

import html
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

ENDPOINT = "https://api.mymemory.translated.net/get"
MAX_BYTES = 450


class TranslationError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward source text to an unexpected redirect destination.
        return None


def query_provider(text: str) -> dict:
    request = Request(
        ENDPOINT + "?" + urlencode({"q": text, "langpair": "ja|zh-CN"}),
        headers={"Accept": "application/json", "User-Agent": "ComicTranslation-P01-Probe/0.1"},
    )
    try:
        with build_opener(NoRedirects).open(request, timeout=15) as response:
            payload = response.read(100_001)
            if len(payload) > 100_000:
                raise TranslationError("INVALID_RESPONSE")
            return json.loads(payload)
    except HTTPError as exc:
        code = "QUOTA_EXCEEDED" if exc.code == 429 else "PROVIDER_HTTP_ERROR"
        raise TranslationError(code) from None
    except (URLError, TimeoutError, OSError):
        # Exception URLs can contain private text: expose only a stable code.
        raise TranslationError("NETWORK_ERROR") from None
    except (ValueError, UnicodeError):
        raise TranslationError("INVALID_RESPONSE") from None


@dataclass(frozen=True)
class Translation:
    provider: str
    source_language: str
    target_language: str
    text: str
    elapsed_ms: int
    source_characters: int
    warnings: list[str]
    retrieved_at: str

    def to_dict(self):
        return asdict(self)


class MyMemoryTranslator:
    """One serial experiment session, no retries, no paid fallback, no training writes."""

    def __init__(self, *, character_budget: int = 1000, transport=query_provider):
        if not 1 <= character_budget <= 1000:
            raise ValueError("Experiment budget must be between 1 and 1000")
        self.character_budget = character_budget
        self.attempted_characters = 0
        self.transport = transport

    def translate(self, text: str) -> Translation:
        if not text.strip():
            raise TranslationError("EMPTY_TEXT")
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise TranslationError("TEXT_TOO_LONG")
        if self.attempted_characters + len(text) > self.character_budget:
            raise TranslationError("LOCAL_BUDGET_EXCEEDED")
        self.attempted_characters += len(text)  # Failed calls may still consume quota.
        start = time.perf_counter()
        body = self.transport(text)
        if not isinstance(body, dict):
            raise TranslationError("INVALID_RESPONSE")
        if body.get("quotaFinished") is True or str(body.get("responseStatus")) == "429":
            raise TranslationError("QUOTA_EXCEEDED")
        if str(body.get("responseStatus")) != "200":
            raise TranslationError("PROVIDER_REJECTED")
        data = body.get("responseData")
        if not isinstance(data, dict) or not isinstance(data.get("translatedText"), str):
            raise TranslationError("INVALID_RESPONSE")
        translated = html.unescape(data["translatedText"]).strip()
        if not translated or len(translated) > 10_000:
            raise TranslationError("INVALID_RESPONSE")
        warnings = ["UNREVIEWED_FREE_TRANSLATION"]
        if translated == text.strip():
            warnings.append("UNCHANGED_TEXT")
        if any("\u3040" <= c <= "\u30ff" for c in translated):
            warnings.append("JAPANESE_REMAINS")
        if not any("\u3400" <= c <= "\u9fff" for c in translated):
            warnings.append("NO_CHINESE_CHARACTERS")
        return Translation(
            "mymemory-anonymous", "ja", "zh-CN", translated,
            round((time.perf_counter() - start) * 1000), len(text), warnings,
            datetime.now(UTC).isoformat(),
        )
