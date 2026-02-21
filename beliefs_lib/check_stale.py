"""Staleness detection: compare IN claims against newer entries."""

import hashlib
import re
from datetime import date
from pathlib import Path

from . import Claim
from .check_refs import extract_keywords, resolve_path

NEGATION_PAIRS = [
    ("not derived", "derived"),
    ("hasn't derived", "derived"),
    ("open problem", "resolved"),
    ("unresolved", "resolved"),
    ("not yet tested", "tested"),
    ("not yet tested", "completed"),
    ("unknown", "determined"),
    ("contradicts", "confirmed"),
]


def parse_date(date_str: str) -> date | None:
    """Parse YYYY-MM-DD date string."""
    try:
        parts = date_str.strip().split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def find_entries_after(after_date: date, repos: dict[str, str]) -> list[Path]:
    """Walk entries/YYYY/MM/DD/ dirs across all repos, return paths newer than date."""
    results = []
    date_dir_re = re.compile(r'.*/entries/(\d{4})/(\d{2})/(\d{2})$')

    for repo_name, repo_path in repos.items():
        entries_dir = Path(repo_path).expanduser() / "entries"
        if not entries_dir.is_dir():
            continue

        for year_dir in sorted(entries_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                for day_dir in sorted(month_dir.iterdir()):
                    if not day_dir.is_dir():
                        continue
                    m = date_dir_re.match(str(day_dir))
                    if not m:
                        continue
                    try:
                        entry_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    except ValueError:
                        continue
                    if entry_date <= after_date:
                        continue
                    # Collect all .md files in this day dir
                    for md_file in sorted(day_dir.glob("*.md")):
                        results.append(md_file)

    return results


def hash_file(path: Path) -> str:
    """SHA-256 hash of file content, first 16 hex chars."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def check_source_hashes(claims: list[Claim], repos: dict[str, str]) -> list[tuple[str, str, str, str]]:
    """Check IN claims whose source file content has changed since registration.

    Returns list of (claim_id, status, message, source_path).
    """
    results = []
    for claim in claims:
        if claim.status != "IN":
            continue
        if not claim.source or not claim.source_hash:
            continue

        source_path = resolve_path(claim.source, repos)
        if not source_path.exists():
            continue  # check-refs catches missing files

        try:
            current_hash = hash_file(source_path)
        except Exception:
            continue

        if current_hash != claim.source_hash:
            results.append((
                claim.id, "STALE",
                f"Source file changed (was {claim.source_hash}, now {current_hash})",
                claim.source,
            ))

    return results


def check_stale(claims: list[Claim], repos: dict[str, str]) -> list[tuple[str, str, str, str]]:
    """Check IN claims for staleness against newer entries and source hash changes.

    Returns list of (claim_id, status, message, entry_path).
    """
    results = []
    flagged = set()  # One STALE flag per claim (first evidence wins)

    # Pass 1: source hash comparison (direct, high confidence)
    hash_results = check_source_hashes(claims, repos)
    for claim_id, status, msg, source in hash_results:
        results.append((claim_id, status, msg, source))
        flagged.add(claim_id)

    # Pass 2: keyword + negation heuristic (indirect, lower confidence)
    for claim in claims:
        if claim.status != "IN":
            continue
        if claim.id in flagged:
            continue

        claim_date = parse_date(claim.date)
        if claim_date is None:
            continue

        newer_entries = find_entries_after(claim_date, repos)
        keywords = extract_keywords(claim.text)

        for entry_path in newer_entries:
            if claim.id in flagged:
                break

            try:
                content = entry_path.read_text().lower()
            except Exception:
                continue

            overlap = [k for k in keywords if k in content]
            if len(overlap) < 2:
                continue

            # Check for negation patterns
            claim_lower = claim.text.lower()
            for neg, pos in NEGATION_PAIRS:
                if neg in claim_lower and pos in content:
                    results.append((
                        claim.id, "STALE",
                        f"Claim contains '{neg}', entry contains '{pos}'",
                        str(entry_path)
                    ))
                    flagged.add(claim.id)
                    break
                elif pos in claim_lower and neg in content:
                    results.append((
                        claim.id, "STALE",
                        f"Claim contains '{pos}', entry contains '{neg}'",
                        str(entry_path)
                    ))
                    flagged.add(claim.id)
                    break

    return results
