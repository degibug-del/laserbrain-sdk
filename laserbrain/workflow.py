"""workflow.py — an ordered process an agent runs, measured the whole way down.

WHAT WAS MISSING

laserbrain could already watch one agent on one goal (`Nova.run`) and N agents at once
(`compose`, `Supercode.manage`). It had nothing for the shape most actual work takes: an
ORDERED sequence of steps toward a single goal. That is not a third kind of loop, it is the
one shape where a specific failure lives — and the failure is the reason this file exists.

THE FAILURE IT CATCHES

A step that did something other than what the method declared it was for.

    goal: "ship the release"
      test    declared "the test suite passes"
              reported "the test suite passes"      ⟨pass|suite|test⟩ ⊂ ⟨releas|ship⟩   ok
      build   declared "build the release wheel"
              reported "refactoring the parser"     goal-drift, Φ 0.50                  caught

The step was declared FOR something, it reported doing something else, and the harness
scored the second against the first. That is a fact about this execution rather than an
inference — which matters, because the obvious-looking alternative does not work.

WHAT WAS TRIED FIRST, AND WHY IT WAS DROPPED

The first design compared each step's goal to the WORKFLOW's goal lexically, and reported
steps with little overlap as having wandered. The intended catch was four locally-green
steps that collectively abandoned the goal.

It cannot work, and no threshold rescues it. "the test suite passes" shares no words with
"ship the release" — and neither does "rewrite the documentation index". A legitimate step
and a wandering one are indistinguishable to word overlap, because a step SHOULD be phrased
differently from the goal it serves; restating the goal is what a step that does nothing
looks like. The first run flagged a healthy two-step release as wandering.

There is also a harder point underneath. If a workflow DECLARES a docs-rewrite step, that
step is the method — the author put it there. Nothing about the run is wrong; the method is.
Catching that is a question about a spec, not about an execution, and this file measures
executions.

HOW IT IS MEASURED

Each step gets its OWN harness, grounded on its DECLARED goal, and what the step reports is
scored against that. `parent_goal` carries the workflow's goal into every reading, so the
containment stays visible in the score:

    ⟨pass|suite|test⟩ advancing d1 ⊂ ⟨releas|ship⟩

One harness for the whole sequence does not work either, and that was also measured rather
than assumed: it grounds on step one, so a four-step release reads grounded · goal-drift ·
goal-drift · goal-drift, and the second step was "build the wheel". Per-step grounding is
the same resolution supercode uses for agents.


WHAT MAKES IT AGENT-NATIVE RATHER THAN A PIPELINE

1. A step declares a GOAL, not just a command. Something with no goal cannot be scored, and
   a step that cannot be scored is one the workflow cannot tell you about.
2. It halts on drift instead of running to the end and reporting. A process that keeps
   spending after it has left its goal is the exact thing the instrument is for.
3. Irreversible steps go through the Operator, so "deploy" and "run the tests" are not the
   same kind of thing. A pipeline treats them identically; the sixth layer does not.
4. The workflow is itself measured, so it can be asked whether IT drifted — the same
   discipline `Supercode.self_check()` applies to the supervisor.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _f

from . import Harness
from .operator import Refused


@dataclass
class Step:
    """One step: a name, a goal it is for, and how it must be treated if it acts."""

    name: str
    goal: str
    fn: object
    irreversible: bool = False
    outward: bool = False
    verdict: object = None
    ran: bool = False
    result: object = None
    # False only for a step rebuilt from a vended spec and not yet bound to code.
    bound: bool = True
    # Each step carries its OWN harness, grounded on the DECLARED goal. See run().
    harness: object = None
    # What the step said it was doing, when it reported a goal of its own.
    reported: str = ''


class Workflow:
    """An ordered process, grounded at the top and at every step.

        w = Workflow(goal='ship the release')
        w.step('test',    run_tests,  goal='the suite passes')
        w.step('build',   build_whl,  goal='a wheel exists')
        w.step('publish', upload,     goal='it is on PyPI', irreversible=True, outward=True)

        out = w.run(operator=op)     # op only needed if a step is irreversible
        w.wandered()                 # steps that did other than what they were declared for

    Step functions take the running context dict and return a dict shaped like the harness
    contract — `progress`, `distance`, optionally `goal` and `done`. A step that returns
    nothing is treated as having advanced, because a step that ran and said nothing is not
    evidence of drift; it is only evidence of a step that does not report.
    """

    def __init__(self, goal: str, calibration=None):
        if not goal or not str(goal).strip():
            raise ValueError('a workflow needs a goal — an ungrounded process cannot be '
                             'measured, and the whole point is the measurement')
        self.goal = goal
        self.steps: list[Step] = []
        self._cal = calibration
        # The workflow's own harness, for self_check only. Step verdicts never come from
        # here — see the note in run() about why a shared ground is the wrong instrument.
        self._hz = Harness(calibration=calibration)
        # From grammar.json, not a literal. goal_min is the threshold for "this agent has
        # left its own ground", which is exactly the question asked of one step.
        from . import _G
        self.phi_min = float((_G.get('calibration') or {}).get('goal_min', 0.30))

    def _departed(self, v) -> bool:
        """Whether one step reading counts as having left what it was declared for.

        NOT simply `v.drifting`. Two of the nine verdicts — `stalled` and `self-report` —
        warn before they interrupt, and escalating a warning needs history. Every step
        here gets a fresh harness, so it has none, and a warn can never become an
        interrupt however bad the reading is.

        Measured, not supposed: a step reporting `circling` at distance 9 comes back
        `self-report:circling` with **Φ=0.82 and drifting=False**. Halting on `drifting`
        alone would sail past the loudest signal the instrument can produce. Φ against
        goal_min is the reading that survives having no history behind it.
        """
        if v is None:
            return False
        if getattr(v, 'drifting', False):
            return True
        return float(getattr(v, 'phi', 0.0) or 0.0) >= self.phi_min

    def step(self, name: str, fn, goal: str | None = None,
             irreversible: bool = False, outward: bool = False) -> 'Workflow':
        """Add a step. Returns self so definitions can chain."""
        if not callable(fn):
            raise TypeError(f'step {name!r} must be callable')
        if any(s.name == name for s in self.steps):
            raise ValueError(f'step {name!r} is already defined — names are how steps are '
                             'reported, so duplicates make the report ambiguous')
        self.steps.append(Step(name=name, goal=goal or name, fn=fn,
                               irreversible=irreversible, outward=outward))
        return self

    # ── running ────────────────────────────────────────────────────────────────────────
    def run(self, operator=None, ctx: dict | None = None, halt_on_drift: bool = True) -> dict:
        """Run the steps in order, checking each against its own goal AND the workflow's.

        Halts at the first drifting verdict unless `halt_on_drift=False`. Halting is the
        default because the alternative — finish everything, report at the end — is what a
        pipeline already does, and it means paying for every step after the one that left
        the goal.

        An irreversible step with no operator is refused rather than run. That is the
        layer's rule and it is not softened here just because a workflow is convenient.
        """
        ctx = dict(ctx or {})
        ran, halted_at, refused_at = [], None, None

        for s in self.steps:
            if s.irreversible or s.outward:
                if operator is None:
                    refused_at = s.name
                    break
                try:
                    out = operator.act(lambda: s.fn(ctx), kind='workflow-step',
                                       target=f'{self.goal} :: {s.name}',
                                       reversible=not s.irreversible, outward=s.outward)
                except Refused:
                    refused_at = s.name
                    break
            else:
                out = s.fn(ctx)

            s.ran, s.result = True, out
            ran.append(s.name)
            rep = out if isinstance(out, dict) else {}

            # EACH STEP GETS ITS OWN HARNESS, so its ground is its own goal.
            #
            # The first version shared one harness across the sequence, which grounds on
            # step one and then reports goal-drift for every honest step after it. Measured
            # rather than assumed: a four-step release read grounded · goal-drift ·
            # goal-drift · goal-drift, and the second step was "build the wheel". An
            # instrument that calls the normal shape of the thing it measures a spiral is
            # not strict, it is wrong.
            #
            # Same resolution supercode already uses: every agent gets its own harness, and
            # the cross-agent reading is a separate method. Here the step verdict says
            # whether the step did what it was DECLARED for, and wandered() collects them
            # to the workflow's. parent_goal keeps the containment visible in the score.
            # ...and it is GROUNDED ON THE DECLARED GOAL — what the method says this step
            # is for — before anything the step reports is scored against it. That makes
            # the step verdict mean something specific and checkable: did this step do the
            # thing it was declared to do.
            #
            # This replaced a lexical comparison between each step's goal and the
            # workflow's, which did not work and could not be made to work by tuning. "the
            # test suite passes" shares no words with "ship the release" — and neither does
            # "rewrite the documentation index". A legitimate step and a wandering one were
            # indistinguishable to it, because a step SHOULD be phrased differently from
            # the goal; restating the goal is what a step that does nothing looks like.
            #
            # Grounding on the declaration is the reading the vending story needs anyway:
            # a stored method says what each step is for, and a run is measured against
            # the method. That is a fact about this execution, not a guess about wording.
            s.harness = Harness(calibration=self._cal)
            s.harness.check(goal=s.goal, progress='advancing', parent_goal=self.goal)

            s.reported = str(rep.get('goal') or s.goal)
            s.verdict = s.harness.check(goal=s.reported,
                                        progress=rep.get('progress', 'advancing'),
                                        distance=rep.get('distance'),
                                        parent_goal=self.goal)
            if self._departed(s.verdict) and halt_on_drift:
                halted_at = s.name
                break
            if rep.get('done'):
                break

        return {
            'goal': self.goal,
            'ran': ran,
            'completed': halted_at is None and refused_at is None and len(ran) == len(self.steps),
            'halted_at': halted_at,
            'refused_at': refused_at,
            'wandered': self.wandered(),
            'ctx': ctx,
        }

    # ── reading ────────────────────────────────────────────────────────────────────────
    def wandered(self) -> list[dict]:
        """Steps that did something other than what the method declared them for.

        The reading that justifies the file, and it is a fact rather than an inference:
        the step was declared to be for X, it reported doing Y, and the harness scored Y
        against X. A task runner cannot produce this because it never knew what the step
        was FOR — only whether it exited zero.

        Run with `halt_on_drift=False` to see every one of them instead of stopping at the
        first, which is what you want when reading a finished run rather than guarding a
        live one.
        """
        out = []
        for s in self.steps:
            if s.ran and self._departed(s.verdict):
                out.append({'step': s.name,
                            'declared': s.goal,
                            'reported': s.reported,
                            'reason': getattr(s.verdict, 'reason', None),
                            'drifting': bool(getattr(s.verdict, 'drifting', False)),
                            'phi': getattr(s.verdict, 'phi', None),
                            'laserscore': getattr(s.verdict, 'laserscore', None)})
        return out

    def self_check(self):
        """The workflow's own verdict — the discipline supercode applies to itself."""
        done = sum(1 for s in self.steps if s.ran)
        return self._hz.check(goal=self.goal,
                              progress='advancing' if done else 'stuck',
                              distance=max(0, 10 - int(10 * done / max(1, len(self.steps)))))

    def report(self) -> str:
        lines = [f'workflow: {self.goal}']
        for s in self.steps:
            mark = '·' if not s.ran else ('!' if self._departed(s.verdict) else '+')
            far = '  ← departed' if s.ran and self._departed(s.verdict) else ''
            lines.append(f'  {mark} {s.name:<14} {getattr(s.verdict, "laserscore", "") or ""}{far}')
        return '\n'.join(lines)

    # ── storing and vending ────────────────────────────────────────────────────────────
    #
    # A workflow that can be stored and handed to someone else cannot carry its callables:
    # a function is not data, and a store that shipped executable steps would be a package
    # registry with a worse security model than the ones that already exist.
    #
    # So what travels is the METHOD, not the code. The spec carries the ordered steps, the
    # goal each one is for, and which of them act on the world — everything needed to
    # MEASURE the process — and the consumer binds their own implementations. That split
    # is not a limitation worked around; it is the correct seam. The valuable, transferable
    # part of a workflow was never the shell commands. It is knowing that releasing has
    # four steps in this order, that the third is irreversible, and what each one is FOR.
    #
    # It also means a vended workflow is safe to read: nothing in a spec can execute.

    SPEC_VERSION = 1

    def spec(self) -> dict:
        """The workflow as data — ordered, grounded, and carrying no code."""
        return {
            'spec_version': self.SPEC_VERSION,
            'goal': self.goal,
            'steps': [{'name': s.name, 'goal': s.goal,
                       'irreversible': s.irreversible, 'outward': s.outward}
                      for s in self.steps],
        }

    @classmethod
    def from_spec(cls, spec: dict, calibration=None) -> 'Workflow':
        """Rebuild a workflow from a spec. Every step comes back UNBOUND.

        Unbound steps raise if run, rather than defaulting to a no-op. A workflow that
        quietly skipped the steps nobody implemented would report a clean run of a process
        that did not happen — which is the failure this whole package exists to catch,
        reproduced by its own convenience method.
        """
        v = spec.get('spec_version')
        if v != cls.SPEC_VERSION:
            raise ValueError(f'spec_version {v!r} — this laserbrain reads '
                             f'{cls.SPEC_VERSION}. Refusing to guess at a shape it does '
                             'not know rather than silently mis-reading it.')
        w = cls(goal=spec['goal'], calibration=calibration)
        for s in spec.get('steps') or []:
            name = s['name']

            def unbound(ctx, _n=name):
                raise NotImplementedError(
                    f'step {_n!r} is unbound — bind it with .bind({_n!r}, fn) before '
                    'running. A vended workflow carries the method, not the code.')

            w.step(name, unbound, goal=s.get('goal') or name,
                   irreversible=bool(s.get('irreversible')),
                   outward=bool(s.get('outward')))
            w.steps[-1].bound = False
        return w

    def bind(self, name: str, fn) -> 'Workflow':
        """Supply the implementation for one step of a vended workflow."""
        if not callable(fn):
            raise TypeError(f'step {name!r} must be bound to something callable')
        for s in self.steps:
            if s.name == name:
                s.fn = fn
                s.bound = True
                return self
        raise KeyError(f'no step named {name!r} — this workflow has '
                       f'{[s.name for s in self.steps]}')

    def unbound(self) -> list[str]:
        """Steps still without an implementation. Check before running a vended workflow."""
        return [s.name for s in self.steps if s.bound is False]


class Store:
    """laserstore for methods — where workflows are kept and handed out.

        store = Store()
        store.put(release_workflow, 'release')      # keep it
        w = store.get('release')                    # someone else takes it, unbound
        w.bind('test', my_tests).bind('build', my_build)
        w.run()

    This is the records layer doing what the records layer is for. A method that lives in
    one person's head, or in one repo's Makefile, is not a method anyone can adopt — and
    the transferable part was never the commands. It is the shape: that releasing has these
    steps, in this order, that this one cannot be taken back, and what each is FOR.

    Nothing in a stored workflow can execute. Specs are data, steps come back unbound, and
    a step nobody binds raises rather than passing silently. So reading a vended workflow
    from someone you do not know is safe in a way that installing their package is not.
    """

    def __init__(self, root=None):
        from pathlib import Path
        self.root = Path(root) if root else Path.home() / '.laserbrain' / 'workflows'

    def put(self, workflow: 'Workflow', name: str) -> str:
        """Store a workflow's spec. Returns the path written."""
        import json
        if not name or '/' in name or name.startswith('.'):
            raise ValueError(f'{name!r} is not a usable name — it becomes a filename')
        self.root.mkdir(parents=True, exist_ok=True)
        p = self.root / f'{name}.json'
        p.write_text(json.dumps(workflow.spec(), indent=2) + '\n', encoding='utf-8')
        return str(p)

    def vend(self, name: str) -> dict:
        """The raw spec, as data. Readable without building or running anything."""
        import json
        p = self.root / f'{name}.json'
        if not p.exists():
            raise KeyError(f'no workflow {name!r} in {self.root} — have {self.list()}')
        return json.loads(p.read_text(encoding='utf-8'))

    def get(self, name: str, calibration=None) -> 'Workflow':
        """Vend a workflow, rebuilt and ready to bind. Every step arrives unbound."""
        return Workflow.from_spec(self.vend(name), calibration=calibration)

    def list(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob('*.json'))

    def catalogue(self) -> list[dict]:
        """What is on the shelf, with enough to choose by and nothing that runs."""
        out = []
        for n in self.list():
            try:
                s = self.vend(n)
            except Exception as e:
                out.append({'name': n, 'error': f'{type(e).__name__}: {e}'})
                continue
            steps = s.get('steps') or []
            out.append({'name': n, 'goal': s.get('goal'), 'steps': len(steps),
                        'irreversible': [x['name'] for x in steps if x.get('irreversible')],
                        'outward': [x['name'] for x in steps if x.get('outward')]})
        return out
