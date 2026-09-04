#!/usr/bin/env python3
"""Validate the complete vocabulary bundle and the browser merge hooks."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "index.html"
DATA_PATH = ROOT / "openjlpt-data.js"

EXPECTED_BASE_WORDS = 2954
MINIMUM_NEW_WORDS = 5000
EXPECTED_NEW_COUNTS = {5: 250, 4: 271, 3: 1104, 2: 1489, 1: 2821}
EXPECTED_NEW_WORDS = sum(EXPECTED_NEW_COUNTS.values())
OPENJLPT_COMMIT = "c42fd9fa3777bfc1775446f7c418d549dfd6e4cf"
ALLOWED_WORD_RE = re.compile(
    r"^[\u3040-\u30ff\u3400-\u9fff々〆ヶヵー・A-Za-z0-9]+$"
)
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff々〆ヶヵー]")
KANA_RE = re.compile(r"^[\u3040-\u30ffー・]+$")
KANJI_RE = re.compile(r"[\u3400-\u9fff]")
TRAILING_HIRAGANA_RE = re.compile(r"[\u3040-\u309f]+$")
HANGUL_RE = re.compile(r"[가-힣]")
WORD_ENTRY_RE = re.compile(
    r'\{k:(?P<k>"(?:\\.|[^"\\])*")'
    r',r:(?P<r>"(?:\\.|[^"\\])*")'
    r',m:(?P<m>"(?:\\.|[^"\\])*")'
    r',l:(?P<l>[1-5])\}'
)
EXAMPLE_ENTRY_RE = re.compile(
    r'(?P<word>"(?:\\.|[^"\\])*"):\{'
    r'j:(?P<j>"(?:\\.|[^"\\])*"),'
    r'k:(?P<k>"(?:\\.|[^"\\])*")\}'
)


def extract_json(source: str, marker: str) -> Any:
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"데이터 표식을 찾지 못했습니다: {marker}")
    value, _ = json.JSONDecoder().raw_decode(source[start + len(marker) :])
    return value


def parse_base_words(source: str) -> list[dict[str, Any]]:
    marker = "const WORDS = ["
    start = source.find(marker)
    end = source.find("\n];", start)
    if start < 0 or end < 0:
        raise ValueError("기존 WORDS 배열을 찾지 못했습니다.")
    block = source[start + len(marker) : end]
    words: list[dict[str, Any]] = []
    for match in WORD_ENTRY_RE.finditer(block):
        words.append(
            {
                "k": json.loads(match.group("k")),
                "r": json.loads(match.group("r")),
                "m": json.loads(match.group("m")),
                "l": int(match.group("l")),
            }
        )
    return words


def parse_base_examples(source: str) -> dict[str, dict[str, str]]:
    marker = "const EXAMPLES = "
    start = source.find(marker)
    end = source.find("\n};", start)
    if start < 0 or end < 0:
        raise ValueError("기존 EXAMPLES 블록을 찾지 못했습니다.")
    block = source[start + len(marker) : end]
    examples: dict[str, dict[str, str]] = {}
    for match in EXAMPLE_ENTRY_RE.finditer(block):
        examples[json.loads(match.group("word"))] = {
            "j": json.loads(match.group("j")),
            "k": json.loads(match.group("k")),
        }
    return examples


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


def meaning_parts(meaning: str) -> set[str]:
    return {
        re.sub(r"\(.*?\)", "", part).replace(" ", "")
        for part in meaning.split(",")
        if part.strip()
    }


def valid_reading(word: str, reading: str) -> bool:
    if not ALLOWED_WORD_RE.fullmatch(reading):
        return False
    if KANJI_RE.search(word):
        return bool(KANA_RE.fullmatch(reading))
    return bool(JAPANESE_RE.search(reading))


def validate() -> int:
    errors: list[str] = []
    try:
        index = INDEX_PATH.read_text(encoding="utf-8")
        data = DATA_PATH.read_text(encoding="utf-8")
        base_words = parse_base_words(index)
        base_examples = parse_base_examples(index)
        base_kanji = extract_json(index, "const KANJI_INFO = ")
        extra_words = extract_json(data, "window.OPENJLPT_WORDS = ")
        extra_examples = extract_json(data, "window.OPENJLPT_EXAMPLES = ")
        extra_kanji = extract_json(data, "window.OPENJLPT_KANJI_INFO = ")
        meta = extract_json(data, "window.OPENJLPT_META = ")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"검증 실패: 데이터 파일을 읽거나 해석할 수 없습니다: {error}", file=sys.stderr)
        return 1

    expected_containers = (
        ("기존 단어", base_words, list),
        ("기존 예문", base_examples, dict),
        ("기존 한자", base_kanji, dict),
        ("신규 단어", extra_words, list),
        ("신규 예문", extra_examples, dict),
        ("신규 한자", extra_kanji, dict),
        ("메타데이터", meta, dict),
    )
    for label, value, expected_type in expected_containers:
        if not isinstance(value, expected_type):
            errors.append(f"{label} 최상위 형식이 {expected_type.__name__}이 아닙니다.")
    if isinstance(extra_words, list) and any(not isinstance(word, dict) for word in extra_words):
        errors.append("신규 단어 배열에 객체가 아닌 항목이 있습니다.")
    if isinstance(extra_examples, dict) and any(
        not isinstance(example, dict) for example in extra_examples.values()
    ):
        errors.append("신규 예문 객체에 잘못된 값 형식이 있습니다.")
    if isinstance(extra_kanji, dict) and any(
        not isinstance(character, str) or not isinstance(explanation, str)
        for character, explanation in extra_kanji.items()
    ):
        errors.append("신규 한자 훈음 객체에 잘못된 키 또는 값 형식이 있습니다.")
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    if len(base_words) != EXPECTED_BASE_WORDS:
        errors.append(
            f"기존 단어 수: 예상 {EXPECTED_BASE_WORDS}, 실제 {len(base_words)}"
        )
    if len(extra_words) < MINIMUM_NEW_WORDS or len(extra_words) != EXPECTED_NEW_WORDS:
        errors.append(
            f"신규 단어 수: 예상 {EXPECTED_NEW_WORDS}, 실제 {len(extra_words)}"
        )

    all_words = base_words + extra_words
    all_examples = {**extra_examples, **base_examples}
    all_kanji = {**extra_kanji, **base_kanji}
    key_counts = Counter(word.get("k") for word in all_words)
    duplicates = [key for key, count in key_counts.items() if count > 1]
    if duplicates:
        errors.append(f"중복 표기 {len(duplicates)}개: {', '.join(duplicates[:10])}")

    for number, word in enumerate(all_words, start=1):
        missing = [field for field in ("k", "r", "m", "l") if not word.get(field)]
        if missing:
            errors.append(f"단어 #{number} 필수 필드 누락: {missing}")
            continue
        if not all(isinstance(word[field], str) for field in ("k", "r", "m")):
            errors.append(f"단어 #{number} 문자열 필드 형식 오류")
            continue
        if word["l"] not in {1, 2, 3, 4, 5}:
            errors.append(f"{word['k']}: 잘못된 레벨 {word['l']}")

    for word in extra_words:
        key = word["k"]
        if (
            not ALLOWED_WORD_RE.fullmatch(key)
            or not JAPANESE_RE.search(key)
            or len(key) > 12
        ):
            errors.append(f"{key}: 허용되지 않는 신규 표기")
        if not valid_reading(key, word["r"]):
            errors.append(f"{key}: 허용되지 않는 읽기 {word['r']}")
        if not HANGUL_RE.search(word["m"]):
            errors.append(f"{key}: 한국어 뜻이 확인되지 않음 ({word['m']})")
        if "관련 표현" in word["m"] or "문장의 한국어 번역:" in word["m"]:
            errors.append(f"{key}: 번역 실패를 감추는 대체 문구가 뜻에 포함됨")

        example = all_examples.get(key)
        if (
            not isinstance(example, dict)
            or not isinstance(example.get("j"), str)
            or not isinstance(example.get("k"), str)
            or not example.get("j")
            or not example.get("k")
        ):
            errors.append(f"{key}: 예문 또는 번역 누락")
            continue
        if not HANGUL_RE.search(example["k"]):
            errors.append(f"{key}: 한국어 예문 번역이 확인되지 않음")
        if "문장의 한국어 번역:" in example["k"]:
            errors.append(f"{key}: 번역 실패를 감추는 대체 문구가 예문에 포함됨")
        if not any(contains_term(example["j"], stem) for stem in example_stems(key)):
            errors.append(f"{key}: 예문에 표기나 활용 어간이 없음 ({example['j']})")

    missing_examples = [word["k"] for word in all_words if word["k"] not in all_examples]
    if missing_examples:
        errors.append(
            f"전체 예문 누락 {len(missing_examples)}개: {', '.join(missing_examples[:10])}"
        )

    # The app only asks reading questions for kanji words whose reading differs
    # from their display form. Verify that every such answer has three distinct
    # alternatives; meaning questions are checked with the app's overlap rule.
    reading_candidates = {
        word["r"]
        for word in all_words
        if KANJI_RE.search(word["k"]) and word["r"] != word["k"]
    }
    for word in all_words:
        if KANJI_RE.search(word["k"]) and word["r"] != word["k"]:
            if len(reading_candidates - {word["r"]}) < 3:
                errors.append(f"{word['k']}: 읽기 객관식 오답이 3개 미만")

    unique_meanings: dict[str, set[str]] = {}
    for word in all_words:
        unique_meanings.setdefault(word["m"], meaning_parts(word["m"]))
    for word in all_words:
        answer = word["m"]
        parts = meaning_parts(answer)
        alternatives = 0
        for candidate, candidate_parts in unique_meanings.items():
            if candidate != answer and not (parts & candidate_parts):
                alternatives += 1
                if alternatives == 3:
                    break
        if alternatives < 3:
            errors.append(f"{word['k']}: 뜻 객관식 오답이 3개 미만")

    required_kanji = {
        char
        for word in extra_words
        for char in word["k"]
        if KANJI_RE.fullmatch(char)
    }
    covered_kanji = required_kanji & set(all_kanji)
    coverage = len(covered_kanji) / len(required_kanji) if required_kanji else 1.0
    if coverage < 0.90:
        errors.append(f"신규 한자 훈음 수록률이 낮습니다: {coverage:.1%}")

    extra_level_counts = Counter(word["l"] for word in extra_words)
    for level, expected_count in EXPECTED_NEW_COUNTS.items():
        if extra_level_counts[level] != expected_count:
            errors.append(
                f"N{level} 신규 단어 수: 예상 {expected_count}, 실제 {extra_level_counts[level]}"
            )
    fallback_count = sum(
        extra_examples.get(word["k"], {}).get("j")
        == f"「{word['k']}」という言葉を覚えました。"
        for word in extra_words
    )
    expected_meta = {
        "source": "OpenJLPT",
        "license": "CC BY-SA 4.0",
        "source_commit": OPENJLPT_COMMIT,
        "generated_count": len(extra_words),
        "level_counts": {
            f"N{level}": extra_level_counts[level] for level in (5, 4, 3, 2, 1)
        },
        "fallback_example_count": fallback_count,
        "additional_kanji_info_count": len(extra_kanji),
        "uncovered_kanji_count": len(required_kanji - set(all_kanji)),
    }
    if meta != expected_meta:
        errors.append("OPENJLPT_META 전체 값이 실제 생성 데이터와 다릅니다.")

    script_position = index.find('<script src="./openjlpt-data.js"></script>')
    inline_position = index.find("<script>", script_position + 1)
    if script_position < 0 or inline_position < script_position:
        errors.append("openjlpt-data.js가 인라인 앱 스크립트보다 먼저 로드되지 않습니다.")
    required_hooks = (
        "const OPENJLPT_BUNDLE_VALID =",
        "window.OPENJLPT_META?.generated_count === window.OPENJLPT_WORDS.length",
        "Object.entries(window.OPENJLPT_EXAMPLES)",
        "Object.entries(window.OPENJLPT_KANJI_INFO)",
        "Object.hasOwn(EXAMPLES, word)",
        "data-load-status",
        "CC BY-SA 4.0",
        "DATA-NOTICE.md",
    )
    for hook in required_hooks:
        if hook not in index:
            errors.append(f"index.html 필수 연결/표시 누락: {hook}")

    level_counts = Counter(word["l"] for word in all_words)
    print(f"기존 단어: {len(base_words):,}개")
    print(f"신규 단어: {len(extra_words):,}개")
    print(f"전체 단어: {len(all_words):,}개")
    print(
        "전체 레벨별: "
        + ", ".join(f"N{level} {level_counts[level]:,}" for level in (5, 4, 3, 2, 1))
    )
    print(
        "신규 레벨별: "
        + ", ".join(
            f"N{level} {extra_level_counts[level]:,}" for level in (5, 4, 3, 2, 1)
        )
    )
    print(f"예문: {len(all_examples):,}개")
    print(
        f"신규 한자 훈음 수록률: {len(covered_kanji):,}/{len(required_kanji):,} "
        f"({coverage:.1%})"
    )

    if errors:
        print(f"\n검증 실패: {len(errors)}건", file=sys.stderr)
        for error in errors[:40]:
            print(f"- {error}", file=sys.stderr)
        if len(errors) > 40:
            print(f"- ... 외 {len(errors) - 40}건", file=sys.stderr)
        return 1

    print("검증 성공: 중복·필수 필드·예문·레벨·선택지 오류 0건")
    return 0


if __name__ == "__main__":
    raise SystemExit(validate())
