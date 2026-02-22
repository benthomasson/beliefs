# Dependency-Aware Compaction Prompt

Use this as the custom summarization instruction for `/compact` in Claude Code.

## Usage

```
/compact [paste the prompt below]
```

Or, for a dynamic version that includes current belief state:

```
/compact [paste the prompt below, then append the output of `beliefs compact`]
```

## The Prompt

```
When summarizing this conversation, preserve the following with high priority:

BELIEF STATE: Preserve all currently held beliefs, their justifications, and their status (IN/OUT/STALE). Do not drop any belief that is currently IN or STALE. For each belief, preserve WHY it is held — the evidence, source, or reasoning that supports it. A belief without its justification is worse than no belief (it becomes an unjustified assumption).

WARNINGS AND OPEN PROBLEMS: Preserve all active WARNINGs and unresolved problems with full context. These are the most important items to carry forward — they represent known gaps that need resolution. Never silently drop a warning.

CONTRADICTIONS (NOGOODS): Preserve all recorded contradictions between beliefs, including which claims are involved and whether they are resolved. Unresolved contradictions must survive compaction — rediscovering a known contradiction wastes work.

DEPENDENCY CHAINS: When belief A depends on belief B, preserve both and their relationship. If you must drop context, prefer dropping independent beliefs over beliefs that are part of a dependency chain. Broken chains cannot be repaired after compaction.

RETRACTION HISTORY: Preserve records of beliefs that were retracted and WHY they were retracted. This prevents the re-derivation of known-bad conclusions.

DECISIONS AND THEIR RATIONALE: When a decision was made between alternatives, preserve the decision AND the reasons the alternatives were rejected. Without the rationale, the same deliberation will repeat.

LOWER PRIORITY (drop these first if needed):
- Exploratory discussion that did not lead to conclusions
- File contents that can be re-read from disk
- Intermediate steps of completed tasks
- Verbose tool output where only the result matters
```
