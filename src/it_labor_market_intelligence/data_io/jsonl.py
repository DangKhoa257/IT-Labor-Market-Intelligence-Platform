"""Strict, streaming JSON Lines I/O."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any


class JsonlParseError(ValueError):
    """A JSONL line cannot be parsed as a JSON object."""

    def __init__(self, path: Path, line_number: int, message: str) -> None:
        super().__init__(f"{path}:{line_number}: {message}")
        self.path = path
        self.line_number = line_number


def iter_jsonl(path: Path | str) -> Iterator[dict[str, Any]]:
    """Yield JSON objects, skipping blank lines while retaining physical line numbers in errors."""

    target = Path(path)
    with target.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise JsonlParseError(target, line_number, error.msg) from error
            if not isinstance(value, dict):
                raise JsonlParseError(target, line_number, "expected a JSON object")
            yield value


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    """Materialize JSONL only when callers explicitly request a list."""

    return list(iter_jsonl(path))


def _encoded_records(records: Iterable[Mapping[str, Any]], *, pretty: bool) -> Iterator[str]:
    for record in records:
        if not isinstance(record, Mapping):
            raise TypeError("JSONL records must be mappings")
        if pretty:
            yield json.dumps(dict(record), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        else:
            yield (
                json.dumps(dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )


def write_jsonl(
    path: Path | str, records: Iterable[Mapping[str, Any]], *, pretty: bool = False
) -> None:
    """Write JSONL atomically without retaining the record stream in memory."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            for encoded in _encoded_records(records, pretty=pretty):
                output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def append_jsonl(
    path: Path | str, records: Iterable[Mapping[str, Any]], *, pretty: bool = False
) -> None:
    """Atomically append records by streaming old and new content into a replacement file."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    def combined() -> Iterator[Mapping[str, Any]]:
        if target.exists():
            yield from iter_jsonl(target)
        yield from records

    write_jsonl(target, combined(), pretty=pretty)
