# Changelog

## Unreleased (Grok process 2026-07-25)

- **normalise / unwrap_tool_args**: peel Grok's name-unwrapped `use_tool` envelope so
  `check_state` records goal/progress/distance (was empty while checks still counted).
- **Session.agent**: stamp `agent` from `LASERBRAIN_AGENT` / runner env on every session file.
- **lb_gate**: same unwrap so ALWAYS_ALLOW sees real MCP tool names through `use_tool`.
- **tandem_write**: first-class `kind: claim`.
- Tests: envelope fixtures in `test_runtime.py`.
- **lb_gate WRITE_TOOLS**: add `search_replace` (Grok primary edit — claim gate was blind).
- **lb_gate ALWAYS_ALLOW**: add `search_tool` (MCP schema discovery; no schema deadlock).
- **lb_gate resolve_me**: `LASERBRAIN_AGENT` env → session.agent → unknown (no self-block).
- **lb_gate entry_agent**: accept tandem `from=` and `agent=`; payload.paths + payload.claims.
- **lb_gate deny howto**: Grok-aware (`use_tool` / `laserbrain__check_state`).
- **lb_safety.py**: deny force-push / reset --hard / rm -rf / wrangler deploy / npm publish.
- **Grok hooks**: `LASERBRAIN_AGENT=grok` on every hook command; wire lb_safety.
- **sync_from_icloud.sh**: also syncs lb_safety; sessions symlink under `~/.config/laserbrain/sessions`.
- Tests: `test_gate_grok.py`, `test_safety.py`.
- **MCP tandem_write**: kinds `wave_open` | `wave_close` (auto wave id on open).
- **lb_gate claimed_by_others**: free-form standing claims with paths; attach no-wave
  claims to open wave; fully-closed wave falls through; release via wave_close /
  done(release_claims).
- **lb_coverage**: subagent spawn nudge (parent check between waves).
- **quarantine_drift_log.py**: move unattributed drift rows → `drift-log.pre-agent.jsonl`.
- **Claude settings**: `LASERBRAIN_AGENT=claude` + `lb_safety` on PreToolUse.


## 0.4.2 — 2026-07-25

Three corpus-integrity fixes, all found by running Claude and Grok in tandem and then
reading what the two of them had written.

### Fixed
- **Concurrent runs no longer merge.** `session_id_of` fell back to the literal string
  `'unknown'`, so two agents with no session id in their environment wrote to one file:
  50 steps interleaved, catches attributed to whichever agent happened to be next. The
  fallback is now `unattributed-{ppid}` — stable across one run, different between
  concurrent ones. A merged session is worse than a missing one, because `dogfood.py`
  scores it as a single run and reports a confident wrong answer.
- **A post-reset prompt can no longer become the ground.** After `reset_task` the goal is
  deliberately absent, and the next thing typed is usually a continuation, not a task —
  one session recorded its ground as `'do all'`, which makes every later goal-drift
  verdict meaningless. The ground now comes from the next SPELLED check, where the agent
  states the goal explicitly.
- **Prompt envelopes are stripped.** Grok delivers prompts as
  `<user_query>…</user_query>`; stored raw, the fixed reference became markup and every
  goal comparison was made against tags. `clean_prompt()` unwraps them.

### Notes
- The published instrument has not moved. `test_frozen.py` still pins the calibration.
- Written alongside `lasermind/LINK.md`, which documents why shared state here must be
  append-only or per-agent and never shared-and-mutable. These three bugs are all one
  violation of that rule.


## 0.4.1 — 2026-07-24

### Added
- **`Verdict.why`** — every verdict now carries its own evidence in plain English and
  real numbers: which term of Φ moved, what the overlap was against the first goal and
  what threshold it missed, which distances stopped falling. A monitor that can only
  interrupt gets switched off; one that can be argued with gets trusted.

### Fixed
- **`publish.sh` polls the index instead of sleeping 25 seconds.** On the 0.4.0 release
  the upload succeeded and the verification reported failure, because the package had not
  propagated yet. The check was right to exist and wrong to guess a number.


## 0.4.0 — 2026-07-24

Dynamic where it can be, fixed where it must be.

### Added
- **`Calibration`** — the instrument's numbers as one object instead of six literals
  buried in the decision path. `Calibration()` with no arguments is the published
  instrument; anything else is an argued choice. Weights are validated to sum to 1.0,
  because Φ is reported as a 0..1 displacement and weights that sum to anything else
  silently rescale it.
- **`Harness(calibration=...)`** and **`Team(calibration=...)`**.
- **`laserbrain.vocab.embedding_similarity()`** — cosine over sentence embeddings, behind
  the new `semantic` extra: `pip install 'laserbrain[semantic]'`. Opt-in only; the
  default grammar keeps no dependencies.
- **`test_frozen.py`** — pins the published calibration and golden Φ values.

- **`test_cli.py`** — the CLI was at 0% coverage while the library around it was at 79%.
  Now 99%, including the documented exit-code contract (`check` returns nonzero on drift,
  so it is scriptable) and that `verify` rejects a tampered audit chain.
- **Cross-language parity** (`phronesis-world/scripts/check-drift-parity.ts`, wired into
  `prebuild`). `drift.ts` serves every MCP user; the PyPI package serves every SDK user;
  they carry the same weights and threshold and nothing checked that they agreed. 37
  golden verdicts, generated from the Python side, replayed through the TypeScript one.
- **`publish.sh`** — builds, runs the suite, prompts for the token with `read -rs` (never
  written to disk or exported), then installs the published version into a clean venv and
  imports what it claims to ship. The index is not the artefact; 0.3.0 proved that.

### Fixed
- **Teams ignored their calibration.** `_Dialogue` carried its own copy of the
  thresholds, so `Harness(calibration=...)` configured single agents while teams
  silently used the defaults — two detectors disagreeing about what drift means. One
  object now feeds both.

- **`laserbrain.observe.Observer`** — infers the working state from the runtime's own
  event trace, so the harness can be attached without the agent spelling anything each
  step. `goal` is inferred ONCE at ground and held (a reference re-derived from the
  agent's later behaviour is the self-referential monitor PROOF §3 rules out — there is
  deliberately no setter). `progress` is inferred every step: repetition reads as
  circling, consecutive failure reads as stuck. `distance` is NOT inferred.
- **An unknown distance now means unknown.** `_asdist(None)` used to fall back to 5 — a
  guess. `None` now contributes zero to the displacement, which makes inferred Φ a LOWER
  BOUND: it can under-report drift and cannot manufacture it. Attached automatically,
  that fails toward silence rather than toward false alarms. The honest cost is that the
  `stalled` detector needs distances and is unavailable without them; the verdict says
  so rather than hiding it. Inferred verdicts are tagged so they are never averaged with
  spelled ones and reported as one measurement.

### Notes
- **The published instrument has not moved.** Every default is what 0.3.4 shipped, and
  `test_frozen.py` now fails if that changes. Mutation testing on 0.3.4 found the old
  suite stayed green when `goal_min` moved 0.30 -> 0.45 and when the weights were
  reshuffled; both turn it red now.
- **No `stemmed_similarity`.** It was written, then deleted on sight of the numbers: the
  default `norm()` already strips stopwords and stems words over four characters, so it
  duplicated existing behaviour while implying an improvement it did not deliver. The
  real gap is synonyms, which is what the embedding grammar is for.

All notable changes to `laserbrain`. Dates are UTC. Still zero runtime dependencies.

## 0.3.4 — 2026-07-24

Two bugs found by probing the nested-recursion code before it ran near anything real.

- **Fixed: `RecursionError` reading a deep tree.** `tree_status()` and
  `tree_report()` walked the tree recursively, so past Python's recursion limit the
  *monitor* was the thing that crashed. Both traversals are now iterative, and
  `sub()` refuses to nest past `MAX_DEPTH` (50) with a legible error — nesting that
  deep is itself a drift signal, not a decomposition.
- **Fixed: false-positive tree stall.** `stalled` fired whenever 6 steps accumulated
  anywhere in the tree, even with every node advancing and zero drift, because only
  a root distance *improvement* cleared it and a root that checks once can never
  improve. It now also requires the root to have reported its distance at least
  twice (`root_checks` is exposed in `tree_status()`), so a busy-but-healthy tree no
  longer alarms while a genuine stall still fires.

## 0.3.3 — 2026-07-24

- **Pluggable grammar.** `Harness(similarity=fn)` swaps how "the same goal" is
  judged — an embedding cosine, structured state, anything returning 0..1 — while
  the theorem, thresholds and return logic stay put. The default word-overlap path
  is unchanged byte for byte (it is the published instrument), children from
  `sub()` inherit the metric, and a misbehaving metric degrades safely.
  Fixes the honest weakness: the default reads a synonym restatement as drift.

## 0.3.2 — 2026-07-24

- **Nested recursion** — `Harness.sub(goal)` opens a child recursion with its own
  ground, nested under the parent, to any depth; `tree_status()` and
  `tree_report()` read the whole set. Each node runs the proven flat detector on
  its own goal, so the tree catches what no node can see: every subtask reporting
  *advancing* while the decomposition never brings the root closer. This is the
  proof's third adjective (the reference must be defined at every depth the process
  nests to) finally implemented. The per-node check is the theorem; the tree-level
  stall signal is a prototype extension.

## 0.3.1 — 2026-07-24

- **Async act layer.** `await Harness().arun(async_step)` runs the loop with an
  async step function, awaiting your agent each iteration; `await hz.acheck(…)`
  dispatches the optional API mirror off the event loop so it never blocks.
  `on_return` / `on_escalate` may be sync or async.
- **Run report.** `Harness().report()` — a human-readable summary of the run
  (steps, drifts, and the Φ trajectory as a unicode sparkline). No key needed.
- Verified the LangGraph adapter end to end against a real `StateGraph` —
  see `example_langgraph.py`.

*(These landed after 0.3.0 was already uploaded. PyPI does not allow replacing a
released version, so they ship here rather than in 0.3.0.)*

## 0.3.0 — 2026-07-24

- **CLI.** `laserbrain demo` narrates an agent drifting off-goal and getting
  returned; `laserbrain check --goal … [--against …]` prints a verdict and exits
  non-zero on drift (scriptable); `laserbrain verify run.json` checks an exported
  audit chain. Colour only on a TTY.
- **Typed package.** Ships a `py.typed` marker and annotates the public API, so
  type checkers see laserbrain's types inline.
- **Nicer `Verdict`.** `str(verdict)` prints a readable one-liner
  (`[⚑ drifting] goal-drift · Φ=0.50 · ground=0.33 — …`).

## 0.2.1 — 2026-07-24

- **`ground_score`.** `Verdict.ground_score` and the `ground_score(phi)` function
  map displacement Φ to a bounded `[0,1]` reading (`1/(1+4·Φ)`), 1.0 at ground.
- Packaging: `license = "MIT"` (SPDX), `__version__` exposed.

## 0.2.0 — 2026-07-24

- **Framework adapters** (`laserbrain.adapters`): `guard`, `langgraph_node`,
  `crewai_step_callback`, `middleware`.
- **Human-in-the-loop escalation**: `Harness.run(escalate_after=, on_escalate=)`,
  plus `Harness.escalate()` / `resolution()` for the hosted review queue.
- **Tamper-evident audit**: hash-chained ledger via `Harness.audit()` /
  `export_audit()`, verifiable offline with `verify_audit()`.
- **Team continuity**: `Team.snapshot()` / `Team.restore()`.

## 0.1.0 — 2026-07-23

- Initial release: the frozen single-agent detector (`Harness.check`), the act
  layer (`Harness.run`), and styled recursion `Team`s. The check runs locally and
  free; a key mirrors to the API for retained history.
