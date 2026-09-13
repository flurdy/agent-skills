#!/usr/bin/env python3
"""Atomically save and verify one generated wrap-up handoff."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import errno
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "wrap-up-save/v1"
MAX_INPUT_BYTES = 65_536
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_LINES = (
    "**Where to pick up:**",
    "**Jira:**",
    "**Beads:**",
    "**Deliverable:**",
    "**PRs:**",
    "**Context:**",
    "**Decisions so far:**",
    "**Working-copy risks:**",
    "**Open threads:**",
    "**Suggested next step:**",
)


class SaveFailure(Exception):
    def __init__(self, reason: str, detail: str = "", backup_path: Path | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail
        self.backup_path = backup_path


class SaveResult:
    def __init__(
        self,
        status: str,
        path: Path,
        *,
        mode: str | None = None,
        digest: str | None = None,
        byte_count: int | None = None,
        reason: str | None = None,
        detail: str | None = None,
        existing_digest: str | None = None,
        suggested_slug: str | None = None,
        backup_path: Path | None = None,
    ) -> None:
        self.status = status
        self.path = path
        self.mode = mode
        self.digest = digest
        self.byte_count = byte_count
        self.reason = reason
        self.detail = detail
        self.existing_digest = existing_digest
        self.suggested_slug = suggested_slug
        self.backup_path = backup_path

    def payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schemaVersion": SCHEMA_VERSION,
            "status": self.status,
            "path": str(self.path),
        }
        optional = {
            "mode": self.mode,
            "sha256": self.digest,
            "bytes": self.byte_count,
            "reason": self.reason,
            "detail": self.detail,
            "existingSha256": self.existing_digest,
            "suggestedSlug": self.suggested_slug,
            "backupPath": str(self.backup_path) if self.backup_path is not None else None,
        }
        result.update({key: value for key, value in optional.items() if value is not None})
        return result


class ExistingFile:
    def __init__(self, digest: str, identity: tuple[int, int, int, int]) -> None:
        self.digest = digest
        self.identity = identity


def bounded_safe_detail(error: BaseException) -> str:
    if isinstance(error, OSError) and error.errno is not None:
        return f"{type(error).__name__}: {os.strerror(error.errno)}"[:200]
    return type(error).__name__


def validate_arguments(date_text: str, time_text: str, slug: str, overwrite: str | None) -> None:
    try:
        parsed_date = dt.date.fromisoformat(date_text)
        parsed_time = dt.time.fromisoformat(time_text)
    except ValueError as error:
        raise SaveFailure("invalid-arguments", "date or time has an invalid format") from error
    if parsed_date.isoformat() != date_text or parsed_time.strftime("%H:%M") != time_text:
        raise SaveFailure("invalid-arguments", "date and time must be YYYY-MM-DD and HH:MM")
    if not SLUG.fullmatch(slug):
        raise SaveFailure("invalid-arguments", "slug must be lowercase kebab-case")
    if overwrite is not None and not SHA256.fullmatch(overwrite):
        raise SaveFailure("invalid-arguments", "overwrite hash must be lowercase SHA-256")


def validate_content(content: bytes, date_text: str, time_text: str, slug: str) -> None:
    if not content.strip():
        raise SaveFailure("empty-input")
    if len(content) > MAX_INPUT_BYTES:
        raise SaveFailure("input-too-large", f"handoff exceeds {MAX_INPUT_BYTES} bytes")
    if b"\0" in content:
        raise SaveFailure("nul-byte")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SaveFailure("invalid-utf8") from error

    lines = text.splitlines()
    expected_header = f"# Resume: {slug} — {date_text} {time_text}"
    if not lines or lines[0] != expected_header:
        raise SaveFailure("header-mismatch", f"expected header: {expected_header}")

    cursor = 0
    for required in REQUIRED_LINES:
        match = next(
            (index for index in range(cursor, len(lines)) if lines[index].startswith(required)),
            None,
        )
        if match is None:
            raise SaveFailure("incomplete-block", f"missing or out-of-order field: {required}")
        end = next(
            (index for index in range(match + 1, len(lines)) if re.match(r"^\*\*[^*]+:\*\*", lines[index])),
            len(lines),
        )
        value = lines[match][len(required):].strip()
        if not value and not any(line.strip().lstrip("-* ") for line in lines[match + 1:end]):
            raise SaveFailure("incomplete-block", f"empty field: {required}")
        cursor = match + 1


def target_path(home: Path, date_text: str, slug: str) -> Path:
    return home / ".claude" / "handoffs" / f"{date_text}-{slug}.md"


def file_identity(file_stat: os.stat_result) -> tuple[int, int, int, int]:
    return (file_stat.st_dev, file_stat.st_ino, file_stat.st_size, file_stat.st_mtime_ns)


def read_existing_file(path: Path) -> ExistingFile:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as error:
        raise SaveFailure("target-missing") from error
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise SaveFailure("target-symlink") from error
        raise SaveFailure("target-unreadable", bounded_safe_detail(error)) from error

    digest = hashlib.sha256()
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise SaveFailure("target-not-regular")
        while chunk := os.read(descriptor, 64 * 1024):
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return ExistingFile(digest.hexdigest(), file_identity(file_stat))


def inspect_target(path: Path) -> ExistingFile | None:
    try:
        target_stat = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(target_stat.st_mode):
        raise SaveFailure("target-symlink")
    if not stat.S_ISREG(target_stat.st_mode):
        raise SaveFailure("target-not-regular")
    existing = read_existing_file(path)
    if existing.identity[:2] != file_identity(target_stat)[:2]:
        raise SaveFailure("target-changed")
    return existing


def next_free_slug(directory: Path, date_text: str, slug: str) -> str:
    suffix = 2
    while os.path.lexists(directory / f"{date_text}-{slug}-{suffix}.md"):
        suffix += 1
    return f"{slug}-{suffix}"


def create_temporary_file(directory: Path, content: bytes) -> tuple[Path, os.stat_result]:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".wrap-up-", suffix=".tmp", dir=directory)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return temporary_path, os.lstat(temporary_path)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def verify_saved_file(path: Path, expected: bytes, expected_identity: tuple[int, int]) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise SaveFailure("verify-failed", bounded_safe_detail(error)) from error
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise SaveFailure("verify-failed", "saved path is not a regular file")
        if file_identity(file_stat)[:2] != expected_identity:
            raise SaveFailure("verify-failed", "saved file identity does not match this write")
        actual = bytearray()
        while chunk := os.read(descriptor, 64 * 1024):
            actual.extend(chunk)
            if len(actual) > len(expected):
                raise SaveFailure("verify-failed", "saved byte count does not match input")
        if bytes(actual) != expected:
            raise SaveFailure("verify-failed", "saved bytes do not match input")
        if not identity_matches(path, file_identity(file_stat)):
            raise SaveFailure("verify-failed", "saved path changed during verification")
    finally:
        os.close(descriptor)


def identity_matches(path: Path, expected: tuple[int, int, int, int]) -> bool:
    try:
        return file_identity(os.lstat(path)) == expected
    except FileNotFoundError:
        return False


def sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def install_new(temporary_path: Path, temporary_stat: os.stat_result, target: Path, content: bytes) -> None:
    try:
        os.link(temporary_path, target, follow_symlinks=False)
    except FileExistsError as error:
        raise SaveFailure("target-appeared") from error
    try:
        verify_saved_file(target, content, file_identity(temporary_stat)[:2])
        sync_directory(target.parent)
    except (SaveFailure, OSError):
        if identity_matches(target, file_identity(temporary_stat)):
            target.unlink()
        raise


def install_overwrite(
    temporary_path: Path,
    temporary_stat: os.stat_result,
    target: Path,
    content: bytes,
    existing: ExistingFile,
) -> None:
    if not identity_matches(target, existing.identity):
        raise SaveFailure("target-changed")
    backup = target.parent / f".wrap-up-backup-{secrets.token_hex(8)}.tmp"
    os.link(target, backup, follow_symlinks=False)
    installed = False
    try:
        if not identity_matches(target, existing.identity) or not identity_matches(backup, existing.identity):
            raise SaveFailure("target-changed")
        os.replace(temporary_path, target)
        installed = True
        verify_saved_file(target, content, file_identity(temporary_stat)[:2])
        sync_directory(target.parent)
        backup.unlink()
    except (SaveFailure, OSError) as error:
        # Never discard the only recovery copy when verification or rollback fails.
        with contextlib.suppress(OSError):
            if installed and identity_matches(target, file_identity(temporary_stat)):
                os.replace(backup, target)
                sync_directory(target.parent)
            elif not installed and identity_matches(target, existing.identity):
                backup.unlink()
        if os.path.lexists(backup):
            raise SaveFailure(
                "recovery-required", "Prior file retained; manual recovery needed", backup,
            ) from error
        raise


def save_handoff(
    date_text: str,
    time_text: str,
    slug: str,
    content: bytes,
    home: Path,
    overwrite_sha256: str | None,
) -> SaveResult:
    target = target_path(home, date_text, slug)
    temporary_path: Path | None = None
    try:
        if not home.is_absolute():
            raise SaveFailure("home-unavailable", "HOME must be an absolute directory")
        validate_arguments(date_text, time_text, slug, overwrite_sha256)
        validate_content(content, date_text, time_text, slug)
        try:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as error:
            raise SaveFailure("directory-unavailable", bounded_safe_detail(error)) from error

        existing = inspect_target(target)
        if overwrite_sha256 is None and existing is not None:
            return SaveResult(
                "collision",
                target,
                reason="target-exists",
                existing_digest=existing.digest,
                suggested_slug=next_free_slug(target.parent, date_text, slug),
            )
        if overwrite_sha256 is not None:
            if existing is None:
                raise SaveFailure("target-missing")
            if existing.digest != overwrite_sha256:
                raise SaveFailure("overwrite-mismatch")

        temporary_path, temporary_stat = create_temporary_file(target.parent, content)
        if existing is None:
            install_new(temporary_path, temporary_stat, target, content)
            mode = "new"
        else:
            install_overwrite(temporary_path, temporary_stat, target, content, existing)
            mode = "overwrite"
        return SaveResult(
            "saved",
            target,
            mode=mode,
            digest=hashlib.sha256(content).hexdigest(),
            byte_count=len(content),
        )
    except SaveFailure as error:
        return SaveResult(
            "failure",
            target,
            reason=error.reason,
            detail=error.detail or None,
            backup_path=error.backup_path,
        )
    except OSError as error:
        return SaveResult(
            "failure",
            target,
            reason="write-failed",
            detail=bounded_safe_detail(error),
        )
    finally:
        if temporary_path is not None:
            with contextlib.suppress(OSError):
                temporary_path.unlink(missing_ok=True)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date")
    parser.add_argument("time")
    parser.add_argument("slug")
    parser.add_argument("--overwrite-sha256")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    home_value = os.environ.get("HOME")
    if not home_value:
        target = Path(".claude/handoffs") / f"{arguments.date}-{arguments.slug}.md"
        result = SaveResult("failure", target, reason="home-unavailable")
    else:
        content = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        result = save_handoff(
            arguments.date,
            arguments.time,
            arguments.slug,
            content,
            Path(home_value),
            arguments.overwrite_sha256,
        )
    print(json.dumps(result.payload(), sort_keys=True, separators=(",", ":")))
    return {"saved": 0, "collision": 3}.get(result.status, 2 if result.reason in {
        "empty-input",
        "header-mismatch",
        "incomplete-block",
        "input-too-large",
        "invalid-arguments",
        "invalid-utf8",
        "nul-byte",
    } else 1)


if __name__ == "__main__":
    raise SystemExit(main())
