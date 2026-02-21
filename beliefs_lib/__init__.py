"""Belief tracker data model."""

from dataclasses import dataclass, field


@dataclass
class Claim:
    id: str
    text: str
    source: str = ""
    date: str = ""
    status: str = "IN"  # IN, OUT, STALE
    type: str = ""  # DERIVED, PREDICTED, MATCHED, INHERITED, AXIOM
    source_hash: str = ""  # SHA-256 of source file content at claim creation
    assumes: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    retracted_by: str = ""
    nogood: str = ""
    stale_reason: str = ""
    superseded_by: str = ""
    ref_check: str = ""


@dataclass
class Nogood:
    id: str
    description: str
    discovered: str = ""
    discovered_by: str = ""
    resolution: str = ""
    affects: list[str] = field(default_factory=list)
