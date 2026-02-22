"""Cross-reference verification: check that claim sources exist and are consistent."""

import re
from pathlib import Path

from . import Claim

STOPWORDS = frozenset(
    "the a an is are was were of in to for and or but not from with by at on "
    "as it its this that has have had be been do does did can could will would "
    "should may might shall".split()
)


def extract_keywords(text: str) -> list[str]:
    """Split on non-alphanumeric, lowercase, filter stopwords, keep terms >= 3 chars."""
    tokens = re.split(r'[^a-zA-Z0-9]+', text.lower())
    return [t for t in tokens if len(t) >= 3 and t not in STOPWORDS]


def resolve_path(source: str, repos: dict[str, str]) -> Path:
    """Expand repo-prefixed source to absolute path.

    Supports both 'physics/entries/...' and 'physics:entries/...' formats.
    """
    # Try colon separator first (physics:entries/...)
    if ":" in source:
        repo_name, rest = source.split(":", 1)
        if repo_name in repos:
            base = Path(repos[repo_name]).expanduser()
            return base / rest

    # Try slash separator (physics/entries/...)
    parts = source.split("/", 1)
    if len(parts) == 2 and parts[0] in repos:
        base = Path(repos[parts[0]]).expanduser()
        return base / parts[1]

    # Try as-is (relative to cwd or absolute)
    return Path(source).expanduser()


def find_claim(claims: list[Claim], claim_id: str) -> Claim | None:
    """Find a claim by ID."""
    for c in claims:
        if c.id == claim_id:
            return c
    return None


def check_refs(claims: list[Claim], repos: dict[str, str]) -> list[tuple[str, str, str]]:
    """Check cross-references for all claims.

    Returns list of (claim_id, status, message) where status is OK/WARN/FAIL.
    """
    results = []
    for claim in claims:
        if not claim.source:
            results.append((claim.id, "WARN", "No source specified"))
            continue

        source_path = resolve_path(claim.source, repos)
        if not source_path.exists():
            results.append((claim.id, "FAIL", f"Source file not found: {claim.source}"))
            continue

        # Keyword consistency check
        keywords = extract_keywords(claim.text)
        if keywords:
            try:
                content = source_path.read_text().lower()
            except Exception as e:
                results.append((claim.id, "WARN", f"Cannot read source: {e}"))
                continue

            missing = [k for k in keywords if k not in content]
            if len(missing) > len(keywords) * 0.5:
                results.append((
                    claim.id, "WARN",
                    f"Source missing {len(missing)}/{len(keywords)} keywords: {', '.join(missing[:5])}"
                ))
            else:
                results.append((claim.id, "OK", "Consistent"))
        else:
            results.append((claim.id, "OK", "No keywords to check"))

        # Check depends_on references (must exist as claims)
        for dep_id in claim.depends_on:
            dep = find_claim(claims, dep_id)
            if dep is None:
                results.append((claim.id, "FAIL", f"Depends on non-existent claim: {dep_id}"))
            elif dep.status == "OUT":
                results.append((claim.id, "WARN", f"Depends on retracted claim: {dep_id}"))

    # Second pass: check assumes that look like claim IDs but don't exist
    claim_ids = {c.id for c in claims}
    for claim in claims:
        for label in claim.assumes:
            # Warn if the label matches an existing claim ID pattern (has hyphens)
            # and is close to but doesn't match any actual claim
            if "-" in label and label not in claim_ids:
                # Check if any claim ID shares a prefix
                for cid in claim_ids:
                    if label.startswith(cid.rsplit("-", 1)[0]) or cid.startswith(label.rsplit("-", 1)[0]):
                        results.append((claim.id, "WARN",
                            f"Assumes '{label}' looks like claim ID but doesn't exist (similar: {cid})"))
                        break

    return results
