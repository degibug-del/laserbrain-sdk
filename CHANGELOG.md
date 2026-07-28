# Changelog

## 0.11.0 — 2026-07-28

**`Nova` and `Skill` ship.** They were written for 0.10.0 and did not make the wheel. The
tree and PyPI both read `0.10.0` while holding different code — the published package was
two symbols short, and `from laserbrain import Nova`, which phronesis.world/nova prints as
the first line a reader types, raised `ImportError` for everyone who followed it.

That is the second time one version number has covered two different contents (0.9.0 did
it with `collisions`/`route`/`manage`). The lesson taken both times and applied properly
this time: a release is verified by installing the built artifact into a clean environment
and importing from it, never by reading the source tree — the tree is always right, which
is exactly why checking it proves nothing.

- **`Nova(goal=...)`** — the agent. Holds skills, runs a loop, takes a reading every step.
  `learn(name, fn)` teaches it, `use()` lists what it knows, `run(act)` drives it, and
  `compose({name: agent})` runs a fleet and returns what no member could see from inside
  itself: `collisions`, `route`, `fleet_catches`, `seen_only_from_above`.
- **`Skill`** — the unit `learn` stores and `use` reports.
- **No method sets, moves or clears a ground.** The harness freezes it at the first check.
  Python offers no true barrier, so nova offers evidence instead: the ground is
  fingerprinted at first reading and `ground_intact()` answers directly. Tampering does not
  raise, it is reported — a monitor that crashes gets removed, one that tells you gets read.

## 0.10.0 — 2026-07-28

**supercode is the manager; laserbrain is the reference.** That division decides how much
authority a supervisor may hold. Because the reference is always laserbrain's, supercode
may manage freely — it acts on readings it did not author. The one thing it may not do is
set a running agent's ground, because then laserbrain would be measuring against a
reference the manager chose.

- **`Supercode.collisions()`** — pairs of agents whose GROUNDS overlap. The reading only a
  supervisor can take: two agents handed the same task are both perfectly grounded, both
  advancing and correct at every step, so the duplication is invisible from inside either
  harness and no threshold on Φ will surface it. Not a tenth verdict — the nine describe
  one agent against one ground and keep meaning that.
- **`Supercode.route()`** — which agent keeps the shared ground and which yields, ranked on
  catches, then steps invested, then displacement. Returns `keep: None` when the observable
  state gives no basis, rather than a coin-flip dressed as a decision.
- **`Supercode.manage({name: step_fn})`** — runs N agents. Halts duplicated work, injects
  each agent's OWN verdict into its loop, escalates to a human on persistent drift or on a
  collision it cannot honestly decide. Authority goes up to a person, never sideways.
- **`Harness.saw()` / `Verdict.anchored`** now have a caller: lb_coverage feeds observed
  tool outcomes, so `anchored` reports 0.5 or 1.0 instead of 0.5 forever.
- `test_collisions.py`, `test_route.py`, `test_manage.py`.

Note: 0.9.0 shipped without collisions/route/manage while the working tree had them, so
0.9.0 on PyPI and 0.9.0 locally were different code. That is what this release fixes, and
check-laserbrain-parity now compares content rather than version strings.

## 0.9.0 — 2026-07-27

- **`oscillating` reads the GROUND, not just the reading.** `x = [x, f(x)]` makes the
  state a pair: the ground is `x`, the verdicts are `f(x)`, and the cycle detector only
  ever saw `f(x)`. So a genuinely circling agent was caught only when its *readings* also
  happened to repeat periodically — a coincidence stacked on the thing being detected. The
  harness now records the canonical spelling of each ground and checks that trail first,
  falling back to the readings. A period-2 ground (bouncing between two files) fires at
  step 6; the sin/cos period-4 case fires at 8, where the reading-only detector needed 11.
- **`Harness.saw()` and `Verdict.anchored`.** Half of Φ has always been the agent's own
  account of itself — `distance` and `progress` are simply typed in — and nothing said so.
  `saw('tool', 'pytest', ok=True)` records what actually happened; `anchored` reports how
  much of Φ's weight is external: 0.5 when only the frozen ground is, 1.0 when the
  self-report is backed by observed work. `corroboration()` gives the run-level fraction.
  **Φ is unchanged** — reweighting would move the published instrument and invalidate every
  calibration and vector, with no data yet behind a new weight. The test that matters:
  an agent doing the work and an agent inventing its numbers produce *identical* Φ. Only
  `anchored` separates them.
- **`test_anchor.py`** and ground-cycle cases in `test_cycle.py`.

Note for anyone constructing `Verdict` positionally: `anchored` is the LAST field. Placing
it earlier shifts `why` into it on every call site, which is what the first attempt did.

## 0.8.1 — 2026-07-27

- **`oscillating` now sees period 4.** `_cycle` tested periods 2 and 3 only, which misses
  the canonical example of the equation the verdict was derived from: `x = [sin, f(x)]`
  with `f = d/dx` cycles sin -> cos -> -sin -> -cos, period **four**. Sixteen readings,
  four whole repeats, and the detector returned 0. Nothing failed — a range that is too
  narrow does not throw, it answers "no cycle", and every reading beneath it looks healthy.
  Now 2..6, with two whole repeats as the bar and a floor of six readings
  (`need = max(6, 2p)`), which leaves periods 2 and 3 at exactly their previous behaviour.
  The smallest period still wins: `[a,b,a,b,a,b]` is 2, not 4.
- **`test_cycle.py`.** The ninth verdict shipped in three implementations with no test of
  its own, which is why the range went unquestioned. The suite covers the declared range,
  the deliberate cap above it, the cases that must NOT read as cycles, smallest-period-
  wins, and an end-to-end run through a real `Harness`. It fails against the old 2..3
  range — verified by reverting and watching six assertions go red.

## 0.8.0 — 2026-07-27

Minor rather than patch: nothing new was built, but three functions that already existed
became reachable, and adding to the public API is a minor bump even when the code behind
it is unchanged.

- **Bugfinder is six, not three.** `unfalsified`, `instrument_blind` and `unrun` were
  written alongside `residue`, `contaminated` and `stale_gate` and then left out of both
  the import and `__all__` — so half of Bugfinder was public API and half was reachable
  only as `laserbrain.catches.unfalsified`, which nothing documents. Splitting a set of six
  down the middle fails no test: every name still resolves, the package still imports, and
  the only symptom is that three of them are invisible. `__all__` is now 48.
- **`tandem` is `link`.** Renamed everywhere it is an identifier. The Python API was
  already `link_read` / `link_write` / `link_whoami`; what changes here is the log —
  `LASERBRAIN_LINK_LOG` is the preferred env var and `~/.config/laserbrain/link.jsonl` the
  default path. **Backwards compatible**: `LASERBRAIN_TANDEM_LOG` is still honoured, and
  the legacy `tandem.jsonl` is still used when it exists and the new file does not, so an
  un-migrated machine keeps its history instead of silently starting a fresh log.
- **One resolver, four callers.** `link.py`, `waves.py`, `lb_gate.py` and the MCP server
  each resolved that path independently. If they disagree, two agents "sharing" a channel
  write to different files and each reads an empty one — which presents exactly as the
  other agent having said nothing. All four now derive it identically.

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
