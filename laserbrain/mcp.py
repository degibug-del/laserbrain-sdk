"""laserbrain as an MCP server — offline, stdlib only, no account.

    laserbrain mcp          # speaks JSON-RPC on stdin/stdout

Point any MCP client at that command and the agent gets the harness. No key, no network,
no telemetry, nothing to sign up for.

WHY THIS SHIPS IN THE PACKAGE

Until 0.25.0 `pip install laserbrain` gave you a library and a CLI, and the only way to
reach the instrument over MCP was the hosted Worker. The stdio server that Diego actually
uses is a Node file living on one machine, distributed to nobody. So the way the author
uses his own product was the one way a user could not.

That is backwards for a tool whose headline claim is that the check is local, free, and
needs no server. Most agents cannot `import laserbrain` — they speak MCP. Making the local
path reachable over MCP is what makes "free and offline" true for agents rather than only
for Python programs.

WHY THERE IS NO DEPENDENCY

MCP over stdio is JSON-RPC in newline-delimited JSON. That is `json` and `sys.stdin`. An
SDK would add a dependency to a package that has none, for a protocol that fits in this
file. Keeping it stdlib means the offline path has nothing to install, nothing to break at
version boundaries, and nothing to audit.

WHAT IT DELIBERATELY DOES NOT EXPOSE

Only tools that work with the network unplugged. The field, Alice, the spectral grammar
and the persisted self are real capabilities, and every one of them is a call to a server —
offering them here would produce an MCP server that silently fails the moment it is used
the way it advertises. They live on the hosted Worker, which is honest about being a
server. `capabilities` says so, in as many words, rather than leaving a user to discover
it by failure.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from . import Harness, Verdict, __version__, ground_score, laserscore, norm

PROTOCOL = '2024-11-05'

# One process is one agent's session. The ground lives here, in memory, for exactly as
# long as the client holds the pipe open — which is the correct lifetime: a ground that
# outlived the conversation would be measuring a task nobody is doing any more.
_state: dict[str, Any] = {'harness': None, 'checks': []}


def _verdict_dict(v: Verdict) -> dict[str, Any]:
    return {
        'drifting': v.drifting,
        'reason': v.reason,
        'phi': round(v.phi, 4),
        'anchored': round(v.anchored, 4) if v.anchored is not None else None,
        'laserscore': v.laserscore,
        'advice': v.advice,
        'ground_score': round(ground_score(v.phi), 4),
    }


# ── the tools ────────────────────────────────────────────────────────────────────────
def _check_state(args: dict) -> dict:
    goal = str(args.get('goal', '')).strip()
    if not goal:
        return {'error': 'check_state needs a goal — the ground is set from it and frozen'}
    if _state['harness'] is None:
        _state['harness'] = Harness()
    v = _state['harness'].check(goal, str(args.get('progress', 'advancing')),
                                args.get('distance'))
    out = _verdict_dict(v)
    _state['checks'].append({'goal': goal, **out})
    return out


def _reset_task(args: dict) -> dict:
    _state['harness'] = None
    _state['checks'] = []
    return {'ok': True,
            'note': 'ground and history cleared — your next check_state sets a new ground'}


def _get_history(args: dict) -> dict:
    ch = _state['checks']
    spelled = len(ch)
    drifts = sum(1 for c in ch if c['drifting'])
    return {'checks': ch[-int(args.get('limit', 20)):], 'total': spelled, 'drifting': drifts}


def _similarity(args: dict) -> dict:
    a, b = str(args.get('a', '')), str(args.get('b', ''))
    na, nb = norm(a), norm(b)
    inter = na & nb
    union = na | nb
    return {'a_tokens': sorted(na), 'b_tokens': sorted(nb),
            'overlap': round(len(inter) / len(union), 4) if union else 0.0,
            'shared': sorted(inter)}


def _laserscore(args: dict) -> dict:
    return {'laserscore': laserscore(str(args.get('goal', '')),
                                     str(args.get('progress', 'advancing')),
                                     args.get('distance'))}


def _capabilities(args: dict) -> dict:
    return {
        'version': __version__,
        'transport': 'stdio (JSON-RPC, newline-delimited)',
        'offline': True,
        'account_required': False,
        'local_tools': sorted(TOOLS),
        'not_here': {
            'why': 'these are calls to a server, and this server is your own machine',
            'tools': ['read_field', 'speak_to_field', 'ask_alice', 'analyze_language',
                      'compare_phrasings', 'remember_self', 'resume_self', 'forget_self'],
            'where': 'https://laserbrain-mcp.degibug.workers.dev/mcp',
        },
        'note': 'The check is a pure local function. It runs with the network unplugged '
                'and keeps working if the hosted service disappears.',
    }


TOOLS: dict[str, dict[str, Any]] = {
    'check_state': {
        'fn': _check_state,
        'description': (
            'Spell where you are. The FIRST call freezes the ground — every later reading is '
            'measured against it, which is what makes this different from asking yourself. '
            'Call it each step. Returns one of nine verdicts, Φ, and what to do.'),
        'schema': {
            'type': 'object',
            'properties': {
                'goal': {'type': 'string', 'description': 'What you are working on, in your own words.'},
                'progress': {'type': 'string', 'enum': ['advancing', 'stuck', 'circling'],
                             'description': 'Honestly. A false "advancing" wastes the reading.'},
                'distance': {'type': 'number',
                             'description': 'How far from done, 0-10. 0 means finished.'},
            },
            'required': ['goal'],
        },
    },
    'reset_task': {
        'fn': _reset_task,
        'description': ('Start a genuinely new task. Clears the ground so the next check_state '
                        'sets a fresh one. Use when the user redirects you — NOT to escape a '
                        'drift verdict, which is the one thing that makes the reading useless.'),
        'schema': {'type': 'object', 'properties': {}},
    },
    'get_history': {
        'fn': _get_history,
        'description': 'The checks spelled so far this session, and how many were drifting.',
        'schema': {'type': 'object',
                   'properties': {'limit': {'type': 'number', 'description': 'Default 20.'}}},
    },
    'similarity': {
        'fn': _similarity,
        'description': ('Token overlap between two statements under the same normaliser the '
                        'harness uses. Useful for asking whether two goals are the same goal.'),
        'schema': {'type': 'object',
                   'properties': {'a': {'type': 'string'}, 'b': {'type': 'string'}},
                   'required': ['a', 'b']},
    },
    'laserscore': {
        'fn': _laserscore,
        'description': 'The compact one-line reading of a state, without setting or touching a ground.',
        'schema': {'type': 'object',
                   'properties': {'goal': {'type': 'string'},
                                  'progress': {'type': 'string'},
                                  'distance': {'type': 'number'}},
                   'required': ['goal']},
    },
    'capabilities': {
        'fn': _capabilities,
        'description': 'What this server can do offline, and what needs the hosted one.',
        'schema': {'type': 'object', 'properties': {}},
    },
}


# ── JSON-RPC, on a pipe ──────────────────────────────────────────────────────────────
def _tool_list() -> list[dict]:
    return [{'name': n, 'description': t['description'], 'inputSchema': t['schema']}
            for n, t in TOOLS.items()]


def handle(msg: dict) -> dict | None:
    """One request in, one response out. None means notification — say nothing back."""
    method, mid = msg.get('method'), msg.get('id')

    if method == 'initialize':
        return {'jsonrpc': '2.0', 'id': mid, 'result': {
            'protocolVersion': PROTOCOL,
            'capabilities': {'tools': {}},
            'serverInfo': {'name': 'laserbrain', 'version': __version__},
        }}
    if method in ('notifications/initialized', 'initialized'):
        return None
    if method == 'ping':
        return {'jsonrpc': '2.0', 'id': mid, 'result': {}}
    if method == 'tools/list':
        return {'jsonrpc': '2.0', 'id': mid, 'result': {'tools': _tool_list()}}
    if method == 'tools/call':
        params = msg.get('params') or {}
        name = params.get('name')
        tool = TOOLS.get(name)
        if tool is None:
            return {'jsonrpc': '2.0', 'id': mid,
                    'error': {'code': -32602, 'message': f'no such tool: {name}'}}
        try:
            out = tool['fn'](params.get('arguments') or {})
        except Exception as e:      # a tool that throws must not take the server with it
            return {'jsonrpc': '2.0', 'id': mid, 'result': {
                'content': [{'type': 'text', 'text': f'{type(e).__name__}: {e}'}],
                'isError': True}}
        return {'jsonrpc': '2.0', 'id': mid, 'result': {
            'content': [{'type': 'text', 'text': json.dumps(out, indent=2)}]}}

    if mid is None:
        return None                 # an unknown notification is not an error
    return {'jsonrpc': '2.0', 'id': mid,
            'error': {'code': -32601, 'message': f'no such method: {method}'}}


def serve(stdin=None, stdout=None) -> int:
    """Read newline-delimited JSON-RPC until the pipe closes.

    stderr is left alone: an MCP client parses stdout, so anything printed there that is
    not a response corrupts the stream. Diagnostics belong on stderr and nowhere else.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            # Malformed input is the client's bug, not a reason to die mid-session.
            print(json.dumps({'jsonrpc': '2.0', 'id': None,
                              'error': {'code': -32700, 'message': 'parse error'}}),
                  file=stdout, flush=True)
            continue
        res = handle(msg)
        if res is not None:
            print(json.dumps(res), file=stdout, flush=True)
    return 0
