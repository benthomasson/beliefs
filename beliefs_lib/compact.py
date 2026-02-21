"""Dependency-aware context summary."""

from datetime import date

from . import Claim, Nogood
from .resolve import compute_entrenchment


def estimate_tokens(text: str) -> int:
    """Rough token estimate: word count."""
    return len(text.split())


def compact(claims: list[Claim], nogoods: list[Nogood], budget: int = 500, truncate: bool = True) -> str:
    """Produce a compact belief state summary within token budget.

    Priority: nogoods (never dropped), STALE claims, IN claims by entrenchment.
    """
    today = date.today().isoformat()
    total = len(claims)
    n_nogoods = len(nogoods)
    stale_claims = [c for c in claims if c.status == "STALE"]
    in_claims = sorted(
        [c for c in claims if c.status == "IN"],
        key=compute_entrenchment, reverse=True
    )

    lines = [
        f"# Belief State Summary ({today})",
        f"# {total} claims tracked | {n_nogoods} nogoods recorded | {len(stale_claims)} STALE flags pending",
        "",
    ]

    # Nogoods — never dropped
    if nogoods:
        lines.append("## Active Nogoods")
        for ng in nogoods:
            lines.append(f"- {ng.description} ({len(ng.affects)} claims affected)")
        lines.append("")

    # STALE claims — always included
    if stale_claims:
        lines.append("## Stale (needs review)")
        for c in stale_claims:
            line = f"- {c.id}: {c.text if not truncate else c.text[:80]}"
            if c.superseded_by:
                line += f" -> superseded by {c.superseded_by}"
            lines.append(line)
        lines.append("")

    # IN claims by entrenchment, truncated at budget
    if in_claims:
        lines.append("## Active Claims (IN)")
        for i, c in enumerate(in_claims):
            line = f"- {c.id}: {c.text if not truncate else c.text[:80]}"
            if c.type:
                line += f" ({c.type})"
            if c.depends_on:
                line += f" <- {', '.join(c.depends_on)}"
            lines.append(line)

            if estimate_tokens("\n".join(lines)) > budget:
                remaining = len(in_claims) - (i + 1)
                if remaining > 0:
                    lines.append(f"... ({remaining} more claims omitted)")
                break
        lines.append("")

    # Pending actions from STALE claims
    pending = []
    for c in stale_claims:
        if c.source:
            pending.append(f"- Update {c.source} (stale: {c.stale_reason or c.text[:60]})")
    if pending:
        lines.append("## Pending Actions")
        lines.extend(pending)
        lines.append("")

    summary = "\n".join(lines)
    token_count = estimate_tokens(summary)
    lines.append(f"Token count: {token_count} / {budget} budget")

    return "\n".join(lines)
