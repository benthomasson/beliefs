"""Belief tracker CLI — manage claims and contradictions across repos."""

import sys
import argparse
from datetime import date
from pathlib import Path

from . import Claim, Nogood
from .parser import (
    parse_registry, append_claim, update_claim_status,
    parse_nogoods, append_nogood,
)
from .check_refs import check_refs, resolve_path
from .check_stale import check_stale, hash_file
from .resolve import compute_entrenchment, resolve_conflict, classify_source
from .nogoods_cmd import list_nogoods, filter_nogoods, detail_nogood
from .compact import compact


def default_path(name: str) -> Path:
    return Path.cwd() / name


def cmd_check_refs(args):
    repos, claims = parse_registry(args.registry)
    results = check_refs(claims, repos)

    ok = warn = fail = 0
    for claim_id, status, msg in results:
        if status == "OK":
            ok += 1
            if not args.quiet:
                print(f"OK    {claim_id}")
        elif status == "WARN":
            warn += 1
            if not args.quiet:
                print(f"WARN  {claim_id}")
                print(f"      {msg}")
        elif status == "FAIL":
            fail += 1
            if not args.quiet:
                print(f"FAIL  {claim_id}")
                print(f"      {msg}")
        if not args.quiet and status != "OK":
            print()

    if not args.quiet:
        print(f"Summary: {ok} OK, {warn} WARN, {fail} FAIL")

    sys.exit(1 if fail > 0 else 0)


def cmd_check_stale(args):
    repos, claims = parse_registry(args.registry)
    results = check_stale(claims, repos)

    already_stale = [c for c in claims if c.status == "STALE"]
    in_claims = [c for c in claims if c.status == "IN"]
    newly_stale_ids = set()
    for claim_id, status, msg, evidence_path in results:
        newly_stale_ids.add(claim_id)
        if not args.quiet:
            print(f"STALE {claim_id}")
            print(f"      {msg}")
            print(f"      Evidence: {evidence_path}")
            print()

    ok_count = len(in_claims) - len(newly_stale_ids)
    if not args.quiet:
        parts = [f"{ok_count} OK", f"{len(newly_stale_ids)} newly STALE"]
        if already_stale:
            parts.append(f"{len(already_stale)} already STALE")
        print(f"Summary: {', '.join(parts)}")

    sys.exit(1 if newly_stale_ids else 0)


def cmd_add(args):
    repos, claims = parse_registry(args.registry)

    # Check for duplicate ID
    for c in claims:
        if c.id == args.id:
            print(f"Error: claim '{args.id}' already exists", file=sys.stderr)
            sys.exit(1)

    status = args.status or "IN"
    source = args.source or ""
    source_hash = ""
    if source:
        source_path = resolve_path(source, repos)
        if source_path.exists():
            try:
                source_hash = hash_file(source_path)
            except Exception:
                pass

    claim = Claim(
        id=args.id,
        text=args.text,
        source=source,
        source_hash=source_hash,
        date=args.date or date.today().isoformat(),
        status=status,
        type=args.type or "",
        assumes=args.assumes or [],
        depends_on=args.depends_on or [],
        stale_reason=args.stale_reason or "",
    )

    append_claim(args.registry, claim)

    if not args.quiet:
        print(f"Added claim '{claim.id}' (status: {status})")
        if claim.source:
            print(f"  Source:      {claim.source}")
        print(f"  Date:        {claim.date}")
        if claim.assumes:
            print(f"  Assumptions: {', '.join(claim.assumes)}")
        if claim.depends_on:
            print(f"  Depends on:  {', '.join(claim.depends_on)}")
        if claim.type:
            print(f"  Type:        {claim.type}")
        if claim.stale_reason:
            print(f"  Stale reason: {claim.stale_reason}")


def cmd_resolve(args):
    repos, claims = parse_registry(args.registry)

    claim_a = claim_b = None
    for c in claims:
        if c.id == args.claim_a:
            claim_a = c
        if c.id == args.claim_b:
            claim_b = c

    if claim_a is None:
        print(f"Error: claim '{args.claim_a}' not found", file=sys.stderr)
        sys.exit(1)
    if claim_b is None:
        print(f"Error: claim '{args.claim_b}' not found", file=sys.stderr)
        sys.exit(1)

    winner_id, loser_id, winner_score, loser_score = resolve_conflict(claim_a, claim_b)

    if not args.quiet:
        for c in [claim_a, claim_b]:
            source_type = classify_source(c.source)
            score = compute_entrenchment(c)
            print(f"  {c.id}")
            print(f"    Text:    \"{c.text[:70]}\"")
            print(f"    Source:  {c.source} ({source_type}: {score})")
            print(f"    Date:    {c.date}")
            if c.type:
                print(f"    Type:    {c.type}")
            print(f"    Score:   {score}")
            print()

        print(f"Resolution: {winner_id} wins ({winner_score} vs {loser_score})")
        print(f"  -> {loser_id} should be marked STALE")


def cmd_nogoods(args):
    nogoods = parse_nogoods(args.nogoods_file)

    if args.affecting:
        matched = filter_nogoods(nogoods, affecting=args.affecting)
        if not matched:
            print(f"No nogoods affecting '{args.affecting}'")
            return
        for ng in matched:
            print(detail_nogood(ng))
            print()
    else:
        print(list_nogoods(nogoods))


def cmd_compact(args):
    repos, claims = parse_registry(args.registry)
    nogoods = parse_nogoods(args.nogoods_file)
    truncate = not args.no_truncate
    print(compact(claims, nogoods, budget=args.budget, truncate=truncate))


def cmd_list(args):
    repos, claims = parse_registry(args.registry)
    if args.status:
        claims = [c for c in claims if c.status == args.status]
    for c in claims:
        type_str = f" {c.type}" if c.type else ""
        print(f"[{c.status}]{type_str:10s}  {c.id}")


def cmd_show(args):
    repos, claims = parse_registry(args.registry)
    claim = None
    for c in claims:
        if c.id == args.claim_id:
            claim = c
            break
    if claim is None:
        print(f"Error: claim '{args.claim_id}' not found", file=sys.stderr)
        sys.exit(1)
    type_str = f" {claim.type}" if claim.type else ""
    print(f"### {claim.id} [{claim.status}]{type_str}")
    print(f"  {claim.text}")
    if claim.source:
        print(f"  Source:        {claim.source}")
    if claim.date:
        print(f"  Date:          {claim.date}")
    if claim.assumes:
        print(f"  Assumes:       {', '.join(claim.assumes)}")
    if claim.depends_on:
        print(f"  Depends on:    {', '.join(claim.depends_on)}")
    if claim.retracted_by:
        print(f"  Retracted by:  {claim.retracted_by}")
    if claim.stale_reason:
        print(f"  Stale reason:  {claim.stale_reason}")
    if claim.superseded_by:
        print(f"  Superseded by: {claim.superseded_by}")
    if claim.nogood:
        print(f"  Nogood:        {claim.nogood}")
    if claim.ref_check:
        print(f"  Ref check:     {claim.ref_check}")


def cmd_update(args):
    repos, claims = parse_registry(args.registry)
    claim = None
    for c in claims:
        if c.id == args.claim_id:
            claim = c
            break
    if claim is None:
        print(f"Error: claim '{args.claim_id}' not found", file=sys.stderr)
        sys.exit(1)

    extra = {}
    if args.status:
        pass  # handled by update_claim_status directly
    if args.stale_reason:
        extra["stale_reason"] = args.stale_reason
    if args.superseded_by:
        extra["superseded_by"] = args.superseded_by
    if args.add_assumes:
        new_assumes = list(set(claim.assumes + args.add_assumes))
        extra["assumes"] = ", ".join(new_assumes)
    if args.add_depends_on:
        new_deps = list(set(claim.depends_on + args.add_depends_on))
        extra["depends_on"] = ", ".join(new_deps)

    new_status = args.status or claim.status
    update_claim_status(args.registry, args.claim_id, new_status, **extra)

    if not args.quiet:
        print(f"Updated claim '{args.claim_id}'")
        if args.status:
            print(f"  Status:  {claim.status} -> {new_status}")
        for k, v in extra.items():
            print(f"  {k.replace('_', ' ').title()}: {v}")


def cmd_add_repo(args):
    repos, claims = parse_registry(args.registry)

    # Parse name:path or bare name
    spec = args.repo
    if ":" in spec:
        name, path = spec.split(":", 1)
    else:
        name = spec
        path = f"~/git/{spec}"

    if name in repos:
        print(f"Error: repo '{name}' already exists ({repos[name]})", file=sys.stderr)
        sys.exit(1)

    # Insert into Repos section in-place (after last repo entry, before blank lines)
    text = args.registry.read_text()
    lines = text.splitlines()
    insert_at = None
    last_repo_line = None
    for i, line in enumerate(lines):
        if line.strip() == "## Repos":
            insert_at = i + 1
        elif insert_at is not None and line.startswith("## "):
            break
        elif insert_at is not None and line.startswith("- "):
            last_repo_line = i + 1
    if last_repo_line is not None:
        insert_at = last_repo_line

    if insert_at is None:
        print("Error: no ## Repos section found in registry", file=sys.stderr)
        sys.exit(1)

    lines.insert(insert_at, f"- {name}: {path}")
    args.registry.write_text("\n".join(lines) + "\n")

    if not args.quiet:
        print(f"Added repo '{name}' -> {path}")


def cmd_init(args):
    if args.registry.exists():
        print(f"Error: {args.registry} already exists", file=sys.stderr)
        sys.exit(1)

    repos = {}
    for name in (args.repos or []):
        # Accept "name:path" or bare "name" (defaults to ~/git/name)
        if ":" in name:
            rname, rpath = name.split(":", 1)
        else:
            rname = name
            rpath = f"~/git/{name}"
        repos[rname] = rpath

    lines = [
        "# Belief Registry",
        "<!-- Generated by beliefs CLI. Hand-editable; run `beliefs check-refs` after manual edits. -->",
        "",
        "## Repos",
    ]
    for rname, rpath in sorted(repos.items()):
        lines.append(f"- {rname}: {rpath}")
    lines.append("")
    lines.append("## Claims")
    lines.append("")

    args.registry.write_text("\n".join(lines))

    # Create nogoods.md if it doesn't exist
    if not args.nogoods_file.exists():
        args.nogoods_file.write_text("# Nogoods\n\n")

    if not args.quiet:
        print(f"Created {args.registry}")
        if repos:
            print(f"  Repos: {', '.join(sorted(repos))}")
        print(f"Created {args.nogoods_file}")


def cmd_hash_sources(args):
    from .parser import serialize_registry

    repos, claims = parse_registry(args.registry)
    updated = 0
    skipped = 0
    missing = 0

    for claim in claims:
        if not claim.source:
            skipped += 1
            continue
        if claim.source_hash and not args.force:
            skipped += 1
            continue

        source_path = resolve_path(claim.source, repos)
        if not source_path.exists():
            missing += 1
            if not args.quiet:
                print(f"MISS  {claim.id} — source not found: {claim.source}")
            continue

        try:
            new_hash = hash_file(source_path)
        except Exception as e:
            missing += 1
            if not args.quiet:
                print(f"ERR   {claim.id} — {e}")
            continue

        claim.source_hash = new_hash
        updated += 1
        if not args.quiet:
            print(f"HASH  {claim.id} — {new_hash}")

    if updated > 0:
        args.registry.write_text(serialize_registry(repos, claims))

    if not args.quiet:
        print(f"\nSummary: {updated} hashed, {skipped} skipped, {missing} missing")


def main():
    parser = argparse.ArgumentParser(
        prog="beliefs",
        description="Belief tracker — manage claims and contradictions across repos",
    )
    parser.add_argument(
        "--registry", type=Path, default=default_path("beliefs.md"),
        help="Path to beliefs.md (default: ./beliefs.md)",
    )
    parser.add_argument(
        "--nogoods-file", type=Path, default=default_path("nogoods.md"),
        help="Path to nogoods.md (default: ./nogoods.md)",
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress detail, exit code only")

    sub = parser.add_subparsers(dest="command", required=True)

    # init
    init_p = sub.add_parser("init", help="Create beliefs.md and nogoods.md in current directory")
    init_p.add_argument("--repos", nargs="*", help="Repo names (name:path or bare name for ~/git/name)")

    # add-repo
    add_repo_p = sub.add_parser("add-repo", help="Add a repo to the registry")
    add_repo_p.add_argument("repo", help="Repo spec (name or name:path)")

    # check-refs
    sub.add_parser("check-refs", help="Verify cross-references for all claims")

    # check-stale
    sub.add_parser("check-stale", help="Detect stale IN claims vs newer entries")

    # add
    add_p = sub.add_parser("add", help="Add a new claim to the registry")
    add_p.add_argument("--id", required=True, help="Claim ID (kebab-case)")
    add_p.add_argument("--text", required=True, help="Claim text (one line)")
    add_p.add_argument("--source", help="Source file path (repo/path)")
    add_p.add_argument("--date", help="Claim date YYYY-MM-DD (default: today)")
    add_p.add_argument("--assumes", nargs="*", help="Assumption labels")
    add_p.add_argument("--depends-on", nargs="*", help="Claim IDs this depends on")
    add_p.add_argument("--type", choices=[
                        "DERIVED", "PREDICTED", "MATCHED", "INHERITED", "AXIOM",
                        "WARNING", "OBSERVATION", "NOTE"],
                        help="Claim type (derivation or process-level)")
    add_p.add_argument("--status", choices=["IN", "OUT", "STALE"],
                        help="Initial status (default: IN)")
    add_p.add_argument("--stale-reason", help="Reason for STALE status (use with --status STALE)")

    # resolve
    resolve_p = sub.add_parser("resolve", help="Resolve conflict between two claims")
    resolve_p.add_argument("claim_a", help="First claim ID")
    resolve_p.add_argument("claim_b", help="Second claim ID")

    # nogoods
    nogoods_p = sub.add_parser("nogoods", help="List/query the nogoods database")
    nogoods_p.add_argument("--affecting", help="Filter by affected claim ID")

    # compact
    compact_p = sub.add_parser("compact", help="Produce a context summary")
    compact_p.add_argument("--budget", type=int, default=500, help="Token budget (default: 500)")
    compact_p.add_argument("--no-truncate", action="store_true", help="Don't truncate claim text")

    # list
    list_p = sub.add_parser("list", help="List all claims (ID and status)")
    list_p.add_argument("--status", choices=["IN", "OUT", "STALE"], help="Filter by status")

    # show
    show_p = sub.add_parser("show", help="Show full detail for one claim")
    show_p.add_argument("claim_id", help="Claim ID to show")

    # update
    update_p = sub.add_parser("update", help="Update an existing claim")
    update_p.add_argument("claim_id", help="Claim ID to update")
    update_p.add_argument("--status", choices=["IN", "OUT", "STALE"], help="New status")
    update_p.add_argument("--stale-reason", help="Set stale reason")
    update_p.add_argument("--superseded-by", help="Set superseded-by claim ID")
    update_p.add_argument("--add-assumes", nargs="*", help="Add assumption labels")
    update_p.add_argument("--add-depends-on", nargs="*", help="Add dependency claim IDs")

    # hash-sources
    hash_p = sub.add_parser("hash-sources", help="Backfill source hashes for existing claims")
    hash_p.add_argument("--force", action="store_true", help="Re-hash even if hash already exists")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "add-repo": cmd_add_repo,
        "check-refs": cmd_check_refs,
        "check-stale": cmd_check_stale,
        "add": cmd_add,
        "resolve": cmd_resolve,
        "nogoods": cmd_nogoods,
        "compact": cmd_compact,
        "list": cmd_list,
        "show": cmd_show,
        "update": cmd_update,
        "hash-sources": cmd_hash_sources,
    }
    commands[args.command](args)
