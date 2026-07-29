# Changelog

## 0.15.0 — 2026-07-29

**`Workflow.step()` no longer demands a callable.** Found by authoring the first real
method rather than another test: you could VEND an unbound workflow but you could not WRITE
one, because `step()` required an implementation while `from_spec()` happily produced steps
without any. A stored method carries no code — that is its entire point — so authoring one
had no path through the API. `fn` is now optional and defaults to the same unbound
placeholder `from_spec` uses, so a hand-written method and a vended one are the same
object.

The asymmetry survived a full test suite because every test built workflows out of lambdas.
Nothing exercised the case the feature exists for.

## 0.14.0 — 2026-07-29

**The operator gets the rest of its hands.** Grammar 1.9.0 declares the layer holds "the
shell, the filesystem, the browser, the deploy, the send". Only `shell` existed.

- **`write(path, content)` reads reversibility off the disk instead of taking it on trust.**
  This is the one place the operator can settle the question rather than believe an answer:
  writing a file that does not exist is reversible — delete it and the world is as it was —
  while writing over one that does destroys content with no other copy. So `write` has no
  `reversible` parameter at all. Offering one would only create a way to be wrong about a
  fact already sitting in the filesystem. The same call with the same arguments is allowed
  the first time and refused the second, which is correct and is tested.
- **`delete(path)` is never reversible and never recursive.** A directory raises outright,
  even with an approving authorizer. A tree delete is the action most likely to be
  regretted, `rm -rf` is already on the escalation list for `shell`, and an operator that
  offered a convenient one-call version would hand back exactly what the layer exists to
  slow down.
- **`http(method, url)`** — GET/HEAD/OPTIONS are treated as reads and pass; POST, PUT,
  PATCH and DELETE are outward and irreversible, because a request that changed something
  on someone else's machine cannot be recalled by you. The read exemption is a judgment and
  is documented as one: an API that mutates on GET exists, and any request tells the far
  end you made it.

Everything still routes through the one gate, so the guarantees from 0.12.0 hold unchanged:
default deny, approval never caches, and every refusal is recorded rather than silent.

## 0.13.0 — 2026-07-28

**`Workflow` and `Store`, which 0.12.0 was supposed to carry and did not.** The wheel was
built before `workflow.py` existed and never rebuilt, so 0.12.0 went to PyPI with 53
exports instead of 56 — `Operator` present, `Workflow`, `Step` and `Store` absent. PyPI
versions cannot be reused, so the fix is a new number rather than a corrected upload.

**The release check that let it through is now incapable of that failure.** Step 5 of the
publish script existed *because* 0.10.0 shipped without `Nova`: install the wheel into a
clean venv and import from site-packages rather than from the tree. It ran on 0.12.0 and
passed — because it asserted a hand-written list of symbols (`Nova, Skill, Operator,
Refused`), every one of which was present. A hardcoded list can never contain the thing you
just added, so the check was stale in precisely the situation it exists for.

It no longer names symbols. It reads `__all__` from the source tree and from the installed
wheel and diffs them; anything exported but not shipped fails the release. Nothing to
remember to update, and it would have caught this.

- **`Workflow(goal=...)`** — an ordered process, grounded at the top and at every step.
  `step(name, fn, goal=, irreversible=, outward=)`, then `run(operator=)`. Catches a step
  that did something other than what the method declared it for: declared "build the
  release wheel", reported "refactoring the parser", scored the second against the first.
  A task runner cannot produce that reading, because it only ever knew whether the step
  exited zero.
- **`Store`** — put, vend, get, catalogue. What travels is the METHOD, not the code: a spec
  carries the steps, the goal each is for, and which act on the world, and the consumer
  binds their own implementations. The transferable part of a workflow was never the shell
  commands. Nothing in a spec can execute, and an unbound step raises rather than passing
  silently, so reading a vended workflow is safe in a way installing a package is not.
- Irreversible steps route through `Operator`, so a deploy and a test run are not the same
  kind of thing. A step declared irreversible with no operator is refused, not run.
- **`Nova.follow(workflow, operator=)`** — the seam the package was missing. `Workflow`
  shipped as an island: nova and supercode referred to it zero times. A stored method says
  WHAT the steps are and which cannot be taken back; it cannot say HOW, because a spec
  carries no code. `follow` is what supplies the how — each unbound step binds to the skill
  of the same name, through `use()`, so following leaves the same trace as any other skill
  call. A method travels between people while the doing stays local: two agents can follow
  one released method with entirely different implementations, and both runs are measured
  against the same declared goals, which is what makes them comparable. A step with no
  matching skill raises up front rather than after three steps have already run.

The whole path now composes and is tested as one: an author writes a method and stores it;
a different agent vends it, binds its own skills, and runs it under measurement with the
operator refusing the irreversible step unless a person authorized it.

Three design errors the tests caught before release, each recorded in `workflow.py`:
sharing one harness across a sequence grounds on step one and calls every honest later step
goal-drift; comparing a step's wording to the workflow's cannot distinguish a legitimate
step from a wandering one and no threshold rescues it; and halting on `verdict.drifting`
misses a step reporting circling at Φ=0.82, because warn-then-interrupt verdicts need
history to escalate and a fresh per-step harness has none.

## 0.12.0 — 2026-07-28

**`Operator` — the sixth layer, as something nova can hold.** Named in grammar 1.8.0 the
same day. The other five layers measure, instruct, serve, define and record; this is the
only one that acts on the world, and it is the only one whose failure cannot be corrected.
A wrong reading is re-taken, a lost record rebuilt — a sent message is sent. It fails by
being IRREVERSIBLE, which is the test the grammar already sets for what counts as a layer.

- **`Operator(authorize=...)`** — `act(do, kind=, target=, reversible=, outward=)` runs
  `do` only if the layer's `may_not` clause allows it. Three deliberate choices:
  - **Default is deny.** No authorizer means every irreversible action is refused. The
    alternative puts the burden on the person who is not in the loop, which is the
    situation the layer exists to describe.
  - **Approval never caches.** Every irreversible act asks again, even for an identical
    action approved a moment earlier. Fingerprint caching would let one approval cover a
    repeat nobody saw — a loop deleting a thousand files would ask once.
  - **Refusal is recorded.** Taken, refused or failed, everything lands in `log`. A guard
    that blocked something silently is indistinguishable from one never called.
- **Reversibility is declared, never inferred.** Only the caller knows what the callable
  does; a guard that guessed from a string would be guessing, and guessing in this
  direction is the wrong way to be wrong. Undeclared means irreversible.
- **`Supercode.manage()` now refuses operator work**, checked before anything runs so a
  mixed fleet fails whole rather than half-done. Allocation is a reading; an action is not,
  and a manager that could dispatch irreversible work would be deciding something no
  reading gives it a basis for.
- Not a sandbox, and does not pretend to be: `_authorize` is one line from being replaced
  in-process. Same posture as `ground_intact()` — evidence, not a wall. What it guarantees
  is that this cannot happen by accident, and that when it happens the log says so.

**And the hand: `Operator.shell()` with `classify()`.** An Operator that wraps any callable
is a frame; this is the first concrete thing it drives.

- **`classify(command, reversible=, outward=)` escalates and never relaxes.** A command on
  the known-irreversible list comes back `reversible=False` whatever the caller declared;
  a command matching nothing is returned exactly as declared. The asymmetry is the point —
  a classifier that could talk the guard DOWN would be a way around it, since
  `reversible=True` plus a clever string would open the gate. This one can only ask more
  often than intended, which is the safe direction to be wrong in.
- **`shell(cmd, run=None)`** puts a command through `classify` and then through the gate.
  `run` is injectable so the suite never executes anything — which does mean the real
  subprocess path is the one line here without a test, deliberately: a test that shelled
  out for real would be a test that can delete something.
- **The patterns moved into `grammar.json` (1.9.0), not into this module.** They were only
  in `lasergear/lb_safety.py`, which ships as a Claude Code hook and never reaches the
  wheel. A literal copy here would be a second list that drifts — the failure this
  codebase already recorded: "These numbers used to be typed out in nine places ... A list
  nobody retypes needs no policing." The grammar is canonical, synced across four copies,
  and packaged with the wheel, so the hook and the SDK now read one list. The migration
  script read them out of `lb_safety` at runtime rather than retyping them, so the commit
  that removes a duplicate could not introduce a transcription difference.
- **An authorized carve-out does not downgrade anything.** It means a hook will not
  hard-block the command; it does not mean the person consented to this run of it.

Tested by mutation, not just by assertion. On the gate: three mutations that genuinely open
it are caught by 11, 12 and 2 assertions; a fourth, replacing the default-deny branch,
survived — correctly, since execution fell through to calling `None` and was refused by the
except clause anyway. Redundant guard, not a missing test. On the escalation: removing it
is caught by 6 assertions, removing the outward half by 1.

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
