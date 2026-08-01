#!/usr/bin/env python3
"""test_gate_grok.py — Grok-facing claim/coverage gate behaviours.

Pins the 2026-07-25 improvement list:
  - search_replace is a write tool (claim gate sees Grok edits)
  - search_tool is always allowed (no schema-discovery deadlock)
  - agent identity: env → session → unknown
  - link rows: from= and agent= both count
  - deny howto mentions use_tool for me=grok
"""
import json, os, pathlib, subprocess, sys, tempfile, importlib.util

HOOK = pathlib.Path.home() / (
    'Library/Mobile Documents/com~apple~CloudDocs/phronesis/lasergear/lb_gate.py'
)
ok = True


def show(name, passed, detail=''):
    global ok
    ok = ok and passed
    print(f"  {'✓' if passed else '✗'} {name}" + (f"  — {detail}" if detail else ''))


def load_hook():
    spec = importlib.util.spec_from_file_location('lb_gate_test', HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_gate(ev, env=None, link=None, session=None, sid='test-gate-sid'):
    """Run lb_gate as a subprocess with temp link/session; return (exit, stderr, stdout)."""
    env = dict(os.environ, **(env or {}))
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        tlog = td / 'link.jsonl'
        if link is not None:
            tlog.write_text('\n'.join(json.dumps(r) for r in link) + ('\n' if link else ''))
        else:
            tlog.write_text('')
        env['LASERBRAIN_LINK_LOG'] = str(tlog)
        sdir = td / 'sessions'
        sdir.mkdir()
        # Patch STATE_DIR by writing where the hook looks — we can't easily; instead
        # inject session via monkey through import path for unit checks, and subprocess
        # only for integration of main() with env.
        # For subprocess: point HOME so STATE_DIR = home/.claude/laserbrain
        fake_home = td / 'home'
        (fake_home / '.claude' / 'laserbrain').mkdir(parents=True)
        if session is not None:
            (fake_home / '.claude' / 'laserbrain' / f'{sid}.json').write_text(
                json.dumps(session))
        env['HOME'] = str(fake_home)
        # also clear agent unless set
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({**ev, 'session_id': sid, 'sessionId': sid}),
            text=True, capture_output=True, env=env,
        )
        return proc.returncode, proc.stderr, proc.stdout


def main():
    if not HOOK.exists():
        show('lb_gate exists', False, str(HOOK))
        return 1
    g = load_hook()

    # ── constants ──────────────────────────────────────────────────────────
    show('search_replace in WRITE_TOOLS',
         any('search_replace' == w for w in g.WRITE_TOOLS)
         or any('search_replace' in w for w in g.WRITE_TOOLS))
    show('search_tool in ALWAYS_ALLOW',
         any('search_tool' in a for a in g.ALWAYS_ALLOW))

    # ── edit_target sees Grok search_replace ───────────────────────────────
    ev = {
        'tool_name': 'search_replace',
        'tool_input': {'file_path': '/repo/app/locus/page.tsx', 'old_string': 'a', 'new_string': 'b'},
    }
    tgt = g.edit_target(ev, 'search_replace')
    show('edit_target(search_replace) returns path',
         tgt == '/repo/app/locus/page.tsx', repr(tgt))

    ev_write = {
        'tool_name': 'write',
        'tool_input': {'file_path': '/repo/x.py', 'content': '1'},
    }
    show('edit_target(write) still works',
         g.edit_target(ev_write, 'write') == '/repo/x.py')

    # ── entry_agent ────────────────────────────────────────────────────────
    show('entry_agent from=', g.entry_agent({'from': 'claude'}) == 'claude')
    show('entry_agent agent=', g.entry_agent({'agent': 'grok'}) == 'grok')
    show('entry_agent payload.from',
         g.entry_agent({'payload': {'from': 'grok'}}) == 'grok')

    # ── resolve_me priority ────────────────────────────────────────────────
    old = os.environ.get('LASERBRAIN_AGENT')
    try:
        os.environ['LASERBRAIN_AGENT'] = 'grok'
        show('resolve_me prefers env', g.resolve_me({}, {'agent': 'claude'}) == 'grok')
        del os.environ['LASERBRAIN_AGENT']
        show('resolve_me falls back to session',
             g.resolve_me({}, {'agent': 'grok'}) == 'grok')
        show('resolve_me unknown default', g.resolve_me({}, None) == 'unknown')
    finally:
        if old is not None:
            os.environ['LASERBRAIN_AGENT'] = old
        else:
            os.environ.pop('LASERBRAIN_AGENT', None)

    # ── check_howto agent-aware ────────────────────────────────────────────
    show('howto grok mentions use_tool', 'use_tool' in g.check_howto('grok'))
    show('howto claude mentions mcp__laserbrain',
         'mcp__laserbrain__check_state' in g.check_howto('claude'))

    # ── claimed_by_others: agent= claims + closed waves ────────────────────
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tlog = pathlib.Path(td) / 't.jsonl'
        rows = [
            {'kind': 'wave_open', 'from': 'claude', 'payload': {'wave': 9}},
            {'kind': 'claim', 'agent': 'grok', 'payload': {'wave': 9, 'paths': ['app/locus/']}},
            {'kind': 'claim', 'from': 'claude', 'payload': {'wave': 9, 'paths': ['lasermind/']}},
        ]
        tlog.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
        g.LINK_LOG = tlog
        by = g.claimed_by_others('grok')
        show('grok does not see own claim as other',
             'app/locus/' not in by, repr(by))
        show('grok sees claude claim',
             by.get('lasermind/') == 'claude', repr(by))
        by_c = g.claimed_by_others('claude')
        show('claude sees grok claim via agent=',
             by_c.get('app/locus/') == 'grok', repr(by_c))
        # close wave for claude
        rows.append({'kind': 'wave_close', 'from': 'claude', 'payload': {'wave': 9}})
        tlog.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
        by_after = g.claimed_by_others('grok')
        show('closed agent claims drop',
             'lasermind/' not in by_after, repr(by_after))
        # free-form standing (no open wave at all)
        tlog.write_text('\n'.join(json.dumps(r) for r in [
            {'kind': 'claim', 'agent': 'claude',
             'payload': {'paths': ['phronesis/lasermind/hooks/']}},
        ]) + '\n')
        by_ff = g.claimed_by_others('grok')
        show('free-form claim locks without wave',
             by_ff.get('phronesis/lasermind/hooks/') == 'claude', repr(by_ff))
        tlog.write_text('\n'.join(json.dumps(r) for r in [
            {'kind': 'claim', 'agent': 'claude',
             'payload': {'paths': ['phronesis/lasermind/hooks/']}},
            {'kind': 'done', 'agent': 'claude',
             'payload': {'release_claims': True}},
        ]) + '\n')
        by_rel = g.claimed_by_others('grok')
        show('free-form claim released by done(release_claims)',
             'phronesis/lasermind/hooks/' not in by_rel, repr(by_rel))

    # ── integration: search_tool always allowed even past BLOCK_AFTER ──────
    code, err, out = run_gate(
        {'tool_name': 'search_tool', 'tool_input': {'query': 'laserbrain'}},
        env={'LASERBRAIN_AGENT': 'grok'},
        session={'steps': 20, 'checks': [{'step': 1}], 'agent': 'grok'},
    )
    show('search_tool allowed under gate pressure', code == 0, f'exit={code} err={err[:120]!r}')

    # ── integration: search_replace blocked on foreign claim ───────────────
    code, err, out = run_gate(
        {
            'tool_name': 'search_replace',
            'tool_input': {
                'file_path': '/Users/x/phronesis-world/app/locus/page.tsx',
                'old_string': 'a', 'new_string': 'b',
            },
        },
        env={'LASERBRAIN_AGENT': 'claude'},
        link=[
            {'kind': 'wave_open', 'from': 'claude', 'payload': {'wave': 42}},
            {'kind': 'claim', 'agent': 'grok', 'payload': {'wave': 42, 'paths': ['app/locus/']}},
        ],
        session={'steps': 1, 'checks': [{'step': 1}], 'agent': 'claude'},
    )
    show('search_replace claim-blocked for foreign path',
         code == 2 and 'claim gate' in err, f'exit={code} err={err[:200]!r}')

    # ── integration: own claim not blocked when agent=grok ─────────────────
    code, err, out = run_gate(
        {
            'tool_name': 'search_replace',
            'tool_input': {
                'file_path': '/Users/x/phronesis-world/app/locus/page.tsx',
                'old_string': 'a', 'new_string': 'b',
            },
        },
        env={'LASERBRAIN_AGENT': 'grok'},
        link=[
            {'kind': 'wave_open', 'from': 'claude', 'payload': {'wave': 42}},
            {'kind': 'claim', 'agent': 'grok', 'payload': {'wave': 42, 'paths': ['app/locus/']}},
        ],
        session={'steps': 1, 'checks': [{'step': 1}], 'agent': 'grok'},
    )
    show('search_replace allowed on own claim',
         code == 0, f'exit={code} err={err[:200]!r}')

    # ── integration: coverage deny mentions use_tool for grok ──────────────
    code, err, out = run_gate(
        {'tool_name': 'run_terminal_command', 'tool_input': {'command': 'echo hi'}},
        env={'LASERBRAIN_AGENT': 'grok'},
        session={'steps': 20, 'checks': [{'step': 1}], 'agent': 'grok'},
    )
    show('coverage deny for grok mentions use_tool',
         code == 2 and 'use_tool' in err, f'exit={code} err={err[:220]!r}')

    print('\n  ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
