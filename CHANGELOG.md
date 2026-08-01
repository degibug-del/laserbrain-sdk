# Changelog

## 0.40.0 - 2026-08-01

**A catch can now name the reading that was live when it happened, so sensitivity is
computable for the first time.**

`corpus-map.py` printed, for weeks: *d-prime not computable, now or ever, from this
corpus.* That was true about the data and wrong about the word "ever". Nothing about the
world blocked it — a field was missing.

Precision only needs fires, and a fire identifies itself. Sensitivity needs the opposite
case: a moment where something was genuinely wrong and the instrument said nothing. The
only independent evidence of "genuinely wrong" is a `catch` — a non-zero exit, a test going
red, recorded by a hook with no opinion about the instrument. Catches lived in the session
file under one step counter; readings lived in the drift log under another; no shared key.
A catch could not point at the reading it belonged to, so a miss was unobservable.

  · `check_state` returns `run` and `step` — the drift log's primary key, which until now
    never left the process that wrote it.
  · `Session.check()` accepts and records `run`/`run_step`. Both optional: a caller without
    them is an older server, and None must stay distinguishable from a real run so those
    rows can be excluded rather than silently joined to nothing.
  · `verdict_of()` returns them, named `run`/`run_step` so the server's reading number is
    never confused with the session's tool-call number.
  · New `Session.attribute()` — every catch records the live reading plus `since`, how many
    steps back it was. Attribution decays: coverage runs near 24%, so a catch twelve steps
    after the last reading fell in a stretch nothing watched, and scoring that as a miss
    would blame the detector for a step it was never shown. The distance has to survive
    alongside the join or the join is misleading.

Nothing about the measurement changed. No threshold moved, no verdict was added or removed,
and drift vectors from 0.39.0 remain comparable.

Tooling shipped alongside (in lasermind, not the package): `sensitivity.py` computes the
second row of the detection matrix and withholds d' until n supports it; `replay.py` scores
the grammar against externally-labelled traces; `server_probe.py` lets conformance tests ask
the running server instead of scraping its source.

## 0.39.0 - 2026-08-01

**laserbrain measures the same way for every agent, and now says so. No vendor is named in
any logic, any user-facing string, or any test.**

The instrument had one particular pair of hosts compiled into it. Not as configuration —
as branching. `agent_of` and `session_id_of` enumerated two vendors' env vars and returned
the matching brand; `check_howto` branched on `if me == 'grok'`; `is_grok` decided an
injection path. An instrument shipping a list of which agents exist has to be edited to
measure a new one, and that list is a claim about the world that goes stale.

  · from_claude_code and from_grok were BYTE-IDENTICAL apart from the docstring. The
    spelling difference they appeared to handle is absorbed by session_id_of and
    normalise, which read both. One `from_hook` now; both names kept as aliases.
  · agent_of / session_id_of: LASERBRAIN_AGENT and LASERBRAIN_SESSION_ID, declared, then a
    fallback that cannot be wrong.
  · check_howto: a table in lasergear/hosts.json. Hosts DO differ in how a tool is invoked
    and that difference is real — it is configuration, not logic.
  · is_grok -> camel_shape. It always tested payload spelling, never identity, and two
    hosts can share a convention.
  · every MCP tool description that said "Claude and Grok". A description is read by
    WHATEVER agent is connected; naming two others tells a third it was built for
    somebody else.

THE OBVIOUS REPAIR WAS WORSE THAN THE BUG, twice, and both are worth recording.

First: replacing the hardcoded env pair with a scan for any *_SESSION_ID, longest key
first. This machine carries CLAUDE_CODE_SESSION_ID (the agent) and
CLAUDE_CODE_HOST_SESSION_ID (a browser pane) — the scan picked the browser. The old code
checked a variable that does not exist here and harmlessly fell through to the parent-pid
fallback; the "improvement" made it confidently choose a wrong session id, which merges
runs and misattributes catches. test_runtime.py caught it.

Second: a blanket rename of fixture names in the tests reclassified corpus-map's
self-marked labels as independent, because its STRENGTH keys were real values that had to
match the `by` field. Strength is now DERIVED — a label is self-marked when `by` equals
the row's `agent`, whoever they are — which is better logic than the list it replaced.

Same error each time, one level down from the last: the original guessed a vendor from an
env var, the first fix guessed a session from a variable's NAME, the second guessed that a
string was cosmetic. A shape is not an identity, a name is not a session, and a value that
must match data is not a label.

WHAT STAYS: ~/.claude/laserbrain, the corpus path. It holds 1000+ readings and every
session record; renaming it orphans all of that for a cosmetic gain. It is a location, not
a claim about who may write there, and each occurrence now says so.

## 0.38.0 - 2026-08-01

**A declared `parent_goal` that fell below the floor was received, measured, rejected, and
never mentioned. The verdict then told the agent to pass `parent_goal` - which it had just
done. That is why `excursion` had never once fired.**

In 1008 readings the field was spelled 3 times and `excursion` fired 0 times. It looked
like an adoption problem for weeks. It was not, and the diagnosis reversed twice before
landing:

  · NOT awareness. The goal-drift advice already said "If this is a sub-task, pass
    parent_goal" on every one of the 181 fires.
  · NOT a stale ground. `reground` updates `first_goal`, so the parent was being compared
    against the live ground correctly.
  · All 3 declarations were REJECTED for falling below goal_min - overlaps of 0.03, 0.04
    and 0.17 against a 0.30 floor - and every rejection was silent. The verdict came back
    as plain goal-drift, whose advice then repeated the instruction the agent had already
    followed.

An agent that declares a parent, is silently ignored, and is then told to do the thing it
just did learns the field does not work. Adoption at 0.2% was a taught response, not
neglect.

Now: a rejected declaration is named with the number that decided it, `Verdict.parent_overlap`
carries that number, the drift log records it, and the advice never repeats an instruction
the agent already followed. `excursion` fires correctly when the parent holds. Mirrored in
lasermind/mcp-server.mjs, and the two agree on identical input.

THE THRESHOLD IS NOT TOUCHED, deliberately. On those 3 rejections, containment rescues one,
child-in-parent rescues a different one, and neither rescues the third. Three points cannot
choose a replacement measure, and moving a published calibration on an anecdote is the
mistake the corpus work exists to prevent. Recording `parent_overlap` is what will generate
enough rejections to settle it properly.

Found by executing edge cases rather than reading them: `_rejected_parent` was only ever
SET inside the parent block, so a later call that declared nothing inherited the previous
step's rejection and reported an overlap for a declaration never made - collapsing the one
distinction the field exists to draw, that None means no declaration and a number means one
was made and rejected. Cleared unconditionally now, and pinned by a test.

## 0.37.0 — 2026-08-01

**`check()` was 155x slower than it needed to be, and the cost was a blocking network POST
commented "best-effort". The mirror now runs on an ordered background worker.**

Profiling put 96% of a keyed `check()` inside `urlopen`: ~135 ms per call against 869 us
keyless, with an 8-second timeout as the worst case. A side-channel on the critical path
of the measurement it mirrors is not best-effort, it is a dependency, and a hung network
would have become the instrument's own worst case.

Nothing in the verdict depended on it — the return value was discarded — so it belongs on
a thread. `MIRROR` is one module-level worker draining one bounded queue, and each of
those words is load-bearing:

  ORDERED. The Worker's /v1/drift does not merely store rows: it calls `checkStep(prev,
  body)` and reconstructs the run's state server-side, trace and cycle detection included.
  Out-of-order arrival would corrupt that reconstruction, which is worse than being slow
  because it would be silently wrong. One worker posts synchronously and waits, so
  request N completes before N+1 is sent — order holds end to end, not merely at enqueue.

  BOUNDED. 256 deep; a full queue drops the OLDEST and counts it. An unbounded queue is a
  memory leak inside the thing that was supposed to cost nothing, and dropping the oldest
  keeps the recent history, which is the part anyone reads.

  UNABLE TO REACH THE CALLER. Daemon thread, so it can never hang a process, plus an
  atexit drain with a short bound. A mirror that raises must not break a measurement.

Measured after the change: 1152 us per keyed check against a stub that sleeps 20,000 us,
with delivery order verified as [9,8,7,6,5,4,3,2,1,0] arriving exactly as sent, and 400
sends into a wedged network shedding 144 rows rather than growing. `test_mirror.py` pins
all four properties.

`/v1/escalation` stays synchronous: it reads `esc_id` off the response and genuinely needs
the round trip. Only the two posts that discarded their return moved.

CHANGED SEMANTICS, stated plainly: mirrored rows were guaranteed-but-slow and are now
fast-but-droppable. Under an outright network failure they were already lost — the
synchronous `_post` swallowed the exception and moved on. What is new is loss when the
network is merely SLOW, once ~25 seconds of backlog accumulates. A normally-paced agent
will never reach that; a tight loop against a degraded network will. Since the server
reconstructs from the stream, a dropped row leaves a hole in its trace rather than merely
missing data.

## 0.36.0 — 2026-07-31

**The window is configurable, because it is a frame and not a setting. `Search(window=N)`
moves the instrument; `temperature(window=N)` reads another frame without moving it.**

Temperature landed in 0.35.0 with the window fixed at the published calibration, and the
open question was left sitting in the docstring: nothing says which window is correct.
Measuring it made the question concrete. One trail, read at windows 2, 3, 4, 6, 8 and 9,
gives 0.42, 0.28, 0.46, 0.64, 0.60 and 0.65 — a 2.3x spread on identical data, and NOT
monotonic in the window. Narrower is not colder. The reading depends on how wide the
window is AND on where it lands relative to the structure of the trail, so there is no
single parameter to transform between frames with. What every frame agrees on is the
novelty sequence, the ground count and the territory. `territory()` reports those, and now
reports the frame beside the number, because a temperature quoted without its window is
not a reading anyone can reproduce or compare.

The two operations are deliberately separate. `temperature(window=N)` computes what
another frame would see and changes nothing — an observer can do that without moving.
`Search(window=N)` moves the instrument, and that is a CALIBRATION CHANGE rather than a
display option: `settled`, `narrowing` and `thrashing` all read the same window, so a run
at window 6 is not comparable to a run at window 4, nor to the corpus. The test proves it
rather than trusting the docstring — the same trail ends `settled` at window 4 and
`searching` at window 6.

Windows below 2 are refused in both places. A window of 1 makes temperature the novelty of
a single ground, which is precisely the category error the measure exists to refuse: one
ground has a novelty and does not have a temperature.

Found by executing the parameter rather than reading it: `Search(window=2.9)` silently
truncated to 2. A frame quietly rounded down is a wrong answer with no symptom, and the
frame moves the reading by 2.3x — so a caller passing a computed `n/2` would have been
reading a frame they never asked for, with nothing to notice it by. Non-integers are now
refused with a message naming both neighbouring frames; a float that is already whole
(4.0) is accepted, since that is the same frame written differently. Strings and bools are
refused rather than coerced.

## 0.35.0 — 2026-07-31

**`Search.temperature()` — how energetically the search is moving, as a number rather
than a boundary. The first reading in this package that is undefined for a single
observation rather than merely small.**

The explore instrument already computed a novelty per ground and already thresholded that
distribution at its EXTREMES: `settled` fires on `max(window) <= SETTLED_MAX`, `narrowing`
on the first value against the last. Nothing reported the middle, and the middle is a
different fact — a window holding one very hot ground among cold ones reads `narrowing`
with a maximum of 1.00 while its mean novelty is 0.38. Neither extreme can say that.

Temperature is not a property a component can have. No single molecule has one, and
asking for the temperature of one particle is a category error rather than a hard
measurement. The same holds here: one ground has a novelty and does not have a
temperature — only a path does. So this returns None until the window is full, and that
None means UNDEFINED, not zero. It is the same distinction `claims['grounded']` draws
between "read nothing" and "read only claims", and it is drawn for the same reason: a
number reported where none exists is a fabricated finding.

Reported and decisive in nothing. `test_explore_temperature.py` runs four trails twice —
once normally, once with `temperature()` forced to None — and compares every `reason`,
`novelty`, `revisit` and `advice`. All identical. Had one moved, the reading would have
stopped being a report and become a rule, and the published calibration behind those
rules would silently no longer be the published one. No new constant, no grammar change:
it is derived from novelty, which the instrument was already computing and discarding.

Worth recording because the test caught it and not the reasoning: a search that has gone
completely still reads 0.25 after four identical grounds, not 0.0. The window is four
wide and the OPENING ground genuinely opened new territory, so it stays hot inside the
window for four steps — [1.0, 0, 0, 0]. The first version of the test asserted 0.0 and
was wrong about the instrument rather than finding a fault in it. Both facts are now
pinned: 0.25 while the opener is in the window, exactly 0.0 once it clears.

## 0.34.0 — 2026-07-31

**One phrase list, two readers. `ceiling`'s patterns now live in `grammar.json`, and
`lasermind/mcp-server.mjs` runs the same marker in JavaScript — proved by a conformance
test that drives the real server rather than a copy of it.**

0.33.0 shipped the marker with its lists as Python literals, and a note saying to promote
them the moment a second implementation wanted them. That happened: the local MCP server
now reads them too and reports `claims` on `check_state`. So the lists moved to the
grammar (1.21.0), which is the rule `operator_patterns` already set — a list stays local
until two things need it, then it goes canonical rather than becoming two lists that drift.

`test_ceiling_conformance.py` is what makes that a fact rather than an intention. One list
with two readers still lets the readers disagree about what reading it means — a different
regex assembly, a different tie-break, a different answer for "nothing matched" — which is
exactly how the normaliser once scored the same goal pair 0.46 in the server and 0.56 in
the SDK, each reading its own copy with nothing checking. It speaks MCP to the real
`mcp-server.mjs` over stdio and compares its `claims` against the SDK's `mark()` across
randomised inputs, including every case where the two languages spell "nothing" differently
(`None` vs `null`, both falsy).

Fixed before shipping, and the most dangerous thing in this release: **empty pattern lists
compiled to a valid regex that matched everything.** If `ceiling_patterns` were ever absent
from the grammar, `\b(?:()|())\b` matches the empty string at every word boundary —
sixteen phantom cause-claims on one ordinary sentence, returned as a confident
`grounded: 0.0` about text containing no claims at all. No error, no crash, a wholly
fabricated finding. `_compile()` now returns None on empty lists and `mark()` reports the
honest answer, which is that it read nothing. The MCP server's normaliser has carried a
built-in floor against this exact trap for months, with a comment reading "a fallback that
degrades to nothing is not a fallback"; that comment was read, quoted, and then not applied
here on the grounds that the grammar always ships. It does — but the failure is silent when
it doesn't, and silence is the one thing this instrument is not allowed to be.
`laserbrain.ceiling.AVAILABLE` now says which state you are in, since `mark()` alone cannot
distinguish "no patterns to read with" from "nothing matched".

## 0.33.0 — 2026-07-31

**The harness could say whether observed work backed a claim. It could not say whether
the agent was CLAIMING or REPORTING in the first place. `ceiling` reads that off the
agent's own words, and `check()` finally accepts the free-text fields the grammar has
declared since the beginning.**

`anchored` measures how much of Φ rests outside the agent's account of itself, and its
`corroborated` rule already names the failure: "an agent reporting `advancing` with a
falling distance and no successful work behind it is making a claim with nothing under
it." That is a cause-claim, caught through events. `laserbrain.ceiling` catches the same
thing through language — available a step earlier, and available at all when no event
evidence will ever exist. The distinction is Nisbett & Wilson (1977), and it is the same
one the browser instrument at phronesis.world/field/ceiling has been drawing for people.

It is a SECOND signal, not a replacement, and the tests exist to prove that rather than
assert it: at identical `anchored`, an agent that ran nothing but wrote pure observation
reads 1.0 and one whose tests passed but who writes "this should fix it" reads 0.0. They
disagree in both directions. Like `anchored`, it is reported and NEVER folded into Φ —
`test_ceiling.py` pins that Φ and the verdict are byte-identical with and without it.

`Harness.check()` now takes `doing`, `next` and `blocked`. grammar.json has listed all
four carried fields from the start and this signature accepted exactly one of them
(`parent_goal`); the hosted Worker accepted all three and read none. So agents have been
spelling them into a slot that dropped them. They are keyword-only, they do not touch Φ —
Φ is defined over the three fields that can be spelled canonically — and what they now
feed is the marker.

Known and declared rather than discovered later: the marker is a regex over a fixed
phrase list. It reads "since" in both its causal and temporal senses and cannot tell them
apart, it misses paraphrase, and it marks language and not truth. A low score is a prompt
to look, never a finding. `claims['grounded']` is `None` when nothing matched and `0.0`
when everything matched was a claim — **both are falsy, so test it with `is None`**; a
truthiness check merges the two, which is why `scores` omits the key rather than carrying
a number for it.

Two traps found by executing an audit rather than reading the code, both now pinned by
tests: `doing` was reachable as a ninth positional argument (now keyword-only), and the
None/0.0 collapse above.

Not shipped, deliberately: the phrase lists were briefly promoted into `grammar.json` and
moved straight back. A list belongs there once a SECOND implementation needs it — the
rule `operator_patterns` set. Exactly one reader exists today, and the premature promotion
turned the site build red on a grammar version the deployed Worker did not have.

## 0.32.0 — 2026-07-31

**`phronesis()` could tell you a run was not worth continuing, and nothing acted on it.
`Operator` now refuses to take an irreversible or outward action while the run itself is
judged `abandon`, `wrong-problem` or `repeating` — not just while the latest step is
drifting.**

The existing sixth join reads `harness.last`: one step, the most recent reading. A run
can be twelve checks into work that never closed the distance and still have its twelfth
step read as locally fine — same goal, honest `advancing`, a clean Φ — which is exactly
the case a one-step gate cannot see and `phronesis()` was built to catch. `Operator.act()`
now consults both, automatically whenever a harness is wired, with its own counter
(`blocked_by_judgment`) so a refusal on a bad run is distinguishable in the log from a
refusal on a bad step. `narrow` and `verify` stay advisory — they say the goal is too big
or the self-report disagrees with the trace, not that acting right now is wrong. No added
network cost: `phronesis()` reads data `check()` already collected.

Found while wiring it: `publish.sh` ran ten of the suite's thirty-one test files, named
by hand in a loop nobody had updated since. `test_operator.py`, `test_operator_harness.py`
and `test_nova.py` — the tests covering the exact join this release changes — had never
once been run by the release gate. It now discovers every `test_*.py` rather than
enumerating them.

## 0.31.0 — 2026-07-31

**The instrument could say how far you were from ground and never whether the journey was
worth making. `phronesis()` answers the second question — and the four defects found
auditing it before release were all in code that already passed its tests.**

An agent can hold a perfect goal score, report `advancing` honestly, sit at Φ=0.05, and
be twelve checks into work that has not moved the distance once. Every verdict in the
harness calls that *advancing*, because by its own definition it is. `phronesis()` reads
the same trace and returns `finish`, `continue`, `narrow`, `verify`, `repeating`,
`wrong-problem` or `abandon`, with the evidence it judged on. It is deliberately willing
to say abandon; an instrument that can only ever counsel continuing is offering
encouragement, not judgment.

`goal_score` is now on every `Verdict`, with `scores` beside it. It has been computed
since the beginning and reported only on failure — interpolated into the advice *string*
at the moment it crossed the floor, invisible at every other step. The one number saying
how far the SUBJECT had travelled could only be read once it had already gone too far.

`context_id` names the work itself. The token set a laserscore renders was already a
fingerprint — it is why "build the parser" and "building a parser" do not score as drift
— and it was computed, printed once and discarded every step. Stored, it gives the
instrument memory across sessions, which is what judgment needs and measurement does not:
Φ can say you are 0.3 from ground; only history can say you have opened this context four
times and closed it none. Byte-identical to the server's `contextId`, verified across
processes and languages.

Holding both at once yields `repetition`, which neither gives alone: how many times this
*exact* state has been written in this context. A stronger claim than `stalled` — distance
sits flat through legitimate sub-work, but an identical laserscore means goal, progress
AND distance are all unchanged. Threshold from the corpus, not taste: ≥2 fires on 9.7% of
382 contexts and is noise, ≥3 on 2.6%.

**Calibration.** The verdicts first shipped with thresholds reasoned out and never tested,
which is not the standard every other rule here is held to. Replaying all 141 recorded
runs found three defects reasoning had missed: `wrong-problem` fired on a run that closed
5→1, `narrow` told runs sitting at distance 1 to break the goal into smaller pieces, and
two-check runs were handed hard verdicts on a trace with nothing in it. After: hard
verdicts landing on runs that closed ≥2 distance went from several to zero.

**Pre-publish audit.** Four defects in the context store, each found by measuring rather
than reading:

- Eight concurrent writers recording five checks each stored **36 of 40**. Every writer
  read the whole map, edited its entry and wrote it back over everyone else's. Silent
  undercounting is the worst failure available here — `repetition` raises the `repeating`
  verdict, so a dropped write suppresses a judgment that was true. Now taken under an
  `O_CREAT|O_EXCL` lockfile, the same primitive as Node's `wx`, so the package and the MCP
  server exclude *each other* rather than each locking alone. 40/40 with eight Python
  writers, and again with four Python and four Node racing on one file.
- The sessions list grew without bound, and the whole map is read and rewritten on every
  check — so it cost time on every future check, permanently, in a file written into every
  user's home directory. One context had already reached 88 ids. Capped at 20, with the
  true total in `session_count`.
- Capping would have broken `abandon`: `prior_runs` read `len(sessions)` and would have
  quietly stopped counting past twenty, weakening the verdict precisely on the
  longest-running contexts it exists to catch.
- `run_id` was a millisecond timestamp, so thirty runs built in a loop produced fourteen
  distinct ids — a context opened thirty times reported thirteen, and "opened in N earlier
  sessions" was simply false. `uuid4` now, matching the server.

**What lands on disk.** Contexts persist to `~/.config/laserbrain/contexts.json`, beside
the drift log already written there. Stemmed goal tokens, laserscores, timestamps and
counts — not raw prose, but enough to reconstruct roughly what you were working on. Local
only, never transmitted; delete the file to forget everything.

`context_id` joins `__all__`, which `laserscore` already was — the same tier of concept,
and one being public while the other was not was an accident.

## 0.30.0 — 2026-07-30

**The store reaches every surface now, and the gate that's supposed to prove the tests
watch anything was mostly checking dead code.**

`./mutate.sh` mutates the calibration constants and asks whether the suite notices. It
did not, for four of six: a 2026-07-28 refactor moved the real values into
`grammar.json`, and the Python literal the script was editing had become a fallback for
a key that's never missing — dead code, unreachable by construction. A hardcoded
11-file `SUITE` had also quietly stopped covering 19 of the 30 test files in the repo,
`test_operator.py` and `test_mcp_server.py` included. Fixed both, plus a third bug the
fix itself exposed: `echo_min`'s mutation passed standalone and survived inside the
tight restore-sed-run loop, because the loop landed inside one filesystem mtime tick
and Python reused a stale `__pycache__` bytecode from before the edit. All six
mutations are now caught in both normal and `--deep` mode, for real.

`test_behaviour.py`'s echo-floor case had the same shape of problem one level up: every
other section reaches the true shipped default through `cal=None`; this one only ever
constructed `Calibration(echo_min=0.25)` with a literal the test chose, so a moved
default would never have been noticed behaviourally. Added the missing case.

`uvx laserbrain mcp` resolves to the newest release on PyPI regardless of what a
registry entry's own `version` field claims — proved live, since `uvx laserbrain mcp`
and `uvx --from laserbrain==0.28.0 laserbrain mcp` already disagree now that 0.29.0
exists. `server.json` now pins the exact version with a `runtimeArguments --from`, so
this entry keeps meaning what it says once something newer ships. Registry entries are
immutable, so this takes effect starting with this release, not retroactively.

**The store vends recursion-team presets now, not just task workflows** —
`list_teams` / `vend_team` / `get_team` / `find_team` / `catalogue_teams`, one door,
two shapes, because a workflow runs its steps once in order and a preset cycles until
it converges, and role names like `explorer` fail the workflow spec's own verb
dictionary honestly rather than being coerced into it.

**The store reaches Python, MCP, and the terminal now — before this release it was
Python-only.** `store_list` / `store_find` / `store_vend` over MCP, `laserbrain store
[list|find|vend]` on the command line. Most agents reach this package over MCP, not
`import laserbrain`, which is the same reasoning `mcp.py` already gives for existing at
all; the store shipping with no MCP or CLI surface reproduced that gap one layer up.

Two more workflows — `new-repo`, `repo-surgery` — promoted from a local-only shelf to
shipped, after checking each of six candidates for whether it's an actually generic
pattern or tied to this project's own tooling. Four stayed local (`deploy`,
`grammar-bump`, `release`, `research-note`) rather than being genericised into
something weaker for marginal benefit to a stranger who has to rewrite every step's
binding regardless. 10 workflows ship now, up from 8.

## 0.29.0 — 2026-07-29

**Claim detection, not cure.** No code changed. This release exists because the page every
new user lands on made a claim three preregistered studies did not support.

The act-layer section said the return means *"the agent recovers instead of spinning."*
**Recovers** is a cure word. What is measured is that the return **cuts steps**. Whether it
keeps the answer *as good* is **not established** — tested three ways, each frozen before it
ran, and where the evidence is legible it leans the other way. Fewer steps is also not fewer
tokens, a caveat the research page carries and the README did not.

The research page has always held this line: κ = 0.10 on the judge panel, balanced accuracy
0.55 with a confidence interval that includes chance, one answer key that was simply wrong,
and the rule stated outright. Two other surfaces claimed past it, and a claim is only worth
the boundary printed next to it.

Both now link to [the studies, nulls included](https://phronesis.world/laserbrain/research)
from the point the claim is made rather than from the top of a different page.

Found by auditing the one category of public claim that had not been checked — prices, tool
lists and deployed versions all had gates by then; the scientific claims had none.

## 0.28.0 — 2026-07-29

**The README described a product two generations old, and it is the PyPI page.**

It mentioned `laserbrain mcp` zero times, `modulate` zero times and `Operator` zero times.
The single biggest thing this package does — that `pip install laserbrain` gives any agent
the harness over MCP, offline and free — was stated nowhere a stranger would encounter it.
No code changed in this release; what changed is that the page now says what the code has
done since 0.25.0.

The MCP path is second on the page now, after the theorem and before the Python API,
because most agents cannot `import laserbrain`. Four lines of JSON and an agent has a fixed
reference. Two new sections cover what previously existed only in this changelog:
modulation (same verdict, opposite action by role) and the hands (a drifting agent cannot do
what it cannot undo).

**A pricing claim was corrected because today made it false.** The page said *you pay to see
your agents drift* and listed retained history as the paid half. The SDK writes every
session to disk and keeps it forever, so that was charging for something the client already
has. What a key buys is a PLACE: awake while you sleep, readable by a colleague's laptop,
able to notice a second agent deploying the same thing.

**And an `mcp-name:` marker, for the official MCP registry.** The registry reads it off the
PyPI description to verify that whoever publishes the registry entry also controls the
package, which is why it has to ship in a release before the listing can be created.
`server.json` accompanies it in the repo.

Every example on the page was verified against the PUBLISHED package rather than the tree —
the seven tool names, the modulation shape and its `basis` string, the operator refusal
verbatim including Φ=0.53, and that an unknown team errors instead of silently going
unstyled.

## 0.27.0 — 2026-07-29

**`laserbrain mcp` gains `modulate`, and grammar 1.19.0 is what made it possible.**

    modulate(goal=…, progress='stuck', distance=5, team='deep-search', role='explorer')
    # {"reason": "self-report:stuck", "modulation": {"return": false,
    #  "basis": "explorer recurses deep"}}

The policy table — the eight drift modes, the three recurse depths, the recursion-team
presets — lived only in the Worker's TypeScript. That is why modulation could be served
there and nowhere else: adding it to a local server meant copying the table, a fourth copy
of a list this project has already watched drift twice. `grammar.modulation` is canonical
now and three implementations read it, so the offline server answers exactly what the
hosted one does: `explorer(deep)` tolerates `self-report:stuck`, `checker(tight)` returns
on it.

**WHY THIS IS A VERSION AND NOT PART OF 0.26.0.** It was meant to be. The 0.26.0 wheel was
built at 19:06, `mcp.py` changed at 19:10 and `grammar.json` at 19:13, and the upload went
out before the rebuild — so the published 0.26.0 carries the Operator joins and ships
grammar 1.18.0 with no `modulate`. PyPI versions cannot be overwritten, and a changelog
entry describing an artifact nobody can download is worse than a second version, so the
claim moved here where it is true.

That is the 0.12.0 failure a third time: a wheel built before the source finished, where
the tree is right and reading the tree proves nothing. It was caught by installing the
PUBLISHED package and comparing byte sizes — 126,052 on PyPI against 128,895 locally.

## 0.26.0 — 2026-07-29

**The sixth join: the hands consult the instrument before doing something final.**

    hz = Harness('build the parser')
    op = Operator(authorize=ask_me, harness=hz)

    hz.check('write documentation instead', 'advancing', 4)   # drifted
    op.act(deploy, kind='deploy', target='prod')
    # Refused: the agent is off its ground (goal-drift, Φ=0.53) — return before
    #          acting irreversibly.

Until now the harness could say *return to your goal* and the agent was free to deploy
anyway, because advice is advice. The one layer whose whole job is doing things to the
world had never heard of a verdict: `operator.py` contained no reference to the harness,
and the hosted Worker contains no operator at all. Detection reached policy in 0.25.0 and
stopped there.

**It reads `harness.last`; it does not call `check()`.** An operator has no goal, no
progress and no distance to spell. Inventing them would be the operator marking its own
homework — the exact failure a fixed reference exists to prevent. So `Harness` now retains
its last `Verdict`, and the operator reads it.

**The consult happens BEFORE the authorizer, and the ordering is the substance.** Asking a
person to approve an irreversible act by an off-goal agent is precisely when a person
rubber-stamps: the request looks reasonable in isolation, because every drifting step does.
The drift is only visible against the ground. A test asserts the authorizer is never called
while drifting.

**No reading is not a good reading.** An operator wired to a harness nobody has checked
knows nothing about the agent asking it to act, and spending "nothing" as "fine" is the
failure this instrument is named after. It refuses, and says so.

**Only for what cannot be taken back.** A drifting agent may still read a file. If drift
blocked everything, the first thing anyone would do is unwire the harness — and an operator
that refuses everything is not safe, it is broken.

**And the half no single machine can do.** `Operator(key=…)` also asks the hosted service
before an irreversible act, and the question is one a laptop cannot answer:

    A: allow=True   clear
    B: allow=False  duplicate — another agent in this group started deploy on prod at 02:05

Two agents, each perfectly grounded, each advancing, each correct at every step, both
deploying prod. That fault exists only as a relation between them and is invisible from
inside either. The server cannot hold anyone's hands — the agent runs on someone else's
computer — but the LOCAL operator does enforce, so the answer has teeth.

**It fails open, loudly.** If the service cannot be reached the act proceeds, because a
network blip must not stop a deploy the local instrument already cleared. The consult
returns None rather than an allow, and None is deliberately distinct: "we did not ask" and
"we asked and it said yes" are different facts about an irreversible action. The endpoint
reports the same way — `checked: {drift, group}` says what actually happened, because an
allow that skipped both looks identical to an allow that passed both.

Entirely opt-in: `Operator()` without a harness or key behaves exactly as before.


`test_operator_harness.py`, twelve cases, including the ordering claim and the boring one
that matters most — that a grounded agent can still act.

## 0.25.0 — 2026-07-29

**`laserbrain mcp` — the harness as an MCP server, offline, from the pip package.**

    pip install laserbrain
    laserbrain mcp          # JSON-RPC on stdin/stdout

Point any MCP client at that command and the agent has the harness. No key, no network, no
account, nothing to sign up for.

Until now `pip install laserbrain` gave a library and a CLI, and the only way to reach the
instrument over MCP was the hosted Worker. The stdio server the author actually uses is a
Node file living on one machine, distributed to nobody — so the way laserbrain is used by
the person who wrote it was the one way a user could not use it. For a tool whose headline
claim is that the check is local and needs no server, that was backwards.

Most agents cannot `import laserbrain`. They speak MCP. This makes "free and offline" true
for agents rather than only for Python programs.

**No dependency.** MCP over stdio is JSON-RPC in newline-delimited JSON, which is `json`
and `sys.stdin`. An SDK would have added a dependency to a package that has none, for a
protocol that fits in one file. Six tools: `check_state`, `reset_task`, `get_history`,
`similarity`, `laserscore`, `capabilities`.

**It exposes only what works unplugged.** The field, Alice, the spectral grammar and the
persisted self are real capabilities and every one is a call to a server. Offering them
here would produce an MCP server that fails the moment it is used as advertised. They stay
on the hosted Worker, which is honest about being a server, and `capabilities` says so in
as many words rather than leaving a user to find out by failure.

`test_mcp_server.py` drives it as a real client does — through a subprocess, over pipes,
because an in-process test cannot catch a stray print corrupting the stream. Fourteen
cases, including the one that matters: with `socket.socket` disabled outright it still
answers, and the verdict is real rather than a stub.

## 0.24.0 — 2026-07-29

**`laserbrain key` — one command from install to a working key.**

The README has told every reader since the first release: *add a key and it also mirrors
to the API for retained drift history, alerts and the fleet view.* The package has never
said how. `POST /v1/keys` takes an empty body, needs no auth and answers instantly — the
only thing standing between a reader and the hosted half was knowing that endpoint exists.

On 2026-07-29 the gap had a number on it: about 6,000 downloads, and twelve keys ever
issued against the API, two of them from that afternoon's testing. One account.

    laserbrain key           # a free key, saved to ~/.config/laserbrain/key

It prints the limits the API reports rather than the ones the docs claim, because those
are two sentences that can drift apart and only one of them is enforced. It says what
stays free without a key — the check itself, which is a pure local function — because a
signup flow that implies the product needs an account would be a lie about this product.

**The other half: the SDK now reads the key it writes.** `stored_key()` resolves the
environment first, then the file. Without that, `laserbrain key` would have written a
credential into a file nothing loads, and every hosted call would go on quietly
unauthenticated — which looks exactly like not having run the command. The four call
sites in `services.py` that read `LASERBRAIN_KEY` directly now go through it.

The key is written `0600`, created with that mode rather than chmod-ed afterwards, since
between the write and the chmod it would exist at whatever the umask allows. Re-saving
over an existing loose file tightens it back.

**A blank environment variable was a bug the test caught on its first run.** `export
LASERBRAIN_KEY=` leaves an empty string, and a stray space leaves `"   "` — both truthy.
Testing the value before stripping it returned `None` while a perfectly good key sat in
the file, so the user would have a key on disk and an SDK behaving as though they had
none, with nothing anywhere to indicate why. Strip first, then test.

`test_key_command.py` covers thirteen cases with the network replaced, including the two
that are silent when wrong: that both halves name the same path, and that a second run
does not mint a second key. A key IS the identity, so minting another would strand the
first one's history while printing success.

## 0.23.0 — 2026-07-29

**About a third off import, by not loading a network library the free check never uses.**

Measured before changing anything, and the first hypothesis was wrong: `grammar.json` has
grown from 1.7.0 to 1.18.0 and is parsed on every import, but `json.loads` of the whole
57KB file costs 0.07ms. Irrelevant.

The hot path needed nothing either. `Harness.check` is **0.0147ms** — about 68,000 checks a
second — and `norm()` is 0.0009ms. There was no optimisation to make there, which is worth
saying plainly rather than optimising something to look busy.

The real cost was import, and it was `urllib.request`: imported at module level by
`__init__`, `field` and `services`, and never touched by the free local check, which is the
headline feature. `operator.py` already imported it lazily inside its own function, so the
pattern existed and had simply not been applied at the top.

Now lazy in all three. Measured by installing 0.22.0 and 0.23.0 from PyPI into separate
venvs and timing 25 cold starts of each, interleaved so thermal and load drift hit both
runs equally, minus interpreter baseline:

    import cost, min     0.22.0  22.7ms     0.23.0  15.1ms     33% faster
    import cost, median  0.22.0  23.0ms     0.23.0  15.7ms     32% faster
    -X importtime        0.22.0  22,246us   0.23.0  13,982us   37% faster

`urllib` no longer appears in the trace at all — five lines and 7,799us, gone. The
`-X importtime` figure is higher because it attributes to the module some cost the
end-to-end timing counts as interpreter startup; the ~32% is the one a caller feels.

The network paths were verified rather than assumed: an operator `GET` returns 200 with
61KB, importing urllib on demand at the call.

**A first measurement said 0%.** Both venvs were being timed with the working copy as cwd,
and cwd precedes site-packages on `sys.path`, so both runs imported the same local tree and
tied exactly. A tie is what a correct null result looks like too; it was only caught because
the check printed the version it had actually imported, and the venv holding 0.22.0 said
0.23.0.

**`Operator.http()` had a kwarg trap.** `**kw` forwards to `urllib.request.Request` for
headers and data, so passing `reversible=` or `outward=` — which the docstring says to pass
through `act` instead — fell through and died as `Request.__init__() got an unexpected
keyword argument 'reversible'`, several frames deep, reading like a urllib bug rather than a
misuse. Found by calling the method the way its name suggests. It now raises immediately and
says where those arguments belong.

## 0.22.0 — 2026-07-29

**Ships grammar 1.16.0.** 0.21.0 carried 1.14.0, so a `pip install` got a grammar two
versions behind the canonical one — missing the method space (1.15.0) and the directory of
maps plus the `ground` disambiguation (1.16.0).

Nothing was broken by it: both additions are documentation sections, and the `pattern` that
`lint()` actually executes shipped correctly in 1.14.0. But the wheel and the canonical file
disagreed, which is the exact condition `check-laserstore` exists to catch, and it fails the
next site build.

This is `stale-verify` — the rule added in 0.18.0 — committed by me for the third time in a
day: a change landed after the artifact was built, so the artifact fell behind the source.
The rule catches it in a *method*; nothing catches it in a habit. What the grammar now
carries that the last published wheel did not:

- **`dictionary.phases.method_space`** — a workflow is a shape plus a verb at each position,
  so the method space is the shape language crossed with the verb assignments: 3,418,642
  methods up to length 9, infinite overall. The shapes are closed; the vocabulary is not.
- **`directory`** — every grammar, vocabulary and map in phronesis and where each lives.
  Two of the seven were found by searching the disk rather than remembering them.
- **`dictionary.terms.ground`** now names the collision: /research/dictionary defines
  "Ground state" as a coherence optimum, this defines `ground` as a frozen reference point.
  Same word, unrelated ideas, and neither knew about the other.

## 0.20.0 — 2026-07-29

**The shape language, and `shape-unknown`.** Grammar 1.13.0 replaces a claim that was wrong.

1.11.0 recorded a backbone — check · change · verify · record · act · confirm — and implied
a method is a subsequence of that line. Measured against the five real methods, **only 2 of
5 are.** The other three each broke it differently, and each break forced one production:

    grammar-bump   change → verify → change → verify → record       repetition
    release        ... act → verify → change                        trailing reconcile
    repo-surgery   check → verify → record → change → act → verify → act → verify
                                                                    two acts, and a verify
                                                                    with nothing changed
                                                                    before it

The language, derived in four passes, each forced by a method that would not fit:

    method     := inquiry | check? cycle+ record act_block* reconcile?
    inquiry    := (check | verify)+        a read-only method records nothing
    cycle      := change? verify           the change is optional - a verify may check a
                                           precondition, not only something just changed
    act_block  := change? act verify       repeatable; the leading change varies per block
    reconcile  := change                   update what is generated FROM what changed

Coverage by pass: **2 of 5, 4 of 5, 5 of 5, 13 of 13** including the shipped library. The
third pass fixed a generator bug of mine rather than a gap in the grammar; the fourth added
the read-only production, needed because `investigate` and `audit` change nothing.

**174 shapes.** `lint()` reports `shape-unknown` when a method falls outside the language -
advisory, because an unusual shape is either a new kind of work or a mistake and only the
author can tell which.

The bound is honest and recorded: cycles <= 3, acts <= 2. A legitimate four-cycle method IS
flagged, and that is the enumeration bound rather than anything wrong with the method.

## 0.19.0 — 2026-07-29

**Workflows now ship with laserbrain, and a task can find one.** Two gaps: the store had no
lookup, so an agent had to already know a method's name — which means already knowing it
exists — and every method was phronesis-specific, so a fresh install got an empty shelf.

**The shipped library was enumerated, not invented.** The five phase rules define a
language. Its sentences were counted: 7,895 valid phase sequences up to length 7, 2,201
canonical once repeats collapse. That is the language and not a library — most of it is
degenerate alternation like verify then check then verify. The useful subset is principled:
subsequences of the backbone with each phase in order. There are 63, and **19 are valid**.
Dropping those where `confirm` appears with no `act` — a confirm with nothing to confirm is
just another verify — leaves eight named methods, all lint-clean:

    investigate       check              audit             check → verify
    fix               change→verify→record                 diagnose-and-fix  check→…→record
    ship-built        verify→record→act→confirm            build-and-ship    change→…→confirm
    promote           check→verify→record→act→confirm      full-release      the whole backbone

- **`laserbrain/workflows/` is a store directory inside the package**, declared in
  package-data beside `grammar.json` and for the same reason: a pip install cannot reach the
  repo it came from. Verified in the built wheel, not the tree.
- **`Store.find(task)`** ranks methods against a task using `norm` and Jaccard — the same
  normaliser Φ uses on goals and `collisions()` uses on grounds. Nothing new is introduced:
  if two texts describe the same work the instrument already has an opinion, and this asks
  it. The goal is weighted above the step goals, because a method whose GOAL matches is for
  this task while one whose steps share vocabulary may just share vocabulary.
- **Local methods shadow shipped ones** of the same name. Your release process is more
  specific than the generic one.
- `Store(shipped=False)` isolates the local shelf.

The returned score is deliberately not thresholded. A cutoff that silently returned nothing
would be indistinguishable from an empty store.

## 0.18.0 — 2026-07-29

**A fifth phase rule: `stale-verify`.** A change that falls between the last verify and a
record or act gets committed or shipped with nothing having checked it.

It exists because phronesis's own `grammar-bump` method passed all four earlier rules and
was still wrong. It has a verify, it has a record, and the verify precedes the record — but
it syncs AFTER verifying, so the propagated copies were recorded unchecked. On 2026-07-29
exactly that left two copies at 1.7.0 while canonical was 1.9.0, and a site build in another
repo noticed, two versions later. The shape was right and the content was still wrong, which
is what a fifth rule is for. The method now verifies after syncing and lints clean.

Three more rules were considered and dropped, recorded in the grammar so they are not
re-proposed: `check-before-change` (two of three methods have no leading check and are
correct), `act-is-gated` (redundant — every act verb already carries an irreversible or
outward default), and `reconcile-after-act` (real evidence, but `deploy` has no reconcile
and is correct, so it would fire falsely).

A rule set with invented entries is one people stop reading.

## 0.17.0 — 2026-07-29

**Phases: the shape every method turns out to share, and the ordering rules that fall out
of it.** Grammar 1.11.0.

Three methods were written independently, from three unrelated real failures, and then
mapped onto their step verbs:

    deploy         change → verify → record → act → verify
    grammar-bump   change → change → change → verify → change → record
    release        check → change → change → change → verify → record → act → verify → change

Collapsing repeats leaves one backbone — **change · verify · record · act · confirm** — with
an optional leading `check` and trailing `reconcile`. It was derived, not designed.

Four ordering rules come out of it, and each is a thing that actually went wrong this week,
which is why they are rules rather than preferences:

- **verify-before-record** — a commit and push went out on a RED build, because the steps
  were separate shell lines and a failed verify did not stop the record after it.
- **record-before-act** — an irreversible act whose source is unsaved cannot be reproduced.
- **confirm-after-act** — both PyPI uploads this week needed a retry that only a confirm
  step would have caught.
- **change-is-recorded** — the grammar sync was left uncommitted when a history rewrite
  discarded it. A generated file that is not recorded is not synced, only currently correct.

`Workflow.phases()` returns the sequence; `lint()` now reports shape as well as per-step
declarations. Advisory, like the rest of it: `grammar-bump` legitimately has no `act`, and a
read-only method needs no `record`, so the linter says what is missing and the author
decides whether it matters.

Verified against the failures rather than fixtures — each of the three, rebuilt as a method,
fires the rule that describes it.

## 0.16.0 — 2026-07-29

**An agent-native dictionary, and `Workflow.lint()` that uses it.** Grammar 1.10.0 adds a
`dictionary` section: 18 **terms** fixing the nouns, and 24 **step verbs** fixing the verbs.

Terms exist because this vocabulary has already drifted inside one codebase — `tandem`
became `link`, `laserbrain.md` became `laserfield.md`, and grammar 1.6.0 meant two different
documents for a day. A word with no written definition means whatever the last person
assumed.

Step verbs do more work. A stored method is only worth vending if two people writing the
same method produce something alignable; if one names a step `verify-artifact` and another
`check-wheel`, nothing can tell they are the same step. Each verb also carries its DEFAULT
position on the operator's two axes, which is the same taxonomy `operator_patterns` applies
to shell strings — one classification, two surfaces: the operator applies it to what is
about to run, the dictionary to what is being designed.

- **`Workflow.lint()`** reports `under-declared` (the verb is normally irreversible or
  outward and the step is not marked so — at run time the Operator would wave it through),
  `over-declared` (stricter than the default; harmless, reported so the disagreement is
  visible), `unknown-verb`, and `goal-restates-name` (a goal that repeats its name gives the
  harness nothing to score against).
- **Advisory, never blocking.** Only the author knows what a step actually does, so a linter
  that refused to store a method would be substituting a default for a fact.
- **Step names are verb-first**, because the verb carries the classification. `upload-pypi`
  resolves; `pypi-upload` does not, and that is tested.

It earned itself immediately. On its first run against phronesis's own three stored methods
it caught a real mis-declaration — `deploy` written `irreversible=False`, when putting a
build in front of users cannot be un-shown — plus six step names outside the vocabulary.
None of those six needed a new dictionary entry; every one was a plural, a synonym, or a
noun where a verb belonged.

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
