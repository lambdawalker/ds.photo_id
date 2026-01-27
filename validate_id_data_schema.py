#!/usr/bin/env python3
"""
Validate one JSON file OR all JSON files in a directory using jsonschema.

Usage:
  python validate_profile.py path/to/file.json
  python validate_profile.py path/to/directory
  python validate_profile.py path/to/directory --recursive

Exit codes:
  0 = all valid
  1 = at least one invalid or unreadable JSON file
  2 = usage / path error
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, List, Tuple

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError


# Create an instance and register custom formats on THIS instance (no deprecation warning)
format_checker = FormatChecker()


@format_checker.checks("date-ymd")
def is_date_ymd(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    _, month, day = value.split("-")
    m = int(month)
    d = int(day)
    return 1 <= m <= 12 and 1 <= d <= 31


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "PersonProfile",
    "type": "object",
    "additionalProperties": False,
    "required": ["person", "contact", "physical", "document", "system"],
    "properties": {
        "person": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "birth", "demographics"],
            "properties": {
                "name": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["first", "middle", "last", "suffix"],
                    "properties": {
                        "first": {"type": "string"},
                        "middle": {"type": "string"},
                        "last": {"type": "string"},
                        "suffix": {"type": "string"},
                    },
                },
                "birth": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["date", "place"],
                    "properties": {
                        "date": {"type": "string", "format": "date-ymd"},
                        "place": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["city", "state", "country"],
                            "properties": {
                                "city": {"type": "string"},
                                "state": {"type": "string"},
                                "country": {"type": "string"},
                            },
                        },
                    },
                },
                "demographics": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["gender", "ethnicity", "nationality"],
                    "properties": {
                        "gender": {"type": "string"},
                        "ethnicity": {"type": "string"},
                        "nationality": {"type": "string"},
                    },
                },
            },
        },
        "contact": {
            "type": "object",
            "additionalProperties": False,
            "required": ["address", "email", "phone_number"],
            "properties": {
                "address": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["line1", "line2", "city", "state", "postal_code", "country"],
                    "properties": {
                        "line1": {"type": "string"},
                        "line2": {"type": "string"},
                        "city": {"type": "string"},
                        "state": {"type": "string"},
                        "postal_code": {"type": "string"},
                        "country": {"type": "string"},
                    },
                },
                "email": {"type": "string", "format": "email"},
                "phone_number": {"type": "string"},
            },
        },
        "physical": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "eye_color",
                "hair_color",
                "height",
                "weight",
                "blood_type",
                "distinguishing_marks",
            ],
            "properties": {
                "eye_color": {"type": "string"},
                "hair_color": {"type": "string"},
                "height": {"type": "number", "minimum": 0},
                "weight": {"type": "number", "minimum": 0},
                "blood_type": {"type": "string"},
                "distinguishing_marks": {"type": "array", "items": {"type": "string"}},
            },
        },
        "document": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "type",
                "number",
                "issuing_authority",
                "jurisdiction",
                "issued",
                "expires",
            ],
            "properties": {
                "type": {"type": "string"},
                "number": {"type": "string"},
                "issuing_authority": {"type": "string"},
                "jurisdiction": {"type": "string"},
                "issued": {"type": "string", "format": "date-ymd"},
                "expires": {"type": "string", "format": "date-ymd"},
            },
        },
        "system": {
            "type": "object",
            "additionalProperties": False,
            "required": ["units", "source"],
            "properties": {
                "units": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["height", "weight"],
                    "properties": {
                        "height": {"type": "string", "enum": ["cm", "in"]},
                        "weight": {"type": "string", "enum": ["kg", "lb"]},
                    },
                },
                "source": {"type": "string"},
            },
        },
    },
}


def format_error(err: ValidationError) -> str:
    path = "$"
    if err.path:
        path += "." + ".".join(str(p) for p in err.path)
    return f"{path}: {err.message}"


def iter_json_files(path: Path, recursive: bool) -> Iterable[Path]:
    if path.is_file():
        if path.suffix.lower() == ".json":
            yield path
        return

    globber = path.rglob("*.json") if recursive else path.glob("*.json")
    for p in globber:
        if p.is_file():
            yield p


def validate_file(
    file_path: Path, validator: Draft202012Validator
) -> Tuple[bool, List[str]]:
    try:
        with file_path.open("r", encoding="utf-8") as f:
            instance = json.load(f)
    except Exception as e:
        return False, [f"Could not read/parse JSON: {e}"]

    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if not errors:
        return True, []
    return False, [format_error(e) for e in errors]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate JSON files against a schema.")
    parser.add_argument(
        "--path",
        default="../idPhoto/json_profiles",
        help="Path to a JSON file or a directory of JSON files."
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="If path is a directory, search for JSON files recursively.",
    )
    args = parser.parse_args()

    target = Path(args.path).expanduser().resolve()
    if not target.exists():
        print(f"Path does not exist: {target}")
        return 2

    # IMPORTANT: use the same format_checker instance we registered "date-ymd" on
    validator = Draft202012Validator(SCHEMA, format_checker=format_checker)

    files = list(iter_json_files(target, args.recursive))
    if target.is_dir() and not files:
        print(f"No .json files found in: {target} (recursive={args.recursive})")
        return 2

    any_fail = False
    passed = 0
    failed = 0

    for fp in sorted(files):
        ok, problems = validate_file(fp, validator)
        rel = fp.relative_to(target) if target.is_dir() else fp.name

        if ok:
            # print(f"✅ {rel}")
            passed += 1
        else:
            print(f"❌ {rel}")
            for msg in problems:
                print(f"   - {msg}")
            failed += 1
            any_fail = True

    print(f"\nSummary: {passed} passed, {failed} failed, {passed + failed} total")
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
