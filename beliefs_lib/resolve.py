"""Entrenchment-based conflict resolution."""

from datetime import date

from . import Claim
from .check_stale import parse_date

SOURCE_PRIORITY = {
    "verifier-audit": 90,
    "simulation-result": 80,
    "formal-derivation": 70,
    "analytical-argument": 60,
    "entry-claim": 40,
    "claude-md-claim": 30,
    "readme-claim": 20,
    "speculation": 10,
}

RECENCY_BONUS = 5  # Per month, capped at 30

DERIVATION_TYPE_PRIORITY = {
    "DERIVED": 80,
    "PREDICTED": 70,
    "MATCHED": 50,
    "INHERITED": 40,
    "AXIOM": 90,
    "WARNING": 85,      # High priority — guardrails should be hard to retract
    "OBSERVATION": 45,   # Process-level fact
    "NOTE": 30,          # Informational, low entrenchment
}


def classify_source(source_path: str) -> str:
    """Map source path to source type."""
    s = source_path.lower()
    if "verifier" in s:
        return "verifier-audit"
    if "claude.md" in s or "claude-" in s.split("/")[-1].lower():
        return "claude-md-claim"
    if "readme" in s.split("/")[-1].lower():
        return "readme-claim"
    if "speculation" in s:
        return "speculation"
    return "entry-claim"


def months_since(date_str: str) -> int:
    """Months between claim date and today."""
    d = parse_date(date_str)
    if d is None:
        return 12  # Unknown date gets no recency bonus
    today = date.today()
    return (today.year - d.year) * 12 + (today.month - d.month)


def compute_entrenchment(claim: Claim) -> int:
    """Compute entrenchment score for a claim."""
    score = 0

    # Source priority
    source_type = classify_source(claim.source)
    score += SOURCE_PRIORITY.get(source_type, 0)

    # Recency bonus: 5 per month for claims less than 6 months old
    months = months_since(claim.date)
    recency = max(0, RECENCY_BONUS * (6 - months))
    recency = min(recency, 30)
    score += recency

    # Derivation type
    if claim.type:
        score += DERIVATION_TYPE_PRIORITY.get(claim.type, 0)

    return score


def resolve_conflict(claim_a: Claim, claim_b: Claim) -> tuple[str, str, int, int]:
    """Resolve conflict between two claims.

    Returns (winner_id, loser_id, winner_score, loser_score).
    """
    score_a = compute_entrenchment(claim_a)
    score_b = compute_entrenchment(claim_b)

    if score_a > score_b:
        return claim_a.id, claim_b.id, score_a, score_b
    elif score_b > score_a:
        return claim_b.id, claim_a.id, score_b, score_a
    else:
        # Tie: more recent wins
        date_a = parse_date(claim_a.date)
        date_b = parse_date(claim_b.date)
        if date_a and date_b and date_a > date_b:
            return claim_a.id, claim_b.id, score_a, score_b
        else:
            return claim_b.id, claim_a.id, score_b, score_a
