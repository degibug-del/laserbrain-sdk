"""field.py — read position from laserfield, so the brain stops guessing it.

THE GAP THIS CLOSES. laserbrain's displacement has three terms and software can only
honestly supply two. There is no signal in a tool trace for "how far from done", so
`distance` is spelled by the agent or left as None — and None means a lower-bound Φ and no
stall detector at all. laserbeast does not have this problem: distance is metres. The
field is the virtual equivalent — a state space with a position in it.

WHAT THIS DOES AND DOES NOT MEASURE. Be exact, because the tempting overclaim is right
here. The field emits weather: heat, moisture, rain, vitality, stress, rotation. Those are
NOT your task's completion. What this computes is how far the FIELD has moved from where
it was when you grounded — context displacement, not progress.

    field displacement  =  has the world around the work changed
    task distance       =  how much of the work is left

They are different quantities and conflating them would be the exact overclaim this
project keeps refusing. So `context_distance()` is offered as its own reading, and it is
honest to pass it as `distance=` in ONE case: when the goal is to hold a position in the
field — a daemon, a monitor, an agent whose job is stability rather than completion. For
everything else, read it alongside Φ, not into it.

FAILS OPEN, ALWAYS. A dead daemon returns None, never a number. A monitor that blocks the
thing it monitors is worse than no monitor, and a fabricated distance is worse than an
absent one — absent is a lower bound, fabricated is a lie with a decimal point.

    from laserbrain.field import FieldGround
    fg = FieldGround()                       # samples the field as it is now
    fg.context_distance()                    # 0-10, or None if the field is unreachable
"""
import json
import urllib.request

DEFAULT_URL = 'http://localhost:1618/signal'
# The continuous terms, in a fixed order so the vector means the same thing every time.
# hub_signal and field_sig are summaries of the others and are deliberately excluded —
# including them would weight the same movement twice.
DIMS = ('T', 'Q', 'R', 'V', 'S', 'rotation')


def read_field(url=DEFAULT_URL, timeout=2.0):
    """The field's current state, or None. Never raises: the caller is mid-step."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _vec(state):
    out = []
    for k in DIMS:
        try:
            v = float(state.get(k, 0.0))
        except (TypeError, ValueError):
            v = 0.0
        # rotation is signed and roughly -1..1; the rest are 0..1. Halving its span keeps
        # one dimension from dominating the norm purely by having a wider range.
        out.append(v / 2 if k == 'rotation' else v)
    return out


class FieldGround:
    """The field's position at ground, and displacement from it since.

    Grounded ONCE on construction and never re-sampled as a reference. That is the same
    constraint the goal has: a reference that follows the thing it measures is not a
    reference. If the field is unreachable at construction there is no ground, and every
    later reading returns None rather than silently grounding on the first success.
    """

    def __init__(self, url=DEFAULT_URL, timeout=2.0):
        self.url, self.timeout = url, timeout
        s = read_field(url, timeout)
        self.ground = _vec(s) if s else None
        self.ground_state = s

    @property
    def attached(self):
        return self.ground is not None

    def displacement(self):
        """Euclidean distance in field space from ground, or None. Unbounded above."""
        if self.ground is None:
            return None
        s = read_field(self.url, self.timeout)
        if not s:
            return None
        return sum((a - b) ** 2 for a, b in zip(_vec(s), self.ground)) ** 0.5

    def context_distance(self):
        """Displacement mapped to the harness's 0-10 scale, or None.

        The divisor is the span of the field vector when every dimension has moved its
        full range — reaching 10 means the weather is as different as it can be, not
        merely 'quite different'.
        """
        d = self.displacement()
        if d is None:
            return None
        full = len(DIMS) ** 0.5
        return max(0.0, min(10.0, round(10 * d / full, 1)))

    def reading(self):
        """Everything at once, for logging next to a Verdict rather than inside it."""
        s = read_field(self.url, self.timeout)
        return {'attached': self.attached,
                'context_distance': self.context_distance(),
                'emotion': (s or {}).get('emotion'),
                'season': (s or {}).get('season')}
