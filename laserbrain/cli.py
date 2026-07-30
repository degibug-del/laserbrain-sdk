"""
laserbrain command line — the smart recursion harness, in your terminal.

    laserbrain demo                      watch an agent wander off-goal and get returned
    laserbrain check --goal "…" [--progress advancing] [--distance 6] [--against "…"]
    laserbrain verify run.json           verify an exported audit chain (tamper-evident)
    laserbrain store [list|find|vend] [--kind workflow|team]   prefabricated methods
    laserbrain key                       get a free key for the hosted half
    laserbrain mcp                       run as an MCP server — offline, no key
    laserbrain version

Dep-free (stdlib only), like the rest of the package.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from typing import Sequence

from . import Harness, Verdict, verify_audit, ground_score, __version__

DIM, BOLD, GOLD, RED, GREEN, RESET = '\033[2m', '\033[1m', '\033[33m', '\033[31m', '\033[32m', '\033[0m'


def _c(s: str, code: str) -> str:
    """Colour only when stdout is a TTY — pipes and logs stay clean."""
    return f"{code}{s}{RESET}" if sys.stdout.isatty() else s


def _demo() -> int:
    hz = Harness()
    print()
    print("  " + _c("laserbrain", BOLD) + " — the agent wanders off its goal; the harness catches it and returns it.")
    print()
    print(f"    {'the agent is working on…':38} {'dist':>4} {'Φ':>6}  verdict")
    print("    " + _c("─" * 70, DIM))
    script = [
        ("build the JSON parser", 6),
        ("build the JSON parser", 4),
        ("also add a caching layer and logging", 4),   # ← drifts to a different goal
        ("build the JSON parser", 2),                   # ← returned to ground
        ("build the JSON parser", 0),
    ]
    for goal, dist in script:
        v = hz.check(goal, "advancing", dist)
        if dist == 0:
            tag = _c("✓ done", GREEN)
        elif v.drifting:
            tag = _c("⚑ DRIFT → return", RED)
        elif v.reason == "grounded":
            tag = _c("· grounded", DIM)
        else:
            tag = _c("· on track", DIM)
        print(f"    {goal[:38]:38} {dist:>4} {v.phi:>6.2f}  {v.reason:12} {tag}")
        if v.drifting:
            print(f"    {'':38} {'':>4} {'':>6}  {_c('↩ ' + v.advice, GOLD)}")
    print()
    print("  It left its goal for a single step. Watching only itself, it wouldn't have noticed —")
    print("  laserbrain saw it against the fixed reference and returned it, so it " + _c("finished", GREEN) + ".")
    print()
    print("  " + _c("from laserbrain import Harness", GOLD) + "   →   Harness().check(goal=…, progress=…, distance=…)")
    print()
    return 0


def _check(args: argparse.Namespace) -> int:
    hz = Harness()
    if args.against:
        hz.check(args.against, "advancing", 5)          # set ground to a prior goal, to reveal drift
    v = hz.check(args.goal, args.progress, args.distance)
    print(_verdict_line(v))
    return 1 if v.drifting else 0                        # scriptable: nonzero exit on drift


def _verdict_line(v: Verdict) -> str:
    if v.drifting:
        head = _c("⚑ drifting", RED)
    elif v.reason == "grounded":
        head = _c("✓ grounded", GREEN)
    else:
        head = _c("· on track", DIM)
    return f"[{head}] {v.reason}  Φ={v.phi:.2f}  ground={ground_score(v.phi):.2f}\n  {_c(v.advice, DIM)}"


def _key(args: argparse.Namespace) -> int:
    """Get a key, and say plainly what it does and does not buy.

    WHY THIS COMMAND EXISTS. The README has always told readers "add a key and it also
    mirrors to the API", and until 0.24.0 the package offered no way to get one. The
    endpoint has been public and instant the whole time — POST /v1/keys, no auth, no
    form — so the only thing between a reader and the hosted half was knowing that.
    On 2026-07-29 the numbers on that gap were 6,000 downloads and twelve keys ever
    issued, two of them from testing.

    It prints what the API says the tier allows rather than what the docs claim, because
    those are different sentences that can drift apart, and only one of them is enforced.
    """
    from .services import KEY_PATH, ServiceUnavailable, new_key, save_key, stored_key

    existing = stored_key()
    if existing and not args.new:
        src = 'LASERBRAIN_KEY' if os.environ.get('LASERBRAIN_KEY') else str(KEY_PATH)
        print()
        print("  " + _c("you already have a key", GREEN) + f"   {existing[:11]}…")
        print(f"  {_c('from', DIM)} {src}")
        print()
        print(f"  {_c('laserbrain key --new', GOLD)} gets another one. It will not migrate")
        print("  anything to the new key — a key is the identity, so a second key is a")
        print("  second identity with its own history.")
        print()
        return 0

    try:
        got = new_key()
    except ServiceUnavailable as e:
        print()
        print("  " + _c("could not get a key", RED) + f" — {e}")
        print()
        print("  Nothing is broken locally. The check is a pure function and needs no key:")
        print("  " + _c("Harness().check(...)", GOLD) + " keeps working offline.")
        print()
        return 2

    key = got.get('key')
    if not key:
        print("\n  " + _c("the API answered without a key", RED) + f" — {got}\n")
        return 2

    path = save_key(key)
    tier = got.get('tier') or {}
    print()
    print("  " + _c("key saved", GREEN) + f"   {key}")
    print(f"  {_c('→', DIM)} {path}  {_c('(0600, readable only by you)', DIM)}")
    print()
    print(f"  {_c('this key is on the ' + str(tier.get('name', 'ground')) + ' tier', BOLD)}, and it allows:")
    for label, field, unit in (('reads', 'reads', '/day'), ('writes', 'writes', '/day'),
                               ('field history', 'historyHours', 'h'),
                               ('drift retained', 'driftDays', ' days')):
        v = tier.get(field)
        if v is not None:
            print(f"    {label:16} {v}{unit}")
    print()
    print("  " + _c("what it adds:", BOLD) + " retained drift history, the field, and a self that")
    print("  survives a session. " + _c("What stays free without it:", BOLD) + " the check itself —")
    print("  Harness.check is a pure local function and never calls anything.")
    print()
    print("  " + _c("You pay to SEE your agents drift, not for the detector.", DIM))
    print()
    return 0


def _verify(args: argparse.Namespace) -> int:
    try:
        with open(args.file) as f:
            chain = json.load(f)
    except Exception as e:
        print(_c(f"could not read {args.file}: {e}", RED))
        return 2
    ok, i = verify_audit(chain)
    if ok:
        print(_c(f"✓ audit intact", GREEN) + f" — {len(chain)} records, hash chain verified end to end")
        return 0
    print(_c(f"✗ audit BROKEN at link {i}", RED) + " — a record was altered, or the file is corrupt")
    return 1


def _store(args: argparse.Namespace) -> int:
    """List, find, or vend a prefabricated workflow or team preset from the store —
    the third surface (Python import and MCP already had it) that could not reach 8
    shipped workflows and 3 recursion-team presets before this command existed."""
    from . import Store
    s = Store()
    action = args.action
    kind_team = args.kind == 'team'

    if action == 'list':
        names = s.list_teams() if kind_team else s.list()
        print()
        print(f"  {_c(('team presets' if kind_team else 'workflows'), BOLD)} — {len(names)}")
        for n in names:
            print(f"    {n}")
        print()
        return 0

    if action == 'find':
        if not args.query:
            print(_c('a task, in words: laserbrain store find "fix a broken build"', RED))
            return 2
        hits = (s.find_team(args.query, top=args.top) if kind_team
                else s.find(args.query, top=args.top))
        print()
        if not hits:
            print(f"  {_c('nothing matched', DIM)} {args.query!r}")
            print()
            return 1
        for h in hits:
            desc = h.get('task') if kind_team else h.get('goal')
            score = _c(f"score {h['score']}", DIM)
            print(f"  {_c(h['name'], GOLD)}  {score}")
            print(f"    {desc}")
        print()
        return 0

    if action == 'vend':
        if not args.query:
            print(_c('a name: laserbrain store vend build-and-ship', RED))
            return 2
        try:
            spec = s.vend_team(args.query) if kind_team else s.vend(args.query)
        except KeyError as e:
            print(_c(str(e), RED))
            return 2
        print()
        print(json.dumps(spec, indent=2))
        print()
        return 0

    print(_c(f"unknown action {action!r} — list, find or vend", RED))
    return 2


def _coverage(args: argparse.Namespace) -> int:
    """How much of your work the harness actually watched.

    Nobody in this industry can currently answer "is my agent monitoring attached?".
    On 2026-07-24 the honest answer for a full working day was 2% — ten independently
    caught errors, one check. Test coverage became non-negotiable once it was a number
    on a screen; this is the same move, and it is deliberately unflattering.
    """
    import glob, os
    paths = sorted(glob.glob(os.path.expanduser(args.dir + '/*.json')))
    if not paths:
        print(f"  no sessions in {args.dir} — is the hook installed?")
        return 2
    rows, tot_steps, tot_checks, tot_inf, tot_catch = [], 0, 0, 0, 0
    for f in paths:
        try:
            d = json.load(open(f))
        except Exception:
            continue
        steps = d.get('steps', 0) or 0
        checks, inf = len(d.get('checks', [])), len(d.get('inferred', []))
        catches = len(d.get('catches', []))
        tot_steps += steps; tot_checks += checks; tot_inf += inf; tot_catch += catches
        rows.append((os.path.basename(f)[:20], steps, checks, inf, catches,
                     (checks / steps) if steps else 0.0))
    print()
    print(f"    {'session':22}{'steps':>7}{'spelled':>9}{'inferred':>10}{'catches':>9}{'coverage':>10}")
    print("    " + _c("─" * 67, DIM))
    for name, steps, checks, inf, catches, cov in rows:
        bar = GREEN if cov >= 0.5 else (GOLD if cov >= 0.2 else RED)
        print(f"    {name:22}{steps:>7}{checks:>9}{inf:>10}{catches:>9}" + _c(f"{cov:>9.0%}", bar))
    cov = (tot_checks / tot_steps) if tot_steps else 0.0
    print("    " + _c("─" * 67, DIM))
    print(f"    {'all':22}{tot_steps:>7}{tot_checks:>9}{tot_inf:>10}{tot_catch:>9}"
          + _c(f"{cov:>9.0%}", GREEN if cov >= 0.5 else RED))
    print()
    if cov < 0.5:
        print("  " + _c("Below 50%.", BOLD) + " A detection result cannot be computed from this —")
        print("  silence from a harness that was not running says nothing about the harness.")
        print("  Inferred checks are counted separately and do NOT open that gate: they carry")
        print("  no distance, so their \u03a6 is a lower bound and they cannot detect a stall.")
        return 1
    print("  " + _c("Scorable.", BOLD) + " Recall and precision can be computed from these sessions.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="laserbrain", description="the smart recursion harness — in your terminal")
    p.add_argument("-V", "--version", action="version", version=f"laserbrain {__version__}")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("demo", help="watch an agent drift off-goal and get returned")
    c = sub.add_parser("check", help="check one spelled state")
    c.add_argument("--goal", required=True, help="the agent's current goal")
    c.add_argument("--progress", default="advancing", choices=["advancing", "stuck", "circling"])
    c.add_argument("--distance", type=int, default=5, help="0–10, distance to done")
    c.add_argument("--against", metavar="GOAL", help="a prior goal to set as ground, to reveal drift")
    v = sub.add_parser("verify", help="verify an exported audit chain")
    v.add_argument("file", help="a JSON file written by Harness.export_audit()")
    cv = sub.add_parser("coverage", help="how much of your work the harness actually watched")
    cv.add_argument("--dir", default="~/.claude/laserbrain",
                    help="where the hook writes sessions (default: ~/.claude/laserbrain)")
    st = sub.add_parser("store", help="prefabricated workflows and team presets — list, find, or vend")
    st.add_argument("action", nargs="?", default="list", choices=["list", "find", "vend"])
    st.add_argument("query", nargs="?", default=None,
                    help="a task in words (find) or a name (vend)")
    st.add_argument("--kind", default="workflow", choices=["workflow", "team"])
    st.add_argument("--top", type=int, default=3, help="find: how many matches (default 3)")
    k = sub.add_parser("key", help="get a free API key, and see what it allows")
    k.add_argument("--new", action="store_true",
                   help="fetch another key even if one is already stored")
    sub.add_parser("mcp", help="run as an MCP server on stdin/stdout (offline, no key)")
    sub.add_parser("version", help="print the version")

    args = p.parse_args(argv)
    if args.cmd == "demo":
        return _demo()
    if args.cmd == "check":
        return _check(args)
    if args.cmd == "coverage":
        args.dir = args.dir.replace("~", __import__("os").path.expanduser("~"))
        return _coverage(args)
    if args.cmd == "verify":
        return _verify(args)
    if args.cmd == "store":
        return _store(args)
    if args.cmd == "key":
        return _key(args)
    if args.cmd == "mcp":
        # Nothing may print to stdout but JSON-RPC — an MCP client parses it.
        from .mcp import serve
        return serve()
    if args.cmd == "version":
        print(f"laserbrain {__version__}")
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
