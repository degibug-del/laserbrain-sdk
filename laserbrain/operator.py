"""operator.py — the sixth layer, as something nova can hold.

Named in grammar 1.8.0 on 2026-07-28. The other five layers measure, instruct, serve,
define and record; the operator is the only one that ACTS on the world. That is the whole
reason it needed a name of its own rather than being filed under lasergear as "tools".

WHY IT IS A LAYER

The grammar sets the test: a part is real when it has a failure mode none of the others
share. Every other failure is recoverable by correction — a wrong reading is re-taken, an
absent instruction supplied, an unreachable server retried, a mismatched copy re-synced, a
lost record rebuilt. The operator's is not. A sent message is sent. A deleted file is
deleted. It fails by being IRREVERSIBLE.

WHAT THIS MODULE ACTUALLY ENFORCES

One rule, from the layer's own `may_not` clause:

    take an irreversible or outward-facing action without authorization from the person,
    per action and per session

Three things follow, and each is a deliberate choice rather than an implementation detail:

1. DEFAULT IS DENY. An Operator built with no authorizer refuses every irreversible action.
   The alternative — proceed unless someone objects — puts the burden on the person who is
   not in the loop, which is the situation the layer exists to describe.

2. APPROVAL DOES NOT CACHE. Every irreversible act asks, every time, even for an identical
   action approved a moment ago. "Per action and per session" is the strict reading and the
   safe one: caching by fingerprint would let one approval cover a repeat the person never
   saw. A loop that deletes a thousand files would ask once. That is the failure this rule
   is for.

3. REFUSAL IS RECORDED, NOT SILENT. Every act — taken, refused, or failed — lands in `log`.
   An operator that blocked something and said nothing is indistinguishable from one that
   was never called, which is the same "silence is not success" problem the harness has
   everywhere else.

WHAT IT DOES NOT DO

It does not decide what is reversible. The caller declares that, because only the caller
knows what the callable actually does — a guard that inferred reversibility from a string
would be guessing, and guessing in this direction is exactly the wrong way to be wrong.
Declaring nothing means `reversible=False`, so an undeclared action is treated as
irreversible and asks.

It is also not a sandbox. Python offers no true barrier and this class does not pretend to
be one: `op._authorize = lambda a: True` is one line away for anything running in-process.
It is the same posture as `Nova.ground_intact()` — evidence rather than a wall. What it
guarantees is that taking an irreversible action without asking cannot happen BY ACCIDENT,
and that if it happens deliberately the log says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _f

from .catches import Event


class Refused(Exception):
    """An action the operator would not take.

    Raised rather than returned. A refusal that came back as a falsy value would be
    silently ignorable by `if op.act(...)`-shaped code, and the one thing a refusal must
    not be is easy to miss.
    """


@dataclass(frozen=True)
class Act:
    """A description of something about to be done to the world.

    `reversible` and `outward` are declared by the caller, never inferred. See the module
    docstring: inferring them would mean guessing, and the default has to be the cautious
    one.
    """

    kind: str                    # 'shell' | 'file' | 'browser' | 'deploy' | 'send' | ...
    target: str                  # what it acts on, in whatever form the caller has
    reversible: bool = False
    outward: bool = False        # leaves this machine — a send, a publish, a deploy

    @property
    def needs_authorization(self) -> bool:
        """Irreversible OR outward. Either alone is enough.

        Outward-facing matters even when reversible: an email you can delete has still been
        read, and a page you can unpublish has still been indexed.
        """
        return (not self.reversible) or self.outward

    def __str__(self) -> str:
        marks = []
        if not self.reversible:
            marks.append('irreversible')
        if self.outward:
            marks.append('outward')
        return f'{self.kind}:{self.target}' + (f' ({", ".join(marks)})' if marks else '')


class Operator:
    """The hands. Give it an authorizer or it will refuse anything that cannot be undone.

        op = Operator(authorize=ask_the_person)
        op.attach(nova)
        nova.use('operator', shutil.rmtree, kind='file', target='/tmp/x', path='/tmp/x')

    `authorize` receives the Act and returns truthy to allow. It is supplied by whatever
    is standing in for the person — a prompt, a hook, a queue. Nova cannot set it: nothing
    in this class reads from the agent, which is the same reason `Nova` has no method that
    moves its own ground.
    """

    #: supercode may not route operator work. Allocation is a reading; an action is not,
    #: and a manager that could dispatch irreversible work would be deciding something no
    #: reading gives it a basis for. Written into layers.operator.routing in grammar 1.8.0.
    routable = False

    def __init__(self, authorize=None, name: str = 'operator'):
        self.name = name
        self._authorize = authorize
        self.log: list[Event] = []
        self.asked = 0
        self.refused = 0
        self.taken = 0

    # ── the one entry point ────────────────────────────────────────────────────────────
    def act(self, do, *, kind: str, target: str,
            reversible: bool = False, outward: bool = False, **kw):
        """Run `do(**kw)`, but only if the layer's rule allows it.

        Returns whatever `do` returns. Raises `Refused` if authorization was required and
        not given — including when no authorizer exists at all, which is the default.
        """
        if not callable(do):
            raise TypeError(f'operator needs something callable, got {type(do).__name__}')

        a = Act(kind=kind, target=target, reversible=reversible, outward=outward)

        if a.needs_authorization:
            self.asked += 1
            if self._authorize is None:
                return self._refuse(a, 'no authorizer — an operator with nobody to ask '
                                       'refuses anything it cannot take back')
            # Deliberately NOT cached. See point 2 in the module docstring.
            try:
                allowed = bool(self._authorize(a))
            except Exception as e:
                # An authorizer that breaks is not an authorizer that consented.
                return self._refuse(a, f'authorizer raised {type(e).__name__}: {e}')
            if not allowed:
                return self._refuse(a, 'not authorized')

        try:
            out = do(**kw)
        except Exception as e:
            self._record(a, ok=False, note=f'{type(e).__name__}: {e}')
            raise
        self.taken += 1
        self._record(a, ok=True, note='taken')
        return out

    # ── record-keeping ─────────────────────────────────────────────────────────────────
    def _refuse(self, a: Act, why: str):
        self.refused += 1
        self._record(a, ok=False, note=f'refused — {why}')
        raise Refused(f'{a}: {why}')

    def _record(self, a: Act, *, ok: bool, note: str):
        ev = Event(kind='operator', name=str(a), ok=ok, result=note)
        self.log.append(ev)

    # ── wiring ─────────────────────────────────────────────────────────────────────────
    def attach(self, nova, name: str | None = None):
        """Register as a skill on a Nova. Returns the nova so it can chain."""
        return nova.learn(name or self.name, self.act)

    def report(self) -> str:
        return (f'operator {self.name}: {self.taken} taken, {self.refused} refused, '
                f'{self.asked} asked, {len(self.log)} logged')


def refuse_routing(agents) -> None:
    """Raise if a supervisor is about to dispatch operator work.

    Called from Supercode.manage. The bar is not that acting is dangerous — it is that a
    manager's authority comes entirely from holding readings that no single agent has, and
    a reading gives no basis whatsoever for deciding who should take an irreversible
    action. Routing allocation is inside its competence; routing a deploy is not.
    """
    bad = []
    for name, fn in (agents or {}).items():
        owner = getattr(fn, '__self__', None)
        if isinstance(fn, Operator) or isinstance(owner, Operator) \
                or getattr(fn, 'routable', True) is False:
            bad.append(name)
    if bad:
        raise Refused(
            f'supercode may not route operator work: {", ".join(sorted(bad))}. '
            'Allocation is a reading; an action is not (grammar 1.8.0, '
            'layers.operator.routing).')
