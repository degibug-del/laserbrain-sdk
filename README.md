# laserbrain

Attach the **smart recursion harness** to any agent loop — a provably-correct,
external check for when an AI agent (or a team of agents) has drifted from its goal.

An agent watching only itself provably can't catch its own drift: each step looks
fine next to the last while it wanders far from where it began. laserbrain is a
**fixed reference** it checks against instead. There's a proof.
[The theorem and the studies (nulls included).](https://phronesis.world/laserbrain/research)
· [Watch it work.](https://phronesis.world/laserbrain/demo)

The check is a pure function, so this SDK runs it **locally and free** — no key, no
latency. Add a key and it also mirrors to the API for retained drift history,
alerts and the fleet view: you pay to *see* your agents drift, not for the check.

```bash
pip install laserbrain
```

See it work before writing any code:

```bash
laserbrain demo          # watch an agent drift off-goal and get returned
laserbrain check --goal "write a poem" --against "build a parser"   # a one-shot drift check
```

## The check (local, free)

```python
from laserbrain import Harness

hz = Harness()                      # add key="lb_live_…" to also retain history
v = hz.check(goal="build the JSON parser", progress="advancing", distance=6)
if v.drifting:
    print(v.reason, "—", v.advice)  # e.g. "goal-drift — your goal no longer matches…"
```

`progress` is one of `advancing | stuck | circling`; `distance` is 0–10 to done.
Reasons: `advancing`, `grounded`, `goal-drift`, `stalled`, `self-report:stuck/circling`,
`ungrammatical`. Want a bounded reading instead of a raw distance? `v.ground_score`
maps Φ to `[0,1]` — `1.0` fully grounded, falling as it drifts (`1/(1+4·Φ)`).

## The grammar — bring your own

The theorem blesses *a* fixed reference, never a particular vocabulary. The default is
frozen and zero-dependency: lowercase, drop stopwords, stem anything over four
characters, then Jaccard. That already handles inflection — "building billboards" and
"build a billboard" score 1.0 and trip nothing.

The gap is **synonyms**. "build the JSON parser" and "construct the JSON decoder" share
only `json` — an overlap of 0.20, under the 0.30 threshold — so a faithful restatement
reads as drift. No amount of stemming fixes that; it needs meaning. Pass `similarity=` and the same theorem runs on a better vocabulary:

```python
from laserbrain.vocab import embedding_similarity   # pip install 'laserbrain[semantic]'

hz = Harness(similarity=embedding_similarity())

# or bring any metric of your own
hz = Harness(similarity=lambda a, b: cosine(embed(a), embed(b)))
```

Only the *goal* term changes — thresholds, the stall rule and the return logic are
untouched, and children from `sub()` inherit it. Omit it and you get the published
instrument, byte for byte. A metric that misbehaves degrades safely rather than
crashing the check.

## The act layer — close the loop

Give laserbrain your step function and it detects drift *and* injects the return, so
the agent recovers instead of spinning. Your step reads `ctx["return"]` and steers back.

```python
def step(ctx):
    if ctx.get("return"):            # laserbrain told us to return to ground
        ...                          # steer the agent back toward its goal
    ...
    return dict(goal="build the JSON parser", progress="advancing", distance=d, done=d == 0)

ctx = Harness().run(step, on_return=lambda v, ctx: print("↩", v.advice))
```

**Async agents** get the same loop, awaited — your step and callbacks may be async,
and the API mirror runs off the event loop so it never blocks. After any run,
`report()` prints the shape of it:

```python
hz = Harness()
await hz.arun(async_step)                 # the act layer for asyncio agents
print(hz.report())
# laserbrain · 11 steps · 1 drift(s)
#   goal: 'build the JSON parser'
#   Φ  ▁▂▃▃▃▃▃▃▅▇█  peak 0.21
#   drifts: stalled×1
```

## Nested recursion — a recursion as a set of recursions

Agents decompose. "Build the parser" becomes "write the tokenizer", which becomes
"handle string escapes" — and each subtask is its own recursion with its own ground.
`sub()` opens one. Every node runs the same proven check against *its own* goal, so a
subtask is judged on its own terms.

What no node can see is the tree. Every agent can report **advancing** on its own
sub-goal while the whole decomposition never brings the root any closer — the same
blindness, one level up. So the set gets its own fixed reference: the root's ground.

```python
root = Harness()
root.check("build the JSON parser", "advancing", 8)
tok  = root.sub("write the tokenizer", distance=4)   # a child recursion, own ground
tok.check("write the tokenizer", "advancing", 2)     # → "advancing" — locally fine
esc  = tok.sub("handle string escapes", distance=3)  # nest as deep as you like

print(root.tree_report())
# laserbrain · recursion tree · depth 1 · 3 recursions · 7 steps
# 'build the JSON parser' · 1 steps
#   └ 'write the tokenizer' · 4 steps
#   └ 'write the AST nodes' · 2 steps
#   ⚑ the TREE is spinning — 6 steps across the set since the root got closer
```

Each node's check is the proven detector; the tree-level signal is a prototype
extension, like the teams below — useful, not a theorem.

## Recursion teams — styled multi-agent oversight

A **recursion team** styles each role's recursion: a `deep` explorer tolerates
displacement, a `tight` checker returns fast. laserbrain runs the team, watches the
shared goal (the fixed reference), and injects the return per role — catching the
**echo/agreement spiral** a self-watching group can't see.

```python
from laserbrain import Team

def agent(role, history, injected):
    # your LLM call for this role; `injected` is a return-to-ground note (or None)
    return position, distance

Team("adversarial-deliberation", goal="…").run(agent)
# presets: deep-search · iterative-refinement · adversarial-deliberation
```

## Oversight, provenance, continuity

**Human-in-the-loop.** A self-correcting return usually takes. When it doesn't —
the agent keeps drifting past `escalate_after` steps — laserbrain escalates *that
drift* to a human. The human doesn't watch every step; they see only what the fixed
reference caught. Their decision overrides the auto-return.

```python
def on_escalate(v, ctx):
    return ask_a_human(v.reason, v.advice)     # Slack, a queue, a webhook — you wire it
                                               # returning a decision injects it as the return
Harness().run(step, escalate_after=3, on_escalate=on_escalate)
```

**Provenance.** Every check is written to a hash-chained ledger — tamper-evident and
verifiable offline, by anyone, no key. Editing a past verdict to hide a drift breaks
the chain at that link.

```python
hz.export_audit("run.json")
from laserbrain import verify_audit
verify_audit(json.load(open("run.json")))      # (True, -1) intact · (False, i) broken at link i
```

**Team continuity.** Snapshot a running team and resume it in a later session — the
shared goal (the fixed reference) and the dialogue carry over, so the group re-grounds
instead of starting cold.

```python
snap = team.snapshot()                         # JSON-safe; persist it anywhere
team = Team.restore(snap)                       # keeps watching the same ground
```

## Calibration — the numbers, on purpose

The instrument's thresholds and weights are one object. `Calibration()` with no arguments
**is** the published instrument; anything else is a choice you are making deliberately.

```python
from laserbrain import Harness, Team, Calibration, PUBLISHED

PUBLISHED.is_published          # True — goal_min 0.30, weights 0.5 / 0.3 / 0.2
strict = Calibration(goal_min=0.60)
hz = Harness(calibration=strict)
tm = Team('deep-search', 'ship it', calibration=strict)   # teams honour it too
```

Weights must sum to 1.0 or construction fails: Φ is reported as a 0–1 displacement, and
weights that sum to anything else silently rescale it. The defaults are pinned by a test,
so changing the published instrument turns the build red rather than shipping quietly.

## Attaching without spelling — inferred state

The harness asks you to spell goal, progress and distance every step. That is the honest
interface and it is also why coverage is low in practice. A runtime already knows which
tool ran, with what arguments, and whether it failed — which is most of `progress`.

```python
from laserbrain.observe import Observer

obs = Observer(goal='ship the sky billboard')      # ground, set ONCE — no setter
obs.record('Bash', {'command': 'npm run build'}, ok=False)
hz.check(**obs.state())                            # goal, progress, distance=None
obs.why()          # 'this call has run 3x in the last 6: Bash'
```

`distance` is **not** inferred — there is no honest signal for "how far from done" in a
tool trace. An unknown distance contributes zero rather than a guess, so **inferred Φ is a
lower bound**: it can under-report drift and cannot manufacture it. The cost is stated
rather than hidden — without distances there is no stall detector, and inferred verdicts
are tagged so they are never averaged with spelled ones.

## Runtime attachment — one implementation, any runtime

```python
from laserbrain.runtime import Session

s = Session('run-42', goal='ship the sky billboard')
s.tool('Bash', {'command': 'npm run build'}, ok=False)   # failures become catches
if (msg := s.nudge()):
    print(msg)                                           # inject into agent context
s.coverage                                               # 0.0 — nothing spelled yet
```

Adapters exist for Claude Code and OpenAI-Agents-shaped events; both are three lines over
`Session.feed()`. Sessions are written in the format `dogfood.py` scores, so recall and
precision need no transcription step.

## Coverage — is it even attached?

```
$ laserbrain coverage

    session                 steps  spelled  inferred  catches  coverage
    2026-07-24                 48        1        44       10       2%

  Below 50%. A detection result cannot be computed from this —
  silence from a harness that was not running says nothing about the harness.
```

Exit codes are the contract: `2` no sessions, `1` below the floor, `0` scorable. The 2%
above is real — ours, on the day the tooling was written.

## Every verdict explains itself

```python
v = hz.check(goal='add caching too', progress='advancing', distance=4)
v.reason   # 'goal-drift'
v.why      # "overlap with the first goal is 0.00, below goal_min 0.30;
           #  first goal was 'build the JSON parser'"
```

A monitor that can only interrupt gets switched off. One that can be argued with gets
trusted.

## Framework adapters

Already on LangGraph, CrewAI, AutoGen, or the OpenAI Agents SDK? Attach laserbrain
without changing your loop. Because it checks a fixed reference, it needs the agent
to *spell* its state — so each adapter takes an `extract` that maps your framework's
state to `(goal, progress, distance)`. **No adapter imports a framework**: each
returns a plain callable you hand to the framework's own hook, so install only the
one you use.

```python
from laserbrain.adapters import guard, langgraph_node, crewai_step_callback, middleware

# generic — wrap any step that returns dict(goal=, progress=, distance=)
@guard
def step(state): ...

# LangGraph — a node that writes the Verdict into graph state; branch on it
g.add_node("laserbrain", langgraph_node(extract=lambda s: (s["goal"], "advancing", s["dist"])))
g.add_edge("agent", "laserbrain")
g.add_conditional_edges("laserbrain",
    lambda s: "return" if s["laserbrain"].drifting else "agent")   # .advice steers the return

# CrewAI — a step_callback that fires each agent step
Agent(..., step_callback=crewai_step_callback(lambda o: (o.goal, o.status, o.dist)))

# anything else (AutoGen, OpenAI Agents, a custom loop) — one check per step
lb = middleware(extract=my_extract)
v = lb(step_output)
if v.drifting: reinject(v.advice)
```

Each adapter runs the check locally and free; pass `key=`/`run_id=` (or your own
`Harness`) to also retain history. The LangGraph path is verified end to end against
a real `StateGraph` — see [`example_langgraph.py`](example_langgraph.py) (`pip install
laserbrain langgraph`): the agent drifts to a different goal, `langgraph_node` catches
it, and the conditional edge routes it back.

## What's proven, and what isn't

The **single-agent** detector mirrors the frozen, published instrument
(`drift.ts @ 6b483de7`) and rests on a theorem: detection is sound and complete, and
no self-monitoring agent can be. The **multi-agent** dialogue and recursion teams are
a prototype extension — useful, not (yet) a theorem. Whether *returning* an agent
keeps the answer as good is [an honest open question](https://phronesis.world/laserbrain/research);
this SDK gives you the detection and the return mechanism, and says plainly what each is.

MIT · [phronesis.world/laserbrain](https://phronesis.world/laserbrain)
