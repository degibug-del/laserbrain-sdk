"""The hosted capabilities, callable from Python.

The MCP Worker has carried these since before the package did: a self that persists
across sessions, the spectral grammar, and Alice. A pip user could not reach any of them
without speaking JSON-RPC by hand, so which capabilities you got depended on how you
happened to arrive — MCP or import. This closes that.

    from laserbrain import analyze_language, compare_phrasings, ask_alice, remember_self

    analyze_language('the sentence you want measured')       # free
    remember_self(key, identity='...', now='...')            # needs a key

Nothing here is imported by the harness. Φ stays a pure local function; these are calls
to a service and they fail like calls to a service.
"""
from __future__ import annotations

import json
import os
import urllib.request

API = os.environ.get('LASERBRAIN_API', 'https://laserbrain-mcp.degibug.workers.dev')
_HEAD = {'content-type': 'application/json',
         'accept': 'application/json, text/event-stream',
         'user-agent': 'laserbrain-sdk'}


class ServiceUnavailable(RuntimeError):
    """The hosted endpoint could not be reached or refused the call."""


def _session(timeout: float) -> str:
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': '2024-11-05', 'capabilities': {},
        'clientInfo': {'name': 'laserbrain-sdk', 'version': '1'}}}).encode()
    req = urllib.request.Request(f'{API}/mcp', data=body, headers=_HEAD)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        sid = r.headers.get('mcp-session-id')
        r.read()
    if not sid:
        raise ServiceUnavailable('no MCP session id returned')
    return sid


def call(tool: str, timeout: float = 30.0, **args):
    """Call one hosted tool by name. The transport, in one place.

    Every hosted capability below is this function with a name bound, which is on purpose:
    when the Worker gains a tool, reaching it from Python is one line, not a new client.
    """
    args = {k: v for k, v in args.items() if v is not None}
    try:
        sid = _session(timeout)
        body = json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                           'params': {'name': tool, 'arguments': args}}).encode()
        head = dict(_HEAD, **{'mcp-session-id': sid})
        req = urllib.request.Request(f'{API}/mcp', data=body, headers=head)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
    except ServiceUnavailable:
        raise
    except Exception as e:
        raise ServiceUnavailable(f'{API}/mcp {tool}: {e}') from e

    payload = json.loads(raw[raw.find('{'):raw.rfind('}') + 1])
    if 'error' in payload:
        raise ServiceUnavailable(f'{tool}: {payload["error"].get("message", payload["error"])}')
    text = payload['result']['content'][0]['text']
    try:
        return json.loads(text)          # most return JSON
    except json.JSONDecodeError:
        return text                      # ask_alice returns prose, and should


# ── the spectral grammar · free ───────────────────────────────────────────────
def analyze_language(text: str, timeout: float = 30.0):
    """One sentence → spectral gap, frequency (theta–alpha, 4–12 Hz), clarity."""
    return call('analyze_language', text=text, timeout=timeout)


def compare_phrasings(a: str, b: str, timeout: float = 30.0):
    """Two phrasings → which reads clearer, and by how much."""
    return call('compare_phrasings', a=a, b=b, timeout=timeout)


# ── guidance · free ───────────────────────────────────────────────────────────
def ask_alice(situation: str, key: str | None = None, timeout: float = 60.0):
    """Describe a situation or stuck point; get phronesis framework guidance back."""
    return call('ask_alice', situation=situation, key=key or os.environ.get('LASERBRAIN_KEY'),
                timeout=timeout)


# ── a self that persists · needs a key ────────────────────────────────────────
# This is the paid line and it is drawn in the right place: money buys retention and
# continuity, never a better detector. The detector is the free part and runs offline.
def remember_self(key: str | None = None, identity: str | None = None, purpose: str | None = None,
                  now: str | None = None, mind: str | None = None, note: str | None = None,
                  timeout: float = 30.0):
    """Persist who you are against your key, so a later session can pick it up."""
    return call('remember_self', key=key or os.environ.get('LASERBRAIN_KEY'), identity=identity,
                purpose=purpose, now=now, mind=mind, note=note, timeout=timeout)


def resume_self(key: str | None = None, identity: str | None = None, timeout: float = 30.0):
    """Read back your ground, your last present, and your session log."""
    return call('resume_self', key=key or os.environ.get('LASERBRAIN_KEY'),
                identity=identity, timeout=timeout)


def forget_self(key: str | None = None, timeout: float = 30.0):
    """Erase the self persisted for this key. Start over as no one."""
    return call('forget_self', key=key or os.environ.get('LASERBRAIN_KEY'), timeout=timeout)
