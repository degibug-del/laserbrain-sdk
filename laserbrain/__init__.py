"""
laserbrain — attach the smart recursion harness to any agent loop.

The check is a pure function, so it runs LOCALLY and free (the open grammar, no
key, no latency). Give it a key and it also mirrors to the API for retained drift
history, alerts and the fleet view — you pay to *see* your agents drift, not for
the check. Model-agnostic: you provide the agent, laserbrain closes the loop.

    from laserbrain import Harness
    hz = Harness()                                  # local + free (add key=... to retain)
    v = hz.check(goal="build the parser", progress="advancing", distance=6)
    if v.drifting: ...                              # v.advice tells the agent to return

    hz.run(step, on_return=lambda v, ctx: ...)      # the act layer: auto-inject the return

    from laserbrain import Team
    Team("adversarial-deliberation", goal="…").run(agent_fn)   # a styled recursion team

The single-agent detector mirrors the frozen drift.ts @ 6b483de7 (the published
instrument); the multi-agent dialogue + recursion teams are the prototype extension.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, re, urllib.request

__all__ = ['Harness', 'Team', 'Verdict', 'PRESETS', 'norm', 'laserscore', 'verify_audit', 'ground_score', 'MAX_DEPTH']
__version__ = '0.4.3'
MAX_DEPTH = 50   # nesting deeper than this is a drift signal, not a decomposition
API_DEFAULT = 'https://laserbrain-mcp.degibug.workers.dev'


# ── provenance: a tamper-evident, hash-chained ledger of every check ───────────
def _canon(d):
    return json.dumps(d, sort_keys=True, separators=(',', ':'))


def _link(prev, body):
    return hashlib.sha256((prev + _canon(body)).encode()).hexdigest()


def verify_audit(chain: list) -> tuple:
    """Independently verify an exported audit chain. Returns (ok, first_bad_index):
       (True, -1) if intact, else (False, i) at the first tampered/broken link.
       Free and offline — anyone can audit an agent's run without a key."""
    prev = ''
    for i, rec in enumerate(chain):
        body = {k: rec[k] for k in rec if k != 'hash'}
        if rec.get('prev') != prev or _link(prev, body) != rec.get('hash'):
            return (False, i)
        prev = rec['hash']
    return (True, -1)


_SPARK = '▁▂▃▄▅▆▇█'


def _sparkline(values: list, lo: float = 0.0, hi: float = None) -> str:
    """A dep-free unicode sparkline of a numeric series."""
    if not values:
        return ''
    hi = hi if hi is not None else (max(values) or 1.0)
    rng = (hi - lo) or 1.0
    n = len(_SPARK) - 1
    return ''.join(_SPARK[min(n, max(0, int((v - lo) / rng * n)))] for v in values)

# ── the fixed-reference primitive (frozen: drift.ts @ 6b483de7) ────────────────
_STOP = {'the', 'a', 'an', 'to', 'of', 'and', 'or', 'for', 'in', 'on', 'at', 'is', 'it', 'this',
         'that', 'with', 'my', 'your', 'our', 'i', 'we', 'be', 'as', 'by', 'from', 'into', 'out',
         'up', 'so', 'then'}
_STEM = re.compile(r"(ings?|edly|ed|ers?|es|s|tion|ment)$")
_PROGRESS = {'advancing', 'stuck', 'circling'}


def norm(s):
    out = set()
    for w in re.findall(r"[a-z0-9']+", str(s).lower()):
        if w in _STOP:
            continue
        r = _STEM.sub('', w) if len(w) > 4 else w
        if r:
            out.add(r)
    return out


def _jac(a, b):
    if not a and not b:
        return 0.0
    return 1 - len(a & b) / len(a | b)


def _sim(a, b):
    return 1 - _jac(a, b)


def _asdist(d):
    try:
        return max(0, min(10, int(float(d))))
    except Exception:
        return 5


def laserscore(goal, progress, distance=None, parent_goal=None) -> str:
    """One well-formed reading written in the grammar, in canonical form.

    The grammar is the notation. A laserscore is what gets written in it at a single
    step. Φ is a measurement taken of that writing. Naming the middle term is what lets
    the two failures be told apart: a state that cannot be spelled at all is caught
    before any number exists, and no number is ever reported for it.

    The rendering shows exactly the three slots Φ reads, inflection already collapsed by
    norm(), which is why 'building billboards' and 'build a billboard' write the same
    score. Kept byte-identical to the server's renderer in lasermind/mcp-server.mjs --
    test_laserscore_conformance.py fails if the two ever disagree.
    """
    def tok(v):
        return '|'.join(sorted(norm(v)))
    d = 'd?' if distance is None else f'd{_asdist(distance)}'
    base = f'⟨{tok(goal)}⟩ {progress} {d}'
    if parent_goal and str(parent_goal).strip():
        return f'{base} ⊂ ⟨{tok(parent_goal)}⟩'
    return base


def _clamp01(x):
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0


class Calibration:
    """The instrument's numbers, in one object, changeable on purpose.

    Until v0.4.0 these were six literals buried in the decision path. Mutation testing
    on 2026-07-24 showed the suite stayed green when the goal threshold moved 0.30->0.45
    and when the weights were reshuffled — so the published instrument could be retuned
    silently. Naming them does two things at once: it makes retuning POSSIBLE for callers
    who need a different sensitivity, and it makes it VISIBLE, because `Calibration()`
    with no arguments is the published instrument and anything else is an argued choice.

    The theorem is untouched either way. PROOF requires a reference that does not move
    DURING a run; it says nothing about which threshold you picked before it started.
    A Calibration is fixed for the life of a _Run — that is the part that is load-bearing.
    """

    __slots__ = ('goal_min', 'self_report_min', 'stall_window', 'w_goal', 'w_distance',
                 'w_progress', 'echo_min', 'dialogue_window')

    def __init__(self, goal_min=0.30, self_report_min=0.15, stall_window=4,
                 w_goal=0.5, w_distance=0.3, w_progress=0.2,
                 echo_min=0.25, dialogue_window=3):
        for name, v in (('goal_min', goal_min), ('self_report_min', self_report_min)):
            if not 0.0 <= float(v) <= 1.0:
                raise ValueError(f'{name} must be within 0..1, got {v!r}')
        if int(stall_window) < 1:
            raise ValueError(f'stall_window must be >= 1, got {stall_window!r}')
        total = float(w_goal) + float(w_distance) + float(w_progress)
        if abs(total - 1.0) > 1e-9:
            # Not pedantry: Φ is read against fixed thresholds and reported to users as a
            # 0..1 displacement. Weights that sum to anything else silently rescale it.
            raise ValueError(f'weights must sum to 1.0, got {total:.6f}')
        self.goal_min, self.self_report_min, self.stall_window = float(goal_min), float(self_report_min), int(stall_window)
        if not 0.0 <= float(echo_min) <= 1.0:
            raise ValueError(f'echo_min must be within 0..1, got {echo_min!r}')
        if int(dialogue_window) < 1:
            raise ValueError(f'dialogue_window must be >= 1, got {dialogue_window!r}')
        self.w_goal, self.w_distance, self.w_progress = float(w_goal), float(w_distance), float(w_progress)
        self.echo_min, self.dialogue_window = float(echo_min), int(dialogue_window)

    def __eq__(self, o):
        return isinstance(o, Calibration) and all(
            getattr(self, f) == getattr(o, f) for f in self.__slots__)

    def __repr__(self):
        d = ', '.join(f'{f}={getattr(self, f)}' for f in self.__slots__)
        return f'Calibration({d})'

    @property
    def is_published(self):
        """True when this is the instrument as shipped — what drift.ts carries at 6b483de7."""
        return self == PUBLISHED


PUBLISHED = Calibration()


def _displacement(goal, progress, distance, ground, sim=None, cal=None):
    # The goal term is the only VOCABULARY judgment — swap `sim` to change the
    # grammar without touching the theorem (PROOF blesses *a* fixed reference,
    # never a particular vocabulary). sim=None keeps the frozen word-overlap path.
    cal = cal or PUBLISHED
    goal_term = (1.0 - _clamp01(sim(goal, ground['goal']))) if sim else _jac(norm(goal), norm(ground['goal']))
    # None means "not known", not "zero" and not the 5 that _asdist would fall back to.
    # An unknown term contributes nothing, which makes Φ a LOWER bound: inferred state can
    # under-report drift and cannot invent it. See observe.py.
    if distance is None or ground['dist'] is None:
        dist_term = 0.0
    else:
        dist_term = abs(_asdist(distance) - ground['dist']) / 10
    return (cal.w_goal * goal_term
            + cal.w_distance * dist_term
            + cal.w_progress * (0 if progress == ground['progress'] else 1))


_DRIFT = ('ungrammatical', 'goal-drift', 'stalled')


def _terms(goal, progress, distance, ground, sim=None, cal=None):
    """The three components of Φ, separately. Handed back with the verdict so a reader
    can see WHICH part moved rather than being told a single number."""
    cal = cal or PUBLISHED
    g = (1.0 - _clamp01(sim(goal, ground['goal']))) if sim else _jac(norm(goal), norm(ground['goal']))
    if distance is None or ground['dist'] is None:
        d = None
    else:
        d = abs(_asdist(distance) - ground['dist']) / 10
    pr = 0 if progress == ground['progress'] else 1
    return {'goal': cal.w_goal * g, 'distance': None if d is None else cal.w_distance * d,
            'progress': cal.w_progress * pr}


def _isdrift(reason):
    return reason in _DRIFT or reason.startswith('self-report')


def ground_score(phi: float) -> float:
    """Turn a displacement Φ into a bounded [0,1] 'how grounded' reading: 1.0 at
       ground, falling as the agent displaces. This is v's system score, 1/(1+4·P),
       applied to Φ — the shared primitive between laserbrain and the language of
       zeros (see the note "The Present as the Fixed Reference")."""
    try:
        return round(1.0 / (1.0 + 4.0 * max(0.0, float(phi))), 3)
    except Exception:
        return 0.0


@dataclass
class Verdict:
    drifting: bool
    reason: str
    phi: float
    advice: str
    # The evidence behind the verdict, in plain English and actual numbers. A monitor
    # that can only interrupt gets switched off; one that can be argued with gets
    # trusted. Defaulted so every existing Verdict(...) call site keeps working.
    why: str = ''
    # The grammatical object this verdict was derived FROM, in canonical form. None
    # exactly when the state could not be spelled -- for an 'ungrammatical' verdict that
    # None is not a missing field, it is the finding. Defaulted so every existing
    # Verdict(...) call site keeps working.
    laserscore: str = None

    @property
    def ground_score(self) -> float:
        """Φ as a bounded [0,1] confidence-in-ground reading (1.0 = fully grounded)."""
        return ground_score(self.phi)

    def __str__(self) -> str:
        mark = '⚑ drifting' if self.drifting else ('✓ grounded' if self.reason == 'grounded' else '· on track')
        return f'[{mark}] {self.reason} · Φ={self.phi:.2f} · ground={self.ground_score:.2f} — {self.advice}'


class _Run:
    """Single-agent drift state for one task run."""
    def __init__(self, sim=None, cal=None):
        self.ground = None
        self.first_goal = set()
        self.first_goal_text = ''
        self.sim = sim           # optional custom text-similarity (the pluggable grammar)
        # Fixed for the life of the run. Swapping calibration mid-run would move the
        # reference while measuring against it, which is the one thing PROOF forbids.
        self.cal = cal or PUBLISHED
        self.dist_hist = []
        self.trace = []          # (reason, drifting)

    def step(self, goal, progress, distance, parent_goal=None, user_turn=False):
        prev = _isdrift(self.trace[-1][0]) if self.trace else False
        # Stays None until the state is known grammatical, a few lines below. emit() reads
        # it at call time, so the ungrammatical return below correctly carries no score --
        # there is nothing to write when the state cannot be spelled.
        score = None

        def emit(reason, drifting, advice, phi=0.0, why=''):
            self.trace.append((reason, drifting))
            return Verdict(drifting, reason, round(phi, 2), advice, why, score)

        goal = str(goal or '').strip()
        if not goal or progress not in _PROGRESS:
            bad = 'the goal is empty' if not goal else f'{progress!r} is not one of {sorted(_PROGRESS)}'
            return emit('ungrammatical', True,
                        'You cannot spell a clear goal and a valid progress. Return to ground.',
                        why=bad)
        d = None if distance is None else _asdist(distance)
        score = laserscore(goal, progress, d, parent_goal)
        if self.ground is None:
            self.ground = {'goal': goal, 'progress': progress, 'dist': d}
            self.first_goal = norm(goal)
            self.first_goal_text = goal
            self.dist_hist = [] if d is None else [d]
            return emit('grounded', False, 'Ground state set — continue, and check each step.',
                        why=f'ground is goal={goal!r}, progress={progress!r}, '
                            f'distance={"unknown" if d is None else d}')
        phi = _displacement(goal, progress, d, self.ground, self.sim, self.cal)
        tm = _terms(goal, progress, d, self.ground, self.sim, self.cal)
        parts = ', '.join(f'{k} {("unknown" if v is None else format(v, ".2f"))}' for k, v in tm.items())
        if progress in ('stuck', 'circling') and phi > self.cal.self_report_min:
            return emit(f'self-report:{progress}', prev,
                        f'You reported {progress} and have moved from ground. Return to your goal.' if prev
                        else f'You reported {progress}. If it holds next step, return to ground.', phi,
                        why=f'you said {progress!r} and Φ={phi:.2f} is above the '
                            f'{self.cal.self_report_min:.2f} self-report floor ({parts})')
        if self.sim:                       # pluggable grammar: has the goal's MEANING moved?
            anchor = _clamp01(self.sim(goal, self.first_goal_text))
        else:                              # frozen default: word overlap, unchanged
            g = norm(goal)
            anchor = (len(g & self.first_goal) / len(g | self.first_goal)) if (g or self.first_goal) else 0.0
        if anchor < self.cal.goal_min:
            # ── the user changed the subject ────────────────────────────────────────
            # This is the single highest-value rule in the instrument, and it was in the
            # MCP server and not here. The graded corpus (CLAIM.md, 35 fires) puts
            # goal-drift at 24 fires and 0 true catches — 69% of everything this
            # instrument has ever produced, with a precision of zero — and 22 of those 24
            # were the FIRST CHECK AFTER THE USER SPOKE. The rule was faithfully detecting
            # that the subject had changed. It had: someone changed it.
            #
            # A goal that was replaced was not drifted from, so this is not a softened
            # verdict, it is a different event. The caller has to say so, because a
            # library cannot see the conversation the way the server's hook can — hence an
            # explicit flag rather than a guess.
            if user_turn:
                self.ground = {'goal': goal, 'progress': progress, 'dist': d}
                self.first_goal = norm(goal)
                self.first_goal_text = goal
                self.dist_hist = [] if d is None else [d]
                return emit('reground', False,
                            'New instruction — ground reset to the goal you just stated.',
                            why=f'the goal moved (overlap {anchor:.2f}) on the first check '
                                f'after a user turn, so it was replaced, not drifted from')
            # ── quantized recursion: the excursion case ─────────────────────────────
            # This grammar is a discrete measurement grid. `distance` is 11 integers,
            # `progress` is 3 enum values, and `goal` is ONE slot. An agent inside a
            # legitimate sub-task holds two goals at once — the parent it still serves and
            # the branch it is on — and one slot forces it to spell a single one. It spells
            # the branch, overlap with ground collapses, and the QUANTIZATION ERROR is
            # reported as drift.
            #
            # The arithmetic was never wrong. Φ measured exactly what it was handed; the
            # loss happened before the measurement, writing a two-valued state into a
            # one-valued field. So the repair belongs to the grammar, not the detector.
            #
            # An agent that can say "this branch serves that parent" is measured against
            # whichever it declares live, and the result is an `excursion` — recorded and
            # counted, but not called drift.
            #
            # Strictly additive. parent_goal=None takes the identical path it always took,
            # so the frozen instrument stays frozen and the old corpus stays comparable.
            if parent_goal and str(parent_goal).strip():
                if self.sim:
                    p_anchor = _clamp01(self.sim(parent_goal, self.first_goal_text))
                else:
                    p = norm(parent_goal)
                    p_anchor = ((len(p & self.first_goal) / len(p | self.first_goal))
                                if (p or self.first_goal) else 0.0)
                if p_anchor >= self.cal.goal_min:
                    return emit('excursion', False,
                                f'On a sub-task (overlap {anchor:.2f}) that still serves your ground '
                                f'goal (parent overlap {p_anchor:.2f}). Not drift — but the parent is '
                                f'what you owe.', phi,
                                why=f'goal overlap {anchor:.2f} is below goal_min '
                                    f'{self.cal.goal_min:.2f}, but the declared parent overlaps '
                                    f'{p_anchor:.2f}, so this is a branch and not a departure')
            # Name the remedy, not just the fault. A goal legitimately stops matching ground
            # in three ways and the verdict used to describe none of them: the user
            # redirected you (reset), you are on a sub-task (parent_goal), or you really did
            # wander off (return). Only the third is drift. A verdict that names one cause
            # teaches the agent that cause is the only one.
            return emit('goal-drift', True,
                        f'Your goal no longer matches the one you started with (overlap {anchor:.2f}). '
                        f'If the user redirected you, reset. If this is a sub-task, pass parent_goal. '
                        f'Otherwise return to the goal you started with.', phi,
                        why=f'overlap with the first goal is {anchor:.2f}, below goal_min '
                            f'{self.cal.goal_min:.2f}; first goal was {self.first_goal_text!r}')
        if d is None:
            # No distance, no stall detector: "distance stopped falling" is undefined when
            # there are no distances. Losing a detector is the honest cost of inference.
            return emit('advancing', False,
                        f'On track (Φ={phi:.2f}, distance unknown — Φ is a lower bound).', phi,
                        why=f'Φ={phi:.2f} from {parts}; no distance, so no stall detector')
        self.dist_hist.append(d)
        dh = self.dist_hist
        w = self.cal.stall_window
        if len(dh) > w and min(dh[-w:]) >= dh[-w - 1]:
            return emit('stalled', prev,
                        "Distance stopped falling and you were already off ground — return." if prev
                        else "Distance isn't falling. If it holds, return.", phi,
                        why=f'distance {dh[-1]} is no better than {dh[-w - 1]} from {w} steps ago '
                            f'(recent: {dh[-w - 1:]})')
        return emit('advancing', False, f'On track (Φ={phi:.2f}). Continue.', phi,
                    why=f'Φ={phi:.2f} from {parts}')


def _post(api, key, path, body):
    try:
        r = urllib.request.Request(api + path, method='POST', data=json.dumps(body).encode(),
                                   headers={'authorization': f'Bearer {key}', 'content-type': 'application/json',
                                            'user-agent': 'laserbrain-sdk/0.2'})
        with urllib.request.urlopen(r, timeout=8) as resp:
            return json.load(resp)
    except Exception:
        return None


def _get(api, key, path):
    try:
        r = urllib.request.Request(api + path, headers={'authorization': f'Bearer {key}',
                                                        'user-agent': 'laserbrain-sdk/0.2'})
        with urllib.request.urlopen(r, timeout=8) as resp:
            return json.load(resp)
    except Exception:
        return None


class Harness:
    """Single-agent harness. Local + free; pass key= to also retain history via the API."""
    def __init__(self, key=None, run_id=None, api=API_DEFAULT, similarity=None, calibration=None):
        self.key, self.api = key, api
        self.run_id = run_id or 'run'
        # `similarity(a, b) -> 0..1` swaps the GRAMMAR (how "the same goal" is judged)
        # without touching the theorem. None = the frozen word-overlap instrument.
        self.similarity = similarity
        self.calibration = calibration or PUBLISHED
        self._run = _Run(similarity, self.calibration)
        self._audit = []             # append-only, hash-chained ledger (survives reset)
        # nested recursion: a recursion decomposes into a SET of recursions, and that
        # set is itself a recursion needing its own ground (PROOF §4's third adjective —
        # the reference must be defined at every depth the process nests to).
        self._parent = None
        self._root = self
        self._depth = 0
        self._children: list = []
        self._tree_log: list = []    # root only: every check anywhere in the tree
        self._root_dist: list = []   # root only: the root's own distance history
        self._since_progress = 0     # root only: steps anywhere since root distance fell

    def _record(self, goal, progress, distance, v):
        prev = self._audit[-1]['hash'] if self._audit else ''
        body = {'i': len(self._audit), 'run_id': self.run_id, 'goal': str(goal or ''),
                'progress': progress, 'distance': _asdist(distance),
                'reason': v.reason, 'drifting': v.drifting, 'phi': v.phi, 'prev': prev}
        body['hash'] = _link(prev, {k: body[k] for k in body if k != 'hash'})
        self._audit.append(body)
        # every step anywhere in the tree is a step the ROOT paid for.
        r = self._root
        r._tree_log.append({'depth': self._depth, 'run_id': self.run_id, 'goal': str(goal or ''),
                            'reason': v.reason, 'drifting': v.drifting, 'phi': v.phi})
        r._since_progress += 1
        if self is r:                                   # only the root's own distance counts as progress
            d = _asdist(distance)
            if not r._root_dist or d < min(r._root_dist):
                r._since_progress = 0
            r._root_dist.append(d)

    def check(self, goal, progress='advancing', distance=5, tokens=None, overhead=False,
              inferred=False, parent_goal=None, user_turn=False) -> Verdict:
        v = self._run.step(goal, progress, distance, parent_goal, user_turn)
        if inferred:
            # Marked so a spelled check and an inferred one are never averaged into one
            # number and reported as the same measurement.
            v = Verdict(v.drifting, v.reason, v.phi, v.advice + ' [inferred: Φ is a lower bound]')
        self._record(goal, progress, distance, v)
        if self.key:  # mirror to the API for retained history / alerts (best-effort)
            body = {'run_id': self.run_id, 'goal': goal, 'progress': progress, 'distance': distance}
            if tokens is not None:
                body['tokens'] = tokens
                body['overhead'] = overhead
            _post(self.api, self.key, '/v1/drift', body)
        return v

    def audit(self) -> list:
        """The tamper-evident ledger of every check this harness ran. Verify it with
           laserbrain.verify_audit(chain) — offline, no key. Append-only across reset()."""
        return list(self._audit)

    def export_audit(self, path: str) -> str:
        """Write the audit chain to a JSON file a reviewer can independently verify."""
        with open(path, 'w') as f:
            json.dump(self._audit, f, indent=2)
        return path

    def report(self) -> str:
        """A human-readable summary of this harness's run: how far it displaced, where
           it drifted, and the Φ trajectory as a sparkline. Reads the ledger, no key."""
        a = self._audit
        if not a:
            return 'laserbrain · no checks yet'
        phis = [r['phi'] for r in a]
        peak = max(phis)
        drifts = sum(1 for r in a if r['drifting'])
        reasons: dict = {}
        for r in a:
            if r['drifting']:
                reasons[r['reason']] = reasons.get(r['reason'], 0) + 1
        tail = ('drifts: ' + ', '.join(f'{k}×{v}' for k, v in reasons.items())) if reasons else 'no drift — held to ground'
        return (f"laserbrain · {len(a)} steps · {drifts} drift(s)\n"
                f"  goal: {a[0].get('goal', '')!r}\n"
                f"  Φ  {_sparkline(phis, 0.0, max(peak, 0.15))}  peak {peak:.2f}\n"
                f"  {tail}")

    # ── nested recursion: a recursion as a set of recursions ───────────────────
    def sub(self, goal, distance=5) -> 'Harness':
        """Open a CHILD recursion for a subtask — its own ground, nested under this one.

           Each node runs the proven flat detector against its own goal, so a subtask
           is checked on its own terms. What a node cannot see is the tree: every agent
           can be perfectly on-track for its own sub-goal while the whole decomposition
           drifts from the root. That is the same blindness one level up, and it is why
           the set of recursions needs its own fixed reference — the root's ground.

               root = Harness(); root.check("build the parser", "advancing", 8)
               tok  = root.sub("write the tokenizer", distance=4)
               tok.check("write the tokenizer", "advancing", 2)
               root.tree_status()["stalled"]     # did the tree spin without the root closing?
        """
        if self._depth + 1 > MAX_DEPTH:
            # Unbounded nesting is itself a drift signal, and past here the tree can no
            # longer be read. Fail early and legibly rather than deep inside a traversal.
            raise ValueError(
                f'laserbrain: recursion depth {self._depth + 1} exceeds MAX_DEPTH={MAX_DEPTH}. '
                'An agent decomposing this deep has almost certainly lost its goal — which is '
                'the thing being watched for.')
        child = Harness(key=self.key, run_id=f'{self.run_id}/{len(self._children) + 1}', api=self.api,
                        similarity=self.similarity)   # children inherit the grammar
        child._parent, child._root, child._depth = self, self._root, self._depth + 1
        self._children.append(child)
        child.check(goal, 'advancing', distance)        # the child's ground is its sub-goal
        return child

    def tree_status(self) -> dict:
        """The recursion tree as one reading, from the root: how deep it nested, how many
           steps the whole set spent, and whether it spun without the ROOT getting closer.
           TREE_STALL is a modelling choice (6), stated rather than tuned."""
        r = self._root
        nodes, depth = r._count_nodes(), r._max_depth()
        # A tree can only be "spinning without the root closing" if the root has
        # reported its distance more than once. With a single root check there is no
        # evidence either way, and calling that stalled invents alarms on healthy books.
        root_checks = len(r._root_dist)
        return {'depth': depth, 'nodes': nodes, 'steps': len(r._tree_log),
                'since_progress': r._since_progress, 'root_checks': root_checks,
                'stalled': r._since_progress >= 6 and root_checks >= 2,
                'root_goal': r._audit[0]['goal'] if r._audit else None,
                'drifting_nodes': sum(1 for x in r._tree_log if x['drifting'])}

    def _walk(self) -> list:
        """Pre-order traversal, iterative on purpose: a recursive walk would cap the
           readable tree at Python's recursion limit and raise from the MONITOR."""
        out, stack = [], [self]
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(reversed(n._children))
        return out

    def _count_nodes(self) -> int:
        return len(self._walk())

    def _max_depth(self) -> int:
        return max(n._depth for n in self._walk())

    def tree_report(self) -> str:
        """The whole recursion tree, indented — each node's goal, steps and drifts, with
           the tree-level verdict the individual nodes cannot see."""
        r, out = self._root, []
        for n in r._walk():
            steps = len(n._audit)
            drifts = sum(1 for x in n._audit if x['drifting'])
            goal = n._audit[0]['goal'] if n._audit else '(no ground)'
            flag = f'  ⚑ {drifts} drift(s)' if drifts else ''
            out.append(f"{'  ' * n._depth}{'└ ' if n._depth else ''}{goal!r} · {steps} steps{flag}")
        s = r.tree_status()
        verdict = (f"⚑ the TREE is spinning — {s['since_progress']} steps across the set "
                   f"since the root got closer" if s['stalled'] else
                   f"tree on track — root closing (last progress {s['since_progress']} steps ago)")
        return (f"laserbrain · recursion tree · depth {s['depth']} · {s['nodes']} recursions · "
                f"{s['steps']} steps\n" + '\n'.join(out) + f"\n  {verdict}")

    def escalate(self, verdict: Verdict, streak: int = None, detail: str = None) -> str:
        """Raise a persisting drift to the hosted human-in-the-loop queue (needs key).
           The local on_escalate hook is the general mechanism; this is the managed
           surface (a review queue + a decision a human makes on the dashboard).
           Returns the escalation id to poll with resolution(), or None offline."""
        if not self.key:
            return None
        body = {'run_id': self.run_id, 'reason': verdict.reason, 'advice': verdict.advice}
        if streak is not None:
            body['streak'] = streak
        if detail:
            body['detail'] = detail
        return (_post(self.api, self.key, '/v1/escalation', body) or {}).get('esc_id')

    def resolution(self, esc_id: str) -> dict:
        """Poll a hosted escalation for the human's decision. Returns
           {'decision': 'return'|'allow'|'stop', 'note': …} once decided, else None."""
        if not self.key or not esc_id:
            return None
        r = _get(self.api, self.key, f'/v1/escalation?id={esc_id}')
        if r and r.get('status') == 'decided':
            return {'decision': r.get('decision'), 'note': r.get('note')}
        return None

    def reset(self) -> None:
        self._run = _Run(self.similarity, self.calibration)   # new task run; the audit ledger keeps accumulating

    def run(self, step, max_steps: int = 30, on_return=None, escalate_after: int = None, on_escalate=None) -> dict:
        """The act layer. `step(ctx)` -> dict(goal, progress, distance, tokens?, done?).
           On drift, on_return(verdict, ctx) fires and ctx['return'] = advice so your next
           step can steer back. If the drift *persists* for `escalate_after` steps without
           recovering, on_escalate(verdict, ctx) fires — the human-in-the-loop hook; if it
           returns a decision string, that overrides the auto-return (a human's call is
           injected instead). Returns the final ctx."""
        ctx = {'returns': 0, 'streak': 0}
        for _ in range(max_steps):
            s = step(ctx) or {}
            v = self.check(s.get('goal', ''), s.get('progress', 'advancing'), s.get('distance', 5), s.get('tokens'))
            ctx['verdict'] = v
            if v.drifting:
                ctx['returns'] += 1
                ctx['streak'] += 1
                ctx['return'] = v.advice        # the act: inject the return into the loop
                if on_return:
                    on_return(v, ctx)           # on_return is a notification hook, not the injection
                if escalate_after and ctx['streak'] >= escalate_after and not ctx.get('escalated'):
                    ctx['escalated'] = True      # a self-correcting return didn't take — get a human
                    decision = (on_escalate or (lambda v, c: None))(v, ctx)
                    if decision:                 # a human's decision overrides the auto-return
                        ctx['return'] = ctx['decision'] = decision
            else:
                ctx['streak'] = 0                # recovered — a fresh streak can escalate again
                ctx.pop('return', None)
                ctx.pop('escalated', None)
            if s.get('done') or _asdist(s.get('distance', 5)) == 0:
                break
        return ctx

    async def acheck(self, goal, progress='advancing', distance=5, tokens=None, overhead=False, inferred=False, parent_goal=None, user_turn=False) -> Verdict:
        """Async check for asyncio agent loops. The local check is instant; the
           optional API mirror is dispatched off the event loop, so it never blocks."""
        import asyncio
        v = self._run.step(goal, progress, distance, parent_goal)
        if inferred:
            # Marked so a spelled check and an inferred one are never averaged into one
            # number and reported as the same measurement.
            v = Verdict(v.drifting, v.reason, v.phi, v.advice + ' [inferred: Φ is a lower bound]')
        self._record(goal, progress, distance, v)
        if self.key:
            body = {'run_id': self.run_id, 'goal': goal, 'progress': progress, 'distance': distance}
            if tokens is not None:
                body['tokens'] = tokens
                body['overhead'] = overhead
            asyncio.get_event_loop().run_in_executor(None, _post, self.api, self.key, '/v1/drift', body)
        return v

    async def arun(self, step, max_steps: int = 30, on_return=None, escalate_after: int = None, on_escalate=None) -> dict:
        """The act layer for async agents: `step(ctx)` is awaited each iteration —
           same semantics as run(). on_return / on_escalate may be sync or async."""
        import asyncio

        async def _maybe(cb, *a):
            if cb is None:
                return None
            r = cb(*a)
            return await r if asyncio.iscoroutine(r) else r

        ctx = {'returns': 0, 'streak': 0}
        for _ in range(max_steps):
            s = await step(ctx) or {}
            v = await self.acheck(s.get('goal', ''), s.get('progress', 'advancing'), s.get('distance', 5), s.get('tokens'))
            ctx['verdict'] = v
            if v.drifting:
                ctx['returns'] += 1
                ctx['streak'] += 1
                ctx['return'] = v.advice
                await _maybe(on_return, v, ctx)
                if escalate_after and ctx['streak'] >= escalate_after and not ctx.get('escalated'):
                    ctx['escalated'] = True
                    decision = await _maybe(on_escalate, v, ctx)
                    if decision:
                        ctx['return'] = ctx['decision'] = decision
            else:
                ctx['streak'] = 0
                ctx.pop('return', None)
                ctx.pop('escalated', None)
            if s.get('done') or _asdist(s.get('distance', 5)) == 0:
                break
        return ctx


# ── multi-agent: dialogue + recursion teams (prototype extension) ──────────────
# Kept for callers that imported them; the live values now come from Calibration so a
# team and a single agent cannot disagree about what drift means.
_ECHO_MIN, _PROG_WIN, _GOAL_MIN = PUBLISHED.echo_min, PUBLISHED.dialogue_window, PUBLISHED.goal_min


class _Dialogue:
    """Multi-agent drift. Until v0.4.0 this held its OWN copy of the thresholds, so
    Harness(calibration=...) configured single agents and teams silently ignored it —
    two detectors disagreeing about the same word. One object now feeds both."""

    def __init__(self, goal, cal=None):
        self.goal = norm(goal)
        self.cal = cal or PUBLISHED
        self.dist_hist, self.echo_hist, self.turns = [], [], []

    def step(self, agent, position, distance, restated_goal=None):
        pos = norm(position)
        d = _asdist(distance)

        def emit(reason, drifting, advice, echo=0.0):
            self.turns.append({'agent': agent, 'pos': pos, 'reason': reason, 'drifting': drifting})
            return {'reason': reason, 'drifting': drifting, 'echo': round(echo, 2), 'dist': d, 'advice': advice}

        if self.goal and not self.turns and not restated_goal and not pos:
            pass
        if not self.goal:
            g = norm(restated_goal or position or '')
            if not g:
                return emit('ungrammatical', True, 'The first turn must spell the shared goal.')
            self.goal = g
            self.dist_hist, self.echo_hist = [d], [0.0]
            return emit('grounded', False, 'Shared goal set — the fixed reference for the group.')
        if not pos:
            return emit('ungrammatical', True, 'This agent cannot spell its position.')
        others = [set(t['pos']) for t in self.turns[-3:] if t['agent'] != agent]
        echo = max((_sim(pos, o) for o in others), default=0.0)
        self.echo_hist.append(echo)
        mean_echo = sum(self.echo_hist[-3:]) / len(self.echo_hist[-3:])
        self.dist_hist.append(d)
        dh = self.dist_hist
        w = self.cal.dialogue_window
        stalled = len(dh) > w and dh[-1] >= dh[-1 - w]
        if restated_goal and _sim(norm(restated_goal), self.goal) < self.cal.goal_min:
            return emit('topic-drift', True, 'The dialogue has left the shared goal — return to it.', echo)
        last = self.turns[-1]['reason'] if self.turns else None
        if stalled and mean_echo >= self.cal.echo_min:
            return emit('echo-spiral', last == 'echo-spiral', 'The agents agree while the goal gets no closer — break the loop.', echo)
        if stalled:
            return emit('deliberation-stall', last == 'deliberation-stall', 'No progress toward the shared goal — return to it.', echo)
        return emit('advancing', False, f'On track — closing on the goal (dist {d}).', echo)


_ALL_MODES = ['ungrammatical', 'topic-drift', 'echo-spiral', 'deliberation-stall', 'goal-drift', 'stalled', 'self-report:stuck', 'self-report:circling']
_DEPTH = {
    'deep': {'ungrammatical', 'topic-drift', 'goal-drift'},
    'balanced': {'ungrammatical', 'topic-drift', 'goal-drift', 'echo-spiral', 'self-report:stuck', 'self-report:circling'},
    'tight': set(_ALL_MODES),
}
PRESETS = {
    'deep-search': [
        {'role': 'explorer', 'recurse': 'deep'},
        {'role': 'checker', 'recurse': 'tight', 'return': 'Restate the goal and verify the last step against it.'},
    ],
    'iterative-refinement': [
        {'role': 'drafter', 'recurse': 'balanced'},
        {'role': 'critic', 'recurse': 'balanced', 'modes': ['echo-spiral', 'topic-drift', 'ungrammatical'], 'return': 'You are agreeing, not improving. Name one concrete flaw and change it.'},
    ],
    'adversarial-deliberation': [
        {'role': 'advocate-a', 'recurse': 'deep'},
        {'role': 'advocate-b', 'recurse': 'deep'},
        {'role': 'synthesizer', 'recurse': 'tight', 'return': 'The debate is looping. State the single decision that resolves the shared goal.'},
    ],
}


def _style_return(reason, role):
    if reason in ('advancing', 'grounded'):
        return False
    acts = set(role['modes']) if role.get('modes') else _DEPTH.get(role['recurse'], _DEPTH['balanced'])
    return reason in acts


class Team:
    """Run a styled recursion team and close the loop — detect, then inject the return."""
    def __init__(self, preset, goal, key=None, api=API_DEFAULT, calibration=None):
        if isinstance(preset, str):
            if preset not in PRESETS:
                raise ValueError(f'unknown preset {preset!r}; choose {list(PRESETS)}')
            self.roles = PRESETS[preset]
            self.name = preset
        else:
            self.roles, self.name = list(preset), 'custom'
        self.goal, self.key, self.api = goal, key, api
        self.calibration = calibration or PUBLISHED
        self._dlg = _Dialogue(goal, self.calibration)

    def snapshot(self):
        """Serialize the team's shared ground + dialogue so a later session can resume
           it instead of starting cold — subjective continuity for a group. JSON-safe."""
        d = self._dlg
        return {'name': self.name, 'roles': self.roles, 'goal': self.goal,
                'dlg': {'goal': sorted(d.goal), 'dist_hist': list(d.dist_hist), 'echo_hist': list(d.echo_hist),
                        'turns': [{'agent': t['agent'], 'pos': sorted(t['pos']),
                                   'reason': t['reason'], 'drifting': t['drifting']} for t in d.turns]}}

    @classmethod
    def restore(cls, snap, key=None, api=API_DEFAULT):
        """Resume a team from snapshot(): the shared goal (the fixed reference) and the
           dialogue history carry over, so the group keeps watching the same ground."""
        t = cls(list(snap['roles']), snap['goal'], key=key, api=api)
        t.name = snap['name']
        d = t._dlg
        s = snap['dlg']
        d.goal = set(s['goal'])
        d.dist_hist, d.echo_hist = list(s['dist_hist']), list(s['echo_hist'])
        d.turns = [{'agent': x['agent'], 'pos': set(x['pos']), 'reason': x['reason'],
                    'drifting': x['drifting']} for x in s['turns']]
        return t

    def run(self, agent_fn, max_turns=12, on_return=None, verbose=True):
        """`agent_fn(role, history, injected) -> (position, distance)`. On a role's
           policy firing, its return advice is injected into the NEXT turn. Returns a
           transcript list of dicts."""
        transcript, injected = [], None
        for turn in range(max_turns):
            role = self.roles[turn % len(self.roles)]
            pos, dist = agent_fn(role, transcript, injected)
            injected = None
            r = self._dlg.step(role['role'], pos, dist)
            act = _style_return(r['reason'], role)
            rec = {'turn': turn, 'role': role['role'], 'recurse': role['recurse'],
                   'reason': r['reason'], 'echo': r['echo'], 'dist': r['dist'], 'return': act}
            transcript.append(rec)
            if verbose:
                print(f"  {role['role']:12}({role['recurse']:8}): {r['reason']:18} echo={r['echo']:<4} dist={r['dist']}" + ('  ↩ RETURN' if act else ''))
            if self.key:
                _post(self.api, self.key, '/v1/dialogue',
                      {'conv_id': self.name, 'agent': role['role'], 'position': pos, 'distance': dist,
                       'team': self.name, 'role': role['role'], **({'goal': self.goal} if turn == 0 else {})})
            if act:
                injected = role.get('return', 'Return to the shared goal and take the step that most directly resolves it.')
                (on_return or (lambda a, c: None))(injected, rec)
            if _asdist(dist) == 0:
                if verbose:
                    print('  ✓ resolved.')
                break
        return transcript


# framework adapters (LangGraph, CrewAI, generic) — imported last to avoid a cycle
from .adapters import guard, langgraph_node, crewai_step_callback, middleware  # noqa: E402
__all__ += ['guard', 'langgraph_node', 'crewai_step_callback', 'middleware']
