"""runtime.py — attach the harness to a runtime instead of to your code.

The Claude Code hook proved the idea and then proved its cost: because a hook runs against
whatever python3 is on PATH, it could not import laserbrain, so the progress rules were
copied into it and pinned together by a test. That works for one runtime. It does not
scale to five, and a drift-detection product maintaining five copies of its drift rules is
a joke with a long setup.

So the logic lives here, once, and a runtime adapter is reduced to the only thing that is
genuinely runtime-specific: the shape of an event. Everything after normalisation —
inference, session recording, the coverage nudge, the file format dogfood.py scores — is
shared.

    from laserbrain.runtime import Session

    s = Session('run-42', goal='ship the sky billboard')
    s.tool('Bash', {'command': 'npm run build'}, ok=False)
    if s.nudge():
        print(s.nudge())           # inject into the agent's context

Any runtime with a tool-call boundary can drive this in about ten lines; see
`from_claude_code`, `from_grok`, and `from_openai_agents` for shapes, and `normalise`
for the contract they all meet.
"""
import json, os, pathlib, datetime, re

from .observe import Observer

NUDGE_AFTER = 8          # steps without a SPELLED check before the reminder fires
DEFAULT_DIR = pathlib.Path.home() / '.claude' / 'laserbrain'

# Internal dispatchers that wrap a real tool name in their arguments.
_WRAPPER_TOOLS = frozenset({
    'use_tool', 'CallMcpTool', 'call_mcp_tool', 'mcp_tool',
})


def agent_of(ev=None):
    """Which agent is writing this session — for multi-agent corpus splits.

    Prefers LASERBRAIN_AGENT (set in each client's MCP env), then runner env, then
    weak hints on the event. Never invents claude/grok from thin air.
    """
    env = (os.environ.get('LASERBRAIN_AGENT') or '').strip().lower()
    if env:
        return env
    if os.environ.get('GROK_SESSION_ID') or os.environ.get('GROK_HOOK_EVENT'):
        return 'grok'
    if os.environ.get('CLAUDE_SESSION_ID'):
        return 'claude'
    if isinstance(ev, dict):
        if ev.get('sessionId') is not None or ev.get('toolName') is not None:
            return 'grok'
        if ev.get('session_id') is not None or ev.get('tool_name') is not None:
            return 'claude'
    return 'unknown'


def coerce_args(args):
    """toolInput may arrive as a dict or as a JSON object string."""
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        s = args.strip()
        if s.startswith('{') or s.startswith('['):
            try:
                j = json.loads(s)
                if isinstance(j, dict):
                    return j
            except Exception:
                pass
        return {'_': args}
    if args is None:
        return {}
    return {'_': args}


def unwrap_tool_args(tool, args):
    """Peel use_tool / CallMcpTool envelopes until we reach real tool + args.

    Two shapes exist:

      1. toolName is the dispatcher (`use_tool`); toolInput holds
         {tool_name, tool_input: real_args}.
      2. Grok rewrites toolName to `server__tool` for matchers (hooks.md) but
         still leaves toolInput as the outer envelope. Peeling only when tool
         is in _WRAPPER_TOOLS left every check_state with empty goals
         (corpus 2026-07-25: goal='', progress='', distance=None while checks
         still incremented — the gate reopened, dogfood got nothing).

    Peel while the current args look like an envelope and not like flat tool
    arguments (e.g. check_state's goal/progress). Bound the loop so a weird
    payload cannot hang the hook.
    """
    tool = str(tool or '')
    args = coerce_args(args)
    for _ in range(4):
        nested_name = str(
            args.get('tool_name') or args.get('toolName') or args.get('name') or ''
        )
        nested_in = (
            args.get('tool_input') if args.get('tool_input') is not None
            else args.get('toolInput') if args.get('toolInput') is not None
            else args.get('arguments') if args.get('arguments') is not None
            else args.get('parameters') if args.get('parameters') is not None
            else args.get('input') if args.get('input') is not None
            else None
        )
        looks_envelope = nested_in is not None and (
            tool in _WRAPPER_TOOLS
            or nested_name
            or ('tool_input' in args or 'toolInput' in args)
        )
        # Flat check_state / reset args: do not peel past goal/progress.
        if looks_envelope and (args.get('goal') is not None or args.get('progress') is not None):
            if tool not in _WRAPPER_TOOLS:
                break
        if not looks_envelope:
            break
        if nested_name:
            tool = nested_name
        args = coerce_args(nested_in)
    return tool, args


def session_id_of(ev):
    """session id from a hook event or the runner's env (Grok / Claude).

    The last resort is NOT the literal 'unknown'. On 2026-07-25 a Claude session and a
    Grok session ran in tandem and both fell back to it: 50 steps landed in one file with
    two runs interleaved and catches attributed to whichever agent happened to be next.
    A merged session is worse than a missing one — dogfood scores it as though it were a
    single run and reports a confident wrong answer.

    The parent pid is the agent process that spawned this hook, so it is stable across
    every event of one run and different between concurrent runs. Two agents would have
    to share a parent to collide, which is far rarer than sharing a constant.
    """
    if not isinstance(ev, dict):
        ev = {}
    explicit = (ev.get('session_id') or ev.get('sessionId')
                or os.environ.get('GROK_SESSION_ID')
                or os.environ.get('CLAUDE_SESSION_ID'))
    if explicit:
        return str(explicit)
    return f'unattributed-{os.getppid()}'


_PROMPT_WRAPPERS = ('user_query', 'user_prompt', 'query', 'prompt')


def clean_prompt(text):
    """Unwrap a runtime's prompt envelope.

    Grok delivers prompts as '<user_query>\n/hello\n</user_query>'. Stored raw, the
    ground goal becomes markup and every later goal comparison is made against tags.
    """
    t = str(text or '').strip()
    for tag in _PROMPT_WRAPPERS:
        open_t, close_t = f'<{tag}>', f'</{tag}>'
        if open_t in t and close_t in t:
            t = t[t.index(open_t) + len(open_t):t.index(close_t)]
    return t.strip()


def normalise(ev):
    """Any runtime's event -> (kind, tool, args, ok, text).

    kind is 'prompt' | 'tool' | 'check' | 'reset' | None. This is the ONLY part an
    adapter has to care about; returning None for kind means "ignore this event", which
    is the right answer for most of what a runtime emits.

    Accepts Claude Code snake_case and Grok Build camelCase side by side.
    """
    if not isinstance(ev, dict):
        return (None, '', {}, True, '')

    tool = str(ev.get('tool_name') or ev.get('toolName') or ev.get('name') or '')
    args = (ev.get('tool_input') if ev.get('tool_input') is not None
            else ev.get('toolInput') if ev.get('toolInput') is not None
            else ev.get('arguments') if ev.get('arguments') is not None
            else ev.get('parameters') if ev.get('parameters') is not None
            else ev.get('input') if ev.get('input') is not None
            else {})
    tool, args = unwrap_tool_args(tool, args)

    # Prompt capture: only when this is not also a tool event.
    prompt = ev.get('prompt')
    if prompt is None:
        prompt = ev.get('userPrompt') if ev.get('userPrompt') is not None else ev.get('promptText')
    if prompt is not None and not tool:
        return ('prompt', '', {}, True, clean_prompt(prompt))

    if not tool:
        return (None, '', {}, True, '')

    resp = (ev.get('tool_response') if ev.get('tool_response') is not None
            else ev.get('toolResult') if ev.get('toolResult') is not None
            else ev.get('output') if ev.get('output') is not None
            else {})
    ok = True
    event_name = str(ev.get('hookEventName') or ev.get('hook_event_name') or '')
    if 'failure' in event_name.lower():
        ok = False
    if isinstance(resp, dict):
        code = resp.get('exit_code')
        if code is None:
            code = resp.get('exitCode')
        if isinstance(code, int):
            ok = code == 0
        elif resp.get('error') or resp.get('is_error') or resp.get('isError'):
            ok = False
    elif isinstance(resp, str) and resp.strip().lower().startswith('error'):
        ok = False

    # A failure whose evidence is INSIDE the text used to sail through as success.
    #
    # Everything above only fires when a failure announces itself structurally: an
    # exit_code, an isError flag, or a string that literally begins with "error". Most
    # real failures do neither. "timeout: command not found" is a bare stderr line. A
    # denied tool call arrives as ordinary MCP content. A compiler error sits in the
    # middle of 200 lines of output. All three were recorded as ok.
    #
    # The cost was recall itself. Recall is hits over CATCHES, and a catch is exactly an
    # independently-detected failure. With this recogniser blind to unlabelled failures,
    # 21 sessions carried ZERO catches on 2026-07-26 — a day containing two failed
    # archives, a rejected upload and a missing binary — so the denominator was always
    # zero and recall was unobtainable no matter how far coverage rose. Raising the
    # coverage floor that morning was necessary and nowhere near sufficient.
    #
    # Deliberately narrow. These are unambiguous failure signatures, anchored to line
    # starts where possible, because a false catch is worse than a missed one: catches
    # are the GROUND TRUTH the harness is scored against, so inventing them would let the
    # instrument grade itself against its own noise.
    if ok:
        probe = (resp if isinstance(resp, str) else json.dumps(resp, default=str))[:4000]
        if _looks_failed(probe):
            ok = False

    low_tool = tool.lower()
    if low_tool.endswith('reset_task') or low_tool.endswith('__reset_task'):
        return ('reset', tool, args, True, '')
    kind = 'check' if low_tool.endswith('check_state') else 'tool'
    text = json.dumps(resp, default=str)[:600] if resp else ''
    return (kind, tool, args, ok, text)


class Session:
    """A recorded run, in the shape dogfood.py scores.

    Deliberately does NOT call check_state itself. It cannot: distance is not inferable
    and the goal must come from the task as first stated, not from the runtime's guess at
    what the agent is doing now. It counts, it infers what is inferable, and it interrupts
    when coverage lapses. The spelled check stays the agent's to make.
    """

    def __init__(self, session_id, goal=None, directory=None, nudge_after=NUDGE_AFTER):
        self.path = pathlib.Path(directory or DEFAULT_DIR) / f'{session_id}.json'
        self.nudge_after = nudge_after
        self.d = self._load(session_id)
        if goal and not self.d.get('goal'):
            self.d['goal'] = str(goal)[:400]
        self._obs = Observer(self.d.get('goal') or 'unset')

    def _load(self, sid):
        try:
            d = json.loads(self.path.read_text())
        except Exception:
            d = {'id': sid, 'started': datetime.datetime.now().isoformat(timespec='seconds'),
                 'goal': None, 'steps': 0, 'checks': [], 'inferred': [], 'catches': [],
                 'events': []}
        if not d.get('agent'):
            d['agent'] = agent_of()
        return d

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.d.get('agent'):
            self.d['agent'] = agent_of()
        self.path.write_text(json.dumps(self.d, indent=2))
        return self

    # ── the three things a runtime can tell us ──────────────────────────────
    def prompt(self, text):
        """The task as first stated. Captured ONCE, and only at the true start of a run.

        After a reset_task the goal is deliberately absent, and the next thing the user
        types is usually a continuation rather than a task — on 2026-07-25 a session
        recorded its ground as 'do all', which makes every later goal-drift verdict
        meaningless. Following a reset the ground comes from the next SPELLED check,
        where the agent states the goal explicitly, not from whatever was typed next.
        """
        t = clean_prompt(text)
        if not t:
            return self
        if self.d.get('goal') or self.d.get('was_reset'):
            return self
        self.d['goal'] = t[:400]
        self._obs = Observer(self.d['goal'])
        return self.save()

    def tool(self, name, args=None, ok=True):
        self.d['steps'] += 1
        self._obs.record(name, args, ok=ok)
        self.d['events'] = [{'sig': e['sig'], 'ok': e['ok']} for e in self._obs.events][-40:]
        self.d['inferred'].append({'step': self.d['steps'], 'progress': self._obs.progress(),
                                   'why': self._obs.why()})
        self.d['inferred'] = self.d['inferred'][-200:]
        if not ok:
            # A failed call is a guard failing or a test going red — dogfood ground truth,
            # recorded without anyone judging anything.
            self.d['catches'].append({'step': self.d['steps'], 'by': 'build',
                                      'what': f'failed call: {name}'})
        return self.save()

    def check(self, goal, progress, distance, drifting, reason=None, phi=None):
        """A SPELLED check. Inputs are recorded so the session can be replayed under a
        different calibration — see calibrate.py.

        `reason` and `phi` are the verdict as returned, kept so the corpus can be asked
        WHICH signal fired. Without them every fire is an undifferentiated True and the
        question "do goal-drift fires cluster on goal restatements" cannot be asked of the
        data at all. Optional, because older callers pass four positional arguments.
        """
        self.d['steps'] += 1
        rec = {'step': self.d['steps'], 'drifting': bool(drifting),
               'goal': str(goal)[:400], 'progress': str(progress),
               'distance': distance}
        if reason is not None:
            rec['reason'] = str(reason)
        if phi is not None:
            rec['phi'] = phi
        self.d['checks'].append(rec)
        # After a reset the agent's own spelled goal is authoritative — it is the task as
        # the agent states it, which is exactly what a ground should be.
        if not self.d.get('goal') and str(goal).strip():
            self.d['goal'] = str(goal)[:400]
            self.d['was_reset'] = False
            self._obs = Observer(self.d['goal'])
        return self.save()

    def reset(self):
        """Close the current segment and start a new one.

        ARCHIVE, then clear. This used to be a bare wipe, and it was quietly destroying the
        entire dogfood corpus: the design tells an agent to reset_task on every genuinely
        new task, so a working session resets five or six times and each reset threw away
        that segment's checks, fires and catches. On 2026-07-25 a ~100-step session was on
        disk as "steps: 4", and the whole nine-session corpus held 0 fires — while the
        transcript of one session mentioned check_state on 1695 lines. The harness had been
        firing all along; the record of it was deleted at every task boundary.

        A segment is also the RIGHT unit to score, not merely a salvaged one. A reset is a
        wave boundary: one declared goal, one interval, one denominator. Coverage over a
        whole session averages a disciplined stretch together with the ungrounded scramble
        before the first check; per segment, each is visible for what it was.
        """
        if int(self.d.get('steps', 0)) > 0:
            self.d.setdefault('segments', []).append({
                'goal': self.d.get('goal'),
                'steps': int(self.d.get('steps', 0)),
                'checks': self.d.get('checks', []),
                'inferred': self.d.get('inferred', []),
                'catches': self.d.get('catches', []),
                'ended': datetime.datetime.now().isoformat(timespec='seconds'),
            })
        self.d.update(steps=0, checks=[], inferred=[], catches=[], events=[], goal=None,
                      was_reset=True)
        self._obs = Observer('unset')
        return self.save()

    # ── what it gives back ──────────────────────────────────────────────────
    @property
    def coverage(self):
        return (len(self.d['checks']) / self.d['steps']) if self.d['steps'] else 0.0

    def steps_since_check(self):
        last = self.d['checks'][-1]['step'] if self.d['checks'] else 0
        return self.d['steps'] - last

    def nudge(self):
        """The reminder, or None. Fires every `nudge_after` steps without a spelled check
        rather than once, because one message scrolls away."""
        since = self.steps_since_check()
        if since < self.nudge_after or since % self.nudge_after:
            return None
        return (f'laserbrain: {since} steps since your last check_state '
                f'(coverage {self.coverage:.0%} over {self.d["steps"]} steps). '
                f'dogfood.py withholds any detection result below 50%. Call check_state '
                f'now with your CURRENT goal, progress and distance 0-10.')

    def coverage_warning(self):
        """Nudge text whenever coverage has lapsed (not only on the modulo edge).

        Used by Grok Stop hooks: PostToolUse stdout is ignored there, so the only
        injection point that reaches the model is a stop-gate reason.
        """
        since = self.steps_since_check()
        if since < self.nudge_after:
            return None
        return (f'laserbrain: {since} steps since your last check_state '
                f'(coverage {self.coverage:.0%} over {self.d["steps"]} steps). '
                f'dogfood.py withholds any detection result below 50%. Call check_state '
                f'now with your CURRENT goal, progress and distance 0-10.')

    def feed(self, ev):
        """Drive the session from one raw runtime event. Returns a nudge or None.

        The check branch reads the verdict with `verdict_of` rather than by searching the
        raw text for '"drifting": true'. That search was here until 2026-07-25 and it never
        matched a real response: an MCP result arrives wrapped as
        {"content":[{"type":"text","text":"{...}"}]}, and serialising it escapes the inner
        quotes to \\"drifting\\". Every fire was written to disk as drifting=False while the
        agent was being told, in the same call, that it had drifted.

        The cost was the corpus. 204 checks over 10 sessions recorded ZERO fires, 104 of
        them below the 0.30 overlap that defines goal-drift. dogfood.py reported
        "PRECISION undefined — the harness never fired in these sessions", which read as a
        quiet instrument and was a deaf one. The 8% precision we publish had to be
        recovered from chat transcripts because the session files never held it.
        """
        kind, tool, args, ok, text = normalise(ev)
        if kind == 'prompt':
            self.prompt(text); return None
        if kind == 'reset':
            self.reset(); return None
        if kind == 'check':
            v = verdict_of(text)
            self.check(args.get('goal', ''), args.get('progress', ''), args.get('distance'),
                       v['drifting'], reason=v['reason'], phi=v['phi'])
            return None
        if kind == 'tool':
            self.tool(tool, args, ok)
            return self.nudge()
        return None


# ── adapter shapes — thin wrappers over the same path ───────────────────────
# Failure signatures that a tool reports in its TEXT rather than in a status field.
#
# Kept deliberately short and specific. A catch is the ground truth this harness is scored
# against, so a false catch is strictly worse than a missed one: it would let the instrument
# grade itself against noise it generated. Every entry here is a phrase that does not occur
# in ordinary successful output.
#
# Anchored where possible. "error" alone is useless — it matches "no errors", "error
# handling", and every log line about the concept. `^error` and ": error:" (the compiler
# convention) do not.
_FAIL_PATTERNS = [
    r'^\s*error\b',                     # a line that begins by declaring failure
    r':\s*error:',                      # clang/swift/tsc convention: file:line: error:
    r'command not found',
    r'no such file or directory',
    r'permission denied',
    r'^\s*Traceback \(most recent call last\)',
    r'\bBUILD FAILED\b', r'\bEXPORT FAILED\b', r'\bARCHIVE FAILED\b',
    r'\bTHIS CALL DID NOT RUN\b',       # a hook denied it — a real, independently-caught stop
    r'\bfatal:', r'\bfatal error\b',
    r'^\s*FAIL\b',
    r'\bexit code [1-9]', r'\bexit status [1-9]',
    r'\bAssertionError\b', r'\bSyntaxError\b',
]
_FAIL_RE = re.compile('|'.join(_FAIL_PATTERNS), re.IGNORECASE | re.MULTILINE)

# Phrases that LOOK like failures and are not. A guard that reports "0 errors" or a test
# suite that says "no such file or directory: expected" would otherwise manufacture catches.
_NOT_FAIL_RE = re.compile(
    r'\b(0|no|zero)\s+(errors?|failures?)\b|\berrors?:\s*0\b|\bno errors found\b',
    re.IGNORECASE)


def _looks_failed(text: str) -> bool:
    """True when the TEXT of a tool result carries an unambiguous failure signature.

    Used only after the structural checks (exit_code, isError) have declined to call it a
    failure — so this catches the large class of tools that report failure in prose.
    """
    if not text:
        return False
    if _NOT_FAIL_RE.search(text):
        return False
    return bool(_FAIL_RE.search(text))


def verdict_of(text):
    """Read {drifting, reason, phi} out of a check response, whatever shape it arrives in.

    Parses rather than pattern-matches. The shapes that occur in practice are a bare dict,
    a raw JSON string, and — the one that broke this for the entire corpus — the MCP
    envelope {"content":[{"type":"text","text":"{...}"}]}, where the payload is JSON
    carried inside a JSON string and every quote is escaped.

    Returns drifting=False for anything unreadable. That direction is deliberate: an
    unparsed response must not manufacture a fire, because a false fire in the corpus is
    indistinguishable from a real one and would inflate precision. A missed fire at least
    shows up as silence, which is what this bug looked like.
    """
    def walk(x, depth=0):
        if depth > 6 or isinstance(x, bool):
            return None
        if isinstance(x, dict):
            if isinstance(x.get('drifting'), bool):
                return x
            for val in x.values():
                got = walk(val, depth + 1)
                if got is not None:
                    return got
        elif isinstance(x, (list, tuple)):
            for val in x:
                got = walk(val, depth + 1)
                if got is not None:
                    return got
        elif isinstance(x, str):
            t = x.strip()
            if t[:1] in ('{', '['):
                try:
                    return walk(json.loads(t), depth + 1)
                except Exception:
                    return None
        return None

    found = walk(text) or {}
    return {'drifting': bool(found.get('drifting')),
            'reason': str(found.get('reason') or 'unparsed'),
            'phi': found.get('phi')}


def from_claude_code(ev, directory=None):
    """Claude Code hook payload (PostToolUse / UserPromptSubmit) on stdin."""
    s = Session(session_id_of(ev), directory=directory)
    if not s.d.get('agent') or s.d.get('agent') == 'unknown':
        s.d['agent'] = agent_of(ev)
    return s.feed(ev)


def from_grok(ev, directory=None):
    """Grok Build hook payload (camelCase: sessionId, toolName, toolInput, toolResult).

    Same session directory as Claude so tandem runs share one coverage corpus.
    """
    s = Session(session_id_of(ev), directory=directory)
    if not s.d.get('agent') or s.d.get('agent') == 'unknown':
        s.d['agent'] = agent_of(ev)
    return s.feed(ev)


def from_openai_agents(run_id, name, arguments, error=None, directory=None):
    """OpenAI Agents SDK style: a tool name, its arguments, and an optional error."""
    return Session(run_id, directory=directory).feed(
        {'name': name, 'arguments': arguments, 'output': {'error': error} if error else {}})
