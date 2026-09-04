#!/usr/bin/env python3
"""Build the additional JLPT vocabulary bundle used by the static quiz.

The source revision is pinned so a rebuild does not silently change levels or
examples. English glosses and example translations are converted to Korean in
batches; the final JavaScript file is replaced only after every check passes.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "index.html"
OUTPUT_PATH = ROOT / "openjlpt-data.js"

OPENJLPT_COMMIT = "c42fd9fa3777bfc1775446f7c418d549dfd6e4cf"
OPENJLPT_ROOT = (
    "https://raw.githubusercontent.com/evanclan/OpenJLPT/"
    f"{OPENJLPT_COMMIT}/data/json/vocab"
)
LIBHANGUL_COMMIT = "a34aef73378c0992316861bbf13fc914ee7577d9"
LIBHANGUL_URL = (
    "https://raw.githubusercontent.com/libhangul/libhangul/"
    f"{LIBHANGUL_COMMIT}/data/hanja/hanja.txt"
)
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
MOBILE_TRANSLATE_URL = "https://translate.google.com/m"
TRANSLATION_CACHE = Path(tempfile.gettempdir()) / "jlpt-openjlpt-en-ko-v1.json"

EXPECTED_BASE_WORDS = 2954
MINIMUM_NEW_WORDS = 5000
LEVELS = (5, 4, 3, 2, 1)
EXPECTED_SOURCE_COUNTS = {5: 662, 4: 632, 3: 1784, 2: 1793, 1: 3463}
EXPECTED_NEW_COUNTS = {5: 250, 4: 271, 3: 1104, 2: 1489, 1: 2821}
EXPECTED_NEW_WORDS = sum(EXPECTED_NEW_COUNTS.values())

WORD_ENTRY_RE = re.compile(
    r'\{k:(?P<k>"(?:\\.|[^"\\])*")'
    r',r:(?P<r>"(?:\\.|[^"\\])*")'
    r',m:(?P<m>"(?:\\.|[^"\\])*")'
    r',l:(?P<l>[1-5])\}'
)
ALLOWED_WORD_RE = re.compile(
    r"^[\u3040-\u30ff\u3400-\u9fff々〆ヶヵー・A-Za-z0-9]+$"
)
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff々〆ヶヵー]")
KANA_RE = re.compile(r"^[\u3040-\u30ffー・]+$")
KANJI_RE = re.compile(r"[\u3400-\u9fff]")
TRAILING_HIRAGANA_RE = re.compile(r"[\u3040-\u309f]+$")
HANGUL_RE = re.compile(r"[가-힣]")
PREFER_MOBILE_TRANSLATE = False

# Small, reviewed corrections for glosses whose context-free machine
# translation is consistently misleading. Existing generated Korean text is
# reused first; the temporary cache only helps first-time generation.
MEANING_OVERRIDES = {
    "かかる": "걸리다, 들다",
    "こっち": "이쪽",
    "では": "그럼, 그러면",
    "掛ける": "걸다, 곱하다",
    "いずれ": "어느 것, 어느 쪽, 언젠가",
    "単に": "단순히",
    "用いる": "사용하다",
    "追い掛ける": "뒤쫓다",
    "一人でに": "저절로",
    "少数": "소수",
    "事項": "사항",
    "滲む": "번지다, 배어 나오다",
}
EXAMPLE_TRANSLATION_OVERRIDES = {
    "鼻": "코를 풀어 보세요.",
}


def request_bytes(url: str, *, data: bytes | None = None, timeout: int = 60) -> bytes:
    request = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "hchee99-jlpt-quiz-data-builder/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def download_json(url: str) -> Any:
    return json.loads(request_bytes(url).decode("utf-8"))


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    # The app renders examples as HTML so source angle brackets are made inert.
    return text.replace("&", "＆").replace("<", "＜").replace(">", "＞")


def parse_existing_index() -> tuple[list[dict[str, Any]], dict[str, str]]:
    source = INDEX_PATH.read_text(encoding="utf-8")
    words_marker = "const WORDS = ["
    words_start = source.find(words_marker)
    words_end = source.find("\n];", words_start)
    if words_start < 0 or words_end < 0:
        raise RuntimeError("index.html에서 WORDS 배열을 찾지 못했습니다.")
    words_block = source[words_start + len(words_marker) : words_end]
    words: list[dict[str, Any]] = []
    for match in WORD_ENTRY_RE.finditer(words_block):
        words.append(
            {
                "k": json.loads(match.group("k")),
                "r": json.loads(match.group("r")),
                "m": json.loads(match.group("m")),
                "l": int(match.group("l")),
            }
        )

    if len(words) != EXPECTED_BASE_WORDS:
        raise RuntimeError(
            f"기존 단어 파싱 수가 {len(words)}개입니다. "
            f"예상값 {EXPECTED_BASE_WORDS}개와 달라 생성하지 않습니다."
        )

    marker = "const KANJI_INFO = "
    start = source.find(marker)
    if start < 0:
        raise RuntimeError("index.html에서 KANJI_INFO를 찾지 못했습니다.")
    kanji_info, _ = json.JSONDecoder().raw_decode(source[start + len(marker) :])
    if not isinstance(kanji_info, dict):
        raise RuntimeError("KANJI_INFO 형식이 객체가 아닙니다.")
    return words, kanji_info


def extract_json_assignment(source: str, marker: str) -> Any:
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"생성 데이터 표식을 찾지 못했습니다: {marker}")
    value, _ = json.JSONDecoder().raw_decode(source[start + len(marker) :])
    return value


def load_previous_bundle() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    """Reuse committed Korean text so pinned-source rebuilds are deterministic."""
    if not OUTPUT_PATH.exists():
        return {}, {}
    try:
        source = OUTPUT_PATH.read_text(encoding="utf-8")
        meta = extract_json_assignment(source, "window.OPENJLPT_META = ")
        words = extract_json_assignment(source, "window.OPENJLPT_WORDS = ")
        examples = extract_json_assignment(source, "window.OPENJLPT_EXAMPLES = ")
        if meta.get("source_commit") != OPENJLPT_COMMIT:
            return {}, {}
        if not isinstance(words, list) or not isinstance(examples, dict):
            return {}, {}
        word_map = {
            word["k"]: word
            for word in words
            if isinstance(word, dict)
            and isinstance(word.get("k"), str)
            and isinstance(word.get("m"), str)
            and HANGUL_RE.search(word["m"])
        }
        return word_map, examples
    except (OSError, ValueError, AttributeError, json.JSONDecodeError):
        print("기존 생성 파일을 번역 기준으로 재사용할 수 없어 새로 번역합니다.")
        return {}, {}


def valid_word(word: str) -> bool:
    return (
        bool(word)
        and len(word) <= 12
        and bool(ALLOWED_WORD_RE.fullmatch(word))
        and bool(JAPANESE_RE.search(word))
        and not any(char in word for char in "/／~〜=()（）[]【】")
    )


def valid_reading(word: str, reading: str) -> bool:
    if not reading or not ALLOWED_WORD_RE.fullmatch(reading):
        return False
    if KANJI_RE.search(word):
        return bool(KANA_RE.fullmatch(reading))
    return bool(JAPANESE_RE.search(reading))


def example_stems(word: str) -> list[str]:
    stems = [word]
    if word.endswith("する") and len(word) > 2:
        stems.append(word[:-2])
    if KANJI_RE.search(word):
        stem = TRAILING_HIRAGANA_RE.sub("", word)
        if len(stem) >= 2:
            stems.append(stem)
    elif len(word) >= 4 and word[-1] in "いるうくぐすつぬぶむ":
        stems.append(word[:-1])
    return list(dict.fromkeys(stems))


def contains_term(japanese: str, term: str) -> bool:
    """Reject obvious substring matches inside a larger kanji compound."""
    start = japanese.find(term)
    while start >= 0:
        end = start + len(term)
        left = japanese[start - 1] if start else ""
        right = japanese[end] if end < len(japanese) else ""
        left_is_bad = bool(KANJI_RE.fullmatch(term[0]) and KANJI_RE.fullmatch(left))
        right_is_bad = bool(KANJI_RE.fullmatch(term[-1]) and KANJI_RE.fullmatch(right))
        if not left_is_bad and not right_is_bad:
            return True
        start = japanese.find(term, start + 1)
    return False


def select_example(item: dict[str, Any], word: str) -> tuple[str, str] | None:
    stems = example_stems(word)
    for example in item.get("examples") or []:
        japanese = clean_text(example.get("ja"))
        english = clean_text(example.get("en"))
        if not japanese or not english:
            continue
        if any(stem and contains_term(japanese, stem) for stem in stems):
            return japanese, english
    return None


def english_gloss(item: dict[str, Any]) -> str:
    meanings: list[str] = []
    for raw in item.get("meanings") or []:
        meaning = clean_text(raw).strip(" ;")
        if meaning and meaning not in meanings:
            meanings.append(meaning)
        if len(meanings) == 2:
            break
    return "; ".join(meanings)


def load_translation_cache() -> dict[str, str]:
    if not TRANSLATION_CACHE.exists():
        return {}
    try:
        loaded = json.loads(TRANSLATION_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in loaded.items()
        if key and isinstance(value, str) and value.strip()
    }


def save_translation_cache(cache: dict[str, str]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=TRANSLATION_CACHE.parent,
            prefix=f"{TRANSLATION_CACHE.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(cache, temporary, ensure_ascii=False, sort_keys=True)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, TRANSLATION_CACHE)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


class TranslationShapeError(RuntimeError):
    """Raised when a batch translation does not preserve item boundaries."""


def split_translation(translated: str, expected: int) -> list[str]:
    results = [line.strip() for line in translated.split("\n")]
    if len(results) != expected or any(not line for line in results):
        raise TranslationShapeError(
            f"번역 응답 줄 수가 다릅니다: 요청 {expected}, 응답 {len(results)}"
        )
    return results


def translate_mobile_batch(lines: list[str], source_language: str) -> list[str]:
    query = urllib.parse.urlencode(
        {"sl": source_language, "tl": "ko", "q": "\n".join(lines)}
    )
    page = request_bytes(f"{MOBILE_TRANSLATE_URL}?{query}").decode("utf-8")
    match = re.search(
        r'<div class="result-container">(.*?)</div>', page, flags=re.DOTALL
    )
    if not match:
        raise RuntimeError("모바일 번역 응답에서 결과 영역을 찾지 못했습니다.")
    translated = re.sub(r"<br\s*/?>", "\n", match.group(1), flags=re.IGNORECASE)
    translated = html.unescape(re.sub(r"<[^>]+>", "", translated))
    return split_translation(translated, len(lines))


def translate_batch(lines: list[str], source_language: str) -> list[str]:
    global PREFER_MOBILE_TRANSLATE
    if PREFER_MOBILE_TRANSLATE:
        return translate_mobile_batch(lines, source_language)

    payload = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": source_language,
            "tl": "ko",
            "dt": "t",
            "q": "\n".join(lines),
        }
    ).encode("utf-8")
    try:
        raw_response = request_bytes(TRANSLATE_URL, data=payload)
    except urllib.error.HTTPError as error:
        if error.code != 429:
            raise
        PREFER_MOBILE_TRANSLATE = True
        print("  기본 번역 API 제한 감지: 모바일 번역 경로로 전환")
        return translate_mobile_batch(lines, source_language)

    response = json.loads(raw_response.decode("utf-8"))
    translated = "".join(
        part[0] for part in (response[0] or []) if part and part[0] is not None
    )
    return split_translation(translated, len(lines))


def translate_resilient_batch(lines: list[str], source_language: str) -> list[str]:
    try:
        return translate_batch(lines, source_language)
    except (TranslationShapeError, urllib.error.HTTPError) as error:
        can_split = isinstance(error, TranslationShapeError) or error.code == 414
        if not can_split or len(lines) == 1:
            raise
        midpoint = len(lines) // 2
        return translate_resilient_batch(
            lines[:midpoint], source_language
        ) + translate_resilient_batch(lines[midpoint:], source_language)


def make_batches(lines: list[str], *, max_items: int = 40, max_chars: int = 1600):
    batch: list[str] = []
    size = 0
    for line in lines:
        extra = len(line) + (1 if batch else 0)
        if batch and (len(batch) >= max_items or size + extra > max_chars):
            yield batch
            batch = []
            size = 0
        batch.append(line)
        size += extra
    if batch:
        yield batch


def translate_texts(
    texts: list[str], *, source_language: str, use_cache: bool
) -> dict[str, str]:
    unique = list(dict.fromkeys(texts))
    cache = load_translation_cache() if use_cache else {}
    cache_key = lambda text: text if source_language == "en" else f"{source_language}\0{text}"
    missing = [text for text in unique if cache_key(text) not in cache]
    batches = list(make_batches(missing))
    print(
        f"{source_language}→ko 번역 대상 {len(unique):,}개 "
        f"(캐시 {len(unique) - len(missing):,}개, 신규 {len(missing):,}개)"
    )

    for index, batch in enumerate(batches, start=1):
        last_error: Exception | None = None
        for attempt in range(1, 5):
            try:
                results = translate_resilient_batch(batch, source_language)
                cache.update(
                    (cache_key(text), result)
                    for text, result in zip(batch, results, strict=True)
                )
                last_error = None
                break
            except (OSError, ValueError, RuntimeError, urllib.error.URLError) as error:
                last_error = error
                if attempt < 4:
                    wait_seconds = 30 * attempt if getattr(error, "code", None) == 429 else attempt * 2
                    time.sleep(wait_seconds)
        if last_error is not None:
            if use_cache:
                save_translation_cache(cache)
            raise RuntimeError(
                f"번역 배치 {index}/{len(batches)} 실패: {last_error}"
            ) from last_error
        if index % 10 == 0 or index == len(batches):
            print(f"  번역 {index}/{len(batches)} 배치 완료")
            if use_cache:
                save_translation_cache(cache)
        time.sleep(0.25)

    if missing and len(batches) == 0:
        raise RuntimeError("번역할 텍스트가 있지만 배치가 생성되지 않았습니다.")
    return {text: cache[cache_key(text)] for text in unique}


def require_korean_translation(text: str) -> str:
    cleaned = clean_text(text).replace("\u200b", "")
    if not HANGUL_RE.search(cleaned):
        raise RuntimeError(f"한국어가 아닌 번역 응답: {cleaned!r}")
    return cleaned


def normalize_korean_meaning(text: str) -> str:
    cleaned = require_korean_translation(text)
    parts: list[str] = []
    for part in re.split(r"[;；]", cleaned):
        part = part.strip(" ,")
        if part and part not in parts:
            parts.append(part)
    return ", ".join(parts)


def collect_hanja_info(
    words: list[dict[str, Any]], existing_info: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    raw = request_bytes(LIBHANGUL_URL).decode("utf-8")
    direct: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        _, hanja, explanation = parts
        explanation = explanation.split(",", 1)[0].strip()
        if len(hanja) == 1 and explanation and HANGUL_RE.search(explanation):
            direct.setdefault(hanja, explanation)

    required = sorted({char for word in words for char in word["k"] if KANJI_RE.fullmatch(char)})
    additions = {
        char: direct[char]
        for char in required
        if char not in existing_info and char in direct
    }
    uncovered = [
        char for char in required if char not in existing_info and char not in additions
    ]
    return additions, uncovered


def render_bundle(
    words: list[dict[str, Any]],
    examples: dict[str, dict[str, str]],
    kanji_info: dict[str, str],
    meta: dict[str, Any],
) -> str:
    word_lines = [
        "  " + json.dumps(word, ensure_ascii=False, separators=(",", ":"))
        for word in words
    ]
    example_lines = [
        "  "
        + json.dumps(key, ensure_ascii=False)
        + ":"
        + json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        for key, value in examples.items()
    ]
    return "\n".join(
        [
            "/*",
            " * Generated by scripts/build_openjlpt_data.py.",
            " * Derived vocabulary data: OpenJLPT, CC BY-SA 4.0.",
            " * See DATA-NOTICE.md for complete attribution and modification notes.",
            " */",
            "window.OPENJLPT_META = "
            + json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
            + ";",
            "window.OPENJLPT_WORDS = [",
            ",\n".join(word_lines),
            "];",
            "window.OPENJLPT_EXAMPLES = {",
            ",\n".join(example_lines),
            "};",
            "window.OPENJLPT_KANJI_INFO = "
            + json.dumps(
                kanji_info, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + ";",
            "",
        ]
    )


def validate_bundle_before_write(
    words: list[dict[str, Any]],
    examples: dict[str, dict[str, str]],
    kanji_info: dict[str, str],
    meta: dict[str, Any],
    existing_words: list[dict[str, Any]],
    existing_kanji: dict[str, str],
) -> None:
    errors: list[str] = []
    existing_keys = {word["k"] for word in existing_words}
    keys = [word.get("k") for word in words]
    if len(words) != EXPECTED_NEW_WORDS or len(set(keys)) != len(words):
        errors.append("신규 단어 수 또는 고유 표기 수가 예상값과 다릅니다.")
    if existing_keys & set(keys):
        errors.append("신규 단어가 기존 표기와 중복됩니다.")
    if len(examples) != len(words):
        errors.append("신규 단어와 예문 수가 다릅니다.")

    for word in words:
        key = word.get("k")
        if not all(isinstance(word.get(field), str) and word[field] for field in ("k", "r", "m")):
            errors.append(f"필수 문자열 필드 누락: {key!r}")
            continue
        if word.get("l") not in LEVELS or not valid_word(key) or not valid_reading(key, word["r"]):
            errors.append(f"표기·읽기·레벨 오류: {key}")
        if not HANGUL_RE.search(word["m"]):
            errors.append(f"한국어 뜻 누락: {key}")
        if "관련 표현" in word["m"] or "문장의 한국어 번역:" in word["m"]:
            errors.append(f"번역 실패 대체 문구가 뜻에 포함됨: {key}")
        example = examples.get(key)
        if not isinstance(example, dict) or not all(
            isinstance(example.get(field), str) and example[field] for field in ("j", "k")
        ):
            errors.append(f"예문 필드 누락: {key}")
            continue
        if not HANGUL_RE.search(example["k"]):
            errors.append(f"한국어 예문 번역 누락: {key}")
        if "문장의 한국어 번역:" in example["k"]:
            errors.append(f"번역 실패 대체 문구가 예문에 포함됨: {key}")
        if not any(contains_term(example["j"], stem) for stem in example_stems(key)):
            errors.append(f"예문에 표기 또는 안전한 어간이 없음: {key}")

    level_counts = Counter(word["l"] for word in words)
    expected_level_meta = {f"N{level}": level_counts[level] for level in LEVELS}
    fallback_count = sum(
        examples[word["k"]]["j"] == f"「{word['k']}」という言葉を覚えました。"
        for word in words
        if word["k"] in examples
    )
    required_kanji = {
        char for word in words for char in word["k"] if KANJI_RE.fullmatch(char)
    }
    all_kanji = set(existing_kanji) | set(kanji_info)
    uncovered_count = len(required_kanji - all_kanji)
    expected_meta = {
        "source": "OpenJLPT",
        "license": "CC BY-SA 4.0",
        "source_commit": OPENJLPT_COMMIT,
        "generated_count": len(words),
        "level_counts": expected_level_meta,
        "fallback_example_count": fallback_count,
        "additional_kanji_info_count": len(kanji_info),
        "uncovered_kanji_count": uncovered_count,
    }
    if meta != expected_meta:
        errors.append("생성 메타데이터가 실제 데이터와 다릅니다.")
    if required_kanji and len(required_kanji & all_kanji) / len(required_kanji) < 0.90:
        errors.append("신규 한자 훈음 수록률이 90% 미만입니다.")

    if errors:
        details = "\n- ".join(errors[:30])
        raise RuntimeError(f"출력 전 데이터 검증 실패:\n- {details}")


def build(*, use_cache: bool) -> None:
    existing_words, existing_kanji = parse_existing_index()
    previous_words, previous_examples = load_previous_bundle()
    seen = {word["k"] for word in existing_words}
    candidates: list[dict[str, Any]] = []
    rejected = Counter()
    source_counts = Counter()

    for level in LEVELS:
        source = download_json(f"{OPENJLPT_ROOT}/n{level}.json")
        source_counts[level] = len(source)
        if source_counts[level] != EXPECTED_SOURCE_COUNTS[level]:
            raise RuntimeError(
                f"N{level} 원본 수가 {source_counts[level]:,}개입니다. "
                f"예상값 {EXPECTED_SOURCE_COUNTS[level]:,}개와 달라 생성하지 않습니다."
            )
        for item in source:
            word = clean_text(item.get("word"))
            source_level = str(item.get("level", "")).upper()
            if source_level != f"N{level}":
                rejected["level_mismatch"] += 1
                continue
            if not valid_word(word):
                rejected["invalid_word"] += 1
                continue
            if word in seen:
                rejected["duplicate"] += 1
                continue

            reading = clean_text(item.get("reading"))
            if not reading:
                reading = word if not KANJI_RE.search(word) else ""
            if not valid_reading(word, reading):
                rejected["invalid_reading"] += 1
                continue

            meaning_en = english_gloss(item)
            if not meaning_en:
                rejected["missing_meaning"] += 1
                continue

            example = select_example(item, word)
            candidate = {
                "k": word,
                "r": reading,
                "l": level,
                "meaning_en": meaning_en,
                "example_ja": example[0] if example else f"「{word}」という言葉を覚えました。",
                "example_en": example[1] if example else "",
                "fallback": example is None,
            }
            candidates.append(candidate)
            seen.add(word)

    candidate_counts = Counter(candidate["l"] for candidate in candidates)
    if len(candidates) < MINIMUM_NEW_WORDS or len(candidates) != EXPECTED_NEW_WORDS:
        raise RuntimeError(
            f"신규 단어가 {len(candidates):,}개입니다. "
            f"예상값 {EXPECTED_NEW_WORDS:,}개와 달라 생성하지 않습니다."
        )
    for level in LEVELS:
        if candidate_counts[level] != EXPECTED_NEW_COUNTS[level]:
            raise RuntimeError(
                f"N{level} 신규 단어가 {candidate_counts[level]:,}개입니다. "
                f"예상값 {EXPECTED_NEW_COUNTS[level]:,}개와 다릅니다."
            )

    translation_inputs: list[str] = []
    for candidate in candidates:
        previous_word = previous_words.get(candidate["k"])
        candidate["previous_meaning"] = (
            previous_word["m"]
            if previous_word
            and previous_word.get("r") == candidate["r"]
            and previous_word.get("l") == candidate["l"]
            else ""
        )
        previous_example = previous_examples.get(candidate["k"])
        candidate["previous_example_ko"] = (
            previous_example.get("k", "")
            if isinstance(previous_example, dict)
            and previous_example.get("j") == candidate["example_ja"]
            and HANGUL_RE.search(str(previous_example.get("k", "")))
            else ""
        )
        if candidate["k"] not in MEANING_OVERRIDES and not candidate["previous_meaning"]:
            translation_inputs.append(candidate["meaning_en"])
        if (
            not candidate["fallback"]
            and candidate["k"] not in EXAMPLE_TRANSLATION_OVERRIDES
            and not candidate["previous_example_ko"]
        ):
            translation_inputs.append(candidate["example_en"])
    translations = translate_texts(
        translation_inputs, source_language="en", use_cache=use_cache
    )
    words: list[dict[str, Any]] = []
    examples: dict[str, dict[str, str]] = {}
    for candidate in candidates:
        korean_meaning = MEANING_OVERRIDES.get(candidate["k"])
        if not korean_meaning:
            korean_meaning = candidate["previous_meaning"] or normalize_korean_meaning(
                translations[candidate["meaning_en"]]
            )
        if candidate["fallback"]:
            korean_example = f"「{candidate['k']}」라는 단어를 외웠습니다."
        else:
            korean_example = EXAMPLE_TRANSLATION_OVERRIDES.get(candidate["k"])
            if not korean_example:
                korean_example = candidate[
                    "previous_example_ko"
                ] or require_korean_translation(
                    translations[candidate["example_en"]]
                )
        words.append(
            {
                "k": candidate["k"],
                "r": candidate["r"],
                "m": korean_meaning,
                "l": candidate["l"],
            }
        )
        examples[candidate["k"]] = {
            "j": candidate["example_ja"],
            "k": korean_example,
        }

    kanji_info, uncovered_kanji = collect_hanja_info(words, existing_kanji)
    level_counts = Counter(word["l"] for word in words)
    fallback_count = sum(candidate["fallback"] for candidate in candidates)
    meta = {
        "source": "OpenJLPT",
        "license": "CC BY-SA 4.0",
        "source_commit": OPENJLPT_COMMIT,
        "generated_count": len(words),
        "level_counts": {f"N{level}": level_counts[level] for level in LEVELS},
        "fallback_example_count": fallback_count,
        "additional_kanji_info_count": len(kanji_info),
        "uncovered_kanji_count": len(uncovered_kanji),
    }

    validate_bundle_before_write(
        words, examples, kanji_info, meta, existing_words, existing_kanji
    )
    bundle = render_bundle(words, examples, kanji_info, meta)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=OUTPUT_PATH.parent,
            prefix=f"{OUTPUT_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(bundle)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, OUTPUT_PATH)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()

    print(f"기존 단어: {len(existing_words):,}개")
    print(f"신규 단어: {len(words):,}개")
    print(f"전체 단어: {len(existing_words) + len(words):,}개")
    print(
        "레벨별 신규: "
        + ", ".join(f"N{level} {level_counts[level]:,}" for level in LEVELS)
    )
    print(f"원본 예문: {len(words) - fallback_count:,}개")
    print(f"대체 예문: {fallback_count:,}개")
    print(f"추가 한자 훈음: {len(kanji_info):,}자")
    print(f"훈음 미수록 한자: {len(uncovered_kanji):,}자")
    if uncovered_kanji:
        # Some rare CJK characters cannot be encoded by a Windows CP949 console.
        print("  미수록 코드: " + " ".join(f"U+{ord(char):04X}" for char in uncovered_kanji))
    print("제외 내역: " + ", ".join(f"{key} {value:,}" for key, value in rejected.items()))
    print(
        "원본 내역: "
        + ", ".join(f"N{level} {source_counts[level]:,}" for level in LEVELS)
    )
    print(f"생성 완료: {OUTPUT_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="임시 폴더의 영→한 번역 캐시를 사용하지 않습니다.",
    )
    args = parser.parse_args()
    build(use_cache=not args.no_cache)


if __name__ == "__main__":
    main()
