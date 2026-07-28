"""The second instrument — for work whose goal is supposed to move.

    from laserbrain import Search

    s = Search()
    s.ground('design phronesis.world in the mode of the 1950s New Look')
    s.ground('show laserbrain modes chosen for how fast they teach')
    print(s.reading())        # searching · novelty 0.86 · 2 grounds

laserbrain measures displacement from a reference that cannot move. That is the right
measure for execution and the wrong one for exploration, where moving the goal IS the
work — which is why a productive day of redirection scores Φ 0.55 and the reading is
worth nothing. This measures the other mode.

WHAT IS INVARIANT WHEN THE GOAL IS NOT. Four things, none of which need a fixed ground:

    novelty      is this ground new, or somewhere you have already been?
    commitment   was the last ground worked, or abandoned on sight?
    revisiting   does this ground overlap one you already left?
    narrowing    is novelty falling — is the search closing in?

A search is not failing because it changed direction. It is failing when it returns to
ground it already abandoned, when it abandons ground faster than it can learn anything,
or when it never narrows. Those are measurable and none of them is displacement.

THE SEAM. `settled` is the terminal reading: novelty near zero and commitment rising
means the exploration has become a task, and a task is what laserbrain is for. The two
instruments hand off to each other — `reground` is the seam from the execution side and
`settled` is the seam from this one.

Deliberately no valence, like the harness. `revisiting` is not bad, it is a fact about
the path. What to do about it is yours.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _f

from . import norm


@dataclass
class Reading:
    reason: str
    novelty: float
    commitment: float
    revisit: float
    grounds: int
    advice: str
    trail: str | None = None

    def __str__(self) -> str:                       # pragma: no cover - display only
        return f'{self.reason} · novelty {self.novelty:.2f} · {self.grounds} grounds'


def trailscore(goals) -> str | None:
    """The written form: the accumulated territory, sorted, with the ground count.

    The harness's laserscore writes ONE state. A search has no one state — it has a path,
    so what gets written is the union of everywhere it has been. Null before the first
    ground, for the same reason a laserscore is null when nothing can be spelled.
    """
    if not goals:
        return None
    seen = set()
    for g in goals:
        seen |= norm(g)
    return f'⟨{"|".join(sorted(seen))}⟩ ×{len(goals)}'


class Search:
    """A moving reference, measured. The counterpart to Harness."""

    # A ground abandoned in fewer steps than this was not worked, it was glanced at.
    MIN_COMMITMENT = 2
    # Overlap with an already-abandoned ground that counts as being back where you were.
    REVISIT_MIN = 0.60
    # Novelty below this means the search has stopped finding new territory.
    SETTLED_MAX = 0.15
    WINDOW = 4

    def __init__(self):
        self.goals: list[str] = []
        self.tokens: list[set] = []
        self.steps: list[int] = []          # steps spent on each ground
        self.novelty: list[float] = []
        self._seen: set = set()

    # ── the two calls ─────────────────────────────────────────────────────────
    def step(self):
        """One unit of work on the current ground. Optional, but commitment needs it."""
        if self.steps:
            self.steps[-1] += 1

    def ground(self, goal: str) -> Reading:
        """Declare a new ground. This is the move laserbrain calls drift."""
        t = norm(goal)
        # novelty is measured against everywhere the search has been, not against the
        # last ground — returning to step 2 from step 9 is not novel just because step 9
        # was different.
        new = t - self._seen
        novelty = (len(new) / len(t)) if t else 0.0

        # Overlap with the ground you are LEAVING is not revisiting — it is staying, or
        # restating. Only ground you already walked away from counts, which is why the
        # immediately previous one is excluded from this loop. Without that exclusion,
        # holding one goal reads as returning to it, and `settled` can never fire because
        # `revisiting` always wins first.
        staying = 0.0
        if self.tokens:
            last = self.tokens[-1]
            if t or last:
                staying = len(t & last) / len(t | last)
        revisit = 0.0
        if staying < self.REVISIT_MIN:              # you actually left before coming back
            for prev in self.tokens[:-1]:           # everything already ABANDONED
                if t or prev:
                    j = len(t & prev) / len(t | prev)
                    revisit = max(revisit, j)

        prev_commit = self.steps[-1] if self.steps else 0
        self.goals.append(goal)
        self.tokens.append(t)
        self.steps.append(1)
        self.novelty.append(novelty)
        self._seen |= t
        return self._read(novelty, revisit, prev_commit)

    # ── the reading ───────────────────────────────────────────────────────────
    def _read(self, novelty: float, revisit: float, prev_commit: float) -> Reading:
        n = len(self.goals)
        score = trailscore(self.goals)
        mk = lambda r, a: Reading(r, novelty, prev_commit, revisit, n, a, score)

        if n == 1:
            return mk('opened', 'First ground. Everything from here is measured against the path, not against this.')

        # Order matters and is the definition. Revisiting is checked first because it is
        # the one failure that looks like progress from inside: a new goal, freshly
        # spelled, that you have already explored and left.
        if revisit >= self.REVISIT_MIN:
            return mk('revisiting', f'This ground overlaps one you already left ({revisit:.0%}). '
                                    'You have been here. Either finish it or say why it is different.')

        recent = self.steps[-(self.WINDOW + 1):-1]
        if len(recent) >= self.WINDOW and all(s < self.MIN_COMMITMENT for s in recent):
            return mk('thrashing', f'{len(recent)} grounds in a row abandoned after one step. '
                                   'Nothing was worked long enough to learn whether it was wrong.')

        window = self.novelty[-self.WINDOW:]
        if len(window) >= self.WINDOW and max(window) <= self.SETTLED_MAX:
            return mk('settled', 'Novelty has gone. The search has become a task — '
                                 'ground it in Harness and let laserbrain hold it.')

        if len(window) >= self.WINDOW and window[-1] < window[0]:
            return mk('narrowing', f'Novelty falling ({window[0]:.2f} → {window[-1]:.2f}). '
                                   'The search is closing in.')

        return mk('searching', f'New ground, {novelty:.0%} of it unvisited. The path is still opening.')

    def reading(self) -> Reading:
        """The current reading without declaring a new ground."""
        if not self.goals:
            return Reading('unopened', 0.0, 0.0, 0.0, 0, 'No ground yet.', None)
        return self._read(self.novelty[-1], 0.0, self.steps[-1])

    def territory(self) -> dict:
        """What the search has covered, for logging beside a Verdict rather than inside it."""
        return {'grounds': len(self.goals), 'tokens': len(self._seen),
                'trailscore': trailscore(self.goals),
                'novelty': [round(x, 2) for x in self.novelty],
                'steps': list(self.steps)}
