"""Workflow: the ordered process, and the shelf it is vended from.

The test that justifies the file is #2 — four steps, every one of them green, that
together walked away from what the workflow was for. If that case does not come back
green-and-wandered, the whole module is a task runner with extra words.
"""
import json
import sys
import tempfile

sys.path.insert(0, '.')

from laserbrain import Workflow, Store, Operator, Refused   # noqa: E402

ok = True


def check(label, cond):
    global ok
    print(f'  {"ok  " if cond else "FAIL"}  {label}')
    ok = ok and bool(cond)


def advancing(_ctx):
    return {'progress': 'advancing', 'distance': 1}


print('workflow')

# ── 1 · a healthy workflow completes ───────────────────────────────────────────────────
w = Workflow(goal='ship the release')
w.step('test', advancing, goal='the test suite passes')
w.step('build', advancing, goal='build the release wheel')
out = w.run()
check('a healthy workflow completes', out['completed'] is True and out['ran'] == ['test', 'build'])
check('  and no step is flagged as wandered', out['wandered'] == [])

# ── 2 · THE READING: a step that did other than what it was declared for ───────────────
def elsewhere(_ctx):
    return {'progress': 'advancing', 'distance': 1, 'goal': 'refactoring the parser'}


w = Workflow(goal='ship the release')
w.step('test', advancing, goal='the test suite passes')
w.step('build', elsewhere, goal='build the release wheel')
w.step('docs', advancing, goal='rewrite the changelog')
out = w.run(halt_on_drift=False)          # see them all, not just the first

departed = {r['step'] for r in out['wandered']}
check('the step that went elsewhere is caught', departed == {'build'})
row = out['wandered'][0]
check('  and says what it was declared for', row['declared'] == 'build the release wheel')
check('  and what it actually reported', row['reported'] == 'refactoring the parser')
check('  with the containment in the score', '⊂' in (row['laserscore'] or ''))

# ── 3 · steps that did what they were declared for are NOT flagged ─────────────────────
# Two bugs this covers. One: a shared harness grounded on step one, so 'build the wheel'
# read goal-drift purely for being second. Two: comparing a step's wording to the
# workflow's flagged 'the test suite passes' against 'ship the release' — zero overlap,
# and entirely legitimate.
kept = [s for s in w.steps if s.name in ('test', 'docs')]
check('an honest step is not drift for being second', all(not w._departed(s.verdict) for s in kept))
check('  nor for being worded unlike the goal',
      all(s.verdict.reason in ('grounded', 'advancing') for s in kept))

# ── 4 · it halts on a drifting step instead of running on ──────────────────────────────
def circles(_ctx):
    return {'progress': 'circling', 'distance': 9, 'goal': 'something else entirely'}


w = Workflow(goal='ship the release')
w.step('one', advancing, goal='the test suite passes')
w.step('two', circles, goal='the test suite passes')
w.step('three', advancing, goal='build the release wheel')
out = w.run()
check('halts at the drifting step', out['halted_at'] == 'two')
check('  and never runs what came after', 'three' not in out['ran'])

# ── 5 · an irreversible step with no operator is refused, not run ──────────────────────
fired = []
w = Workflow(goal='ship the release')
w.step('publish', lambda c: fired.append('SENT'), goal='upload to PyPI',
       irreversible=True, outward=True)
out = w.run()                                    # no operator supplied
check('an irreversible step with no operator is refused', out['refused_at'] == 'publish')
check('  and it never ran', fired == [])

# ── 6 · with an approving operator it runs ─────────────────────────────────────────────
fired = []
op = Operator(authorize=lambda a: True)
w = Workflow(goal='ship the release')
w.step('publish', lambda c: fired.append('SENT') or {'progress': 'advancing', 'distance': 0},
       goal='upload the release to PyPI', irreversible=True, outward=True)
out = w.run(operator=op)
check('an approved irreversible step runs', fired == ['SENT'] and out['completed'] is True)

# ── 7 · a refusing operator stops it ───────────────────────────────────────────────────
fired = []
op = Operator(authorize=lambda a: False)
w = Workflow(goal='ship the release')
w.step('publish', lambda c: fired.append('SENT'), goal='upload to PyPI', irreversible=True)
out = w.run(operator=op)
check('a refused irreversible step does not run', fired == [] and out['refused_at'] == 'publish')

# ── 8 · the spec carries no code ───────────────────────────────────────────────────────
w = Workflow(goal='ship the release')
w.step('test', advancing, goal='the test suite passes')
w.step('publish', advancing, goal='upload to PyPI', irreversible=True, outward=True)
spec = w.spec()
blob = json.dumps(spec)
check('a spec round-trips through JSON', json.loads(blob) == spec)
check('  and carries no callables', 'function' not in blob and 'lambda' not in blob)
check('  but keeps which steps act', spec['steps'][1]['irreversible'] is True)

# ── 9 · a vended workflow arrives unbound, and unbound steps RAISE ─────────────────────
v = Workflow.from_spec(spec)
check('every vended step is unbound', v.unbound() == ['test', 'publish'])
raised = []
try:
    v.run()
except NotImplementedError as e:
    raised.append(str(e))
check('an unbound step raises rather than passing silently', len(raised) == 1)
check('  and says how to bind it', 'bind' in raised[0])

# ── 10 · binding makes it runnable ─────────────────────────────────────────────────────
v = Workflow.from_spec(spec)
v.bind('test', advancing).bind('publish', advancing)
check('binding clears the unbound list', v.unbound() == [])
out = v.run(operator=Operator(authorize=lambda a: True))
check('a bound vended workflow runs', out['completed'] is True)

# ── 11 · a spec from the future is refused, not guessed at ─────────────────────────────
future = dict(spec)
future['spec_version'] = 99
try:
    Workflow.from_spec(future)
    check('an unknown spec_version is refused', False)
except ValueError:
    check('an unknown spec_version is refused', True)

# ── 12 · the store keeps and vends ─────────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as d:
    store = Store(root=d)
    store.put(w, 'release')
    check('the store lists what it holds', store.list() == ['release'])
    got = store.get('release')
    check('a vended workflow matches the spec', got.spec() == w.spec())
    check('  and arrives unbound', got.unbound() == ['test', 'publish'])
    cat = store.catalogue()[0]
    check('the catalogue names the irreversible steps', cat['irreversible'] == ['publish'])
    check('  without running anything', cat['goal'] == 'ship the release' and cat['steps'] == 2)
    try:
        store.get('nope')
        check('a missing workflow raises', False)
    except KeyError:
        check('a missing workflow raises', True)

# ── 13 · the shapes that should not be allowed ─────────────────────────────────────────
try:
    Workflow(goal='')
    check('an ungrounded workflow is refused', False)
except ValueError:
    check('an ungrounded workflow is refused', True)

w2 = Workflow(goal='x y z')
w2.step('a', advancing)
try:
    w2.step('a', advancing)
    check('duplicate step names are refused', False)
except ValueError:
    check('duplicate step names are refused', True)

# ── 14 · the dictionary linter ─────────────────────────────────────────────────────────
# The case that matters is under-declaration: a step whose verb is normally irreversible
# but which is not marked so. At run time the Operator waves it through without asking
# anyone, which is the failure mode with no second chance. This is the exact bug lint()
# found in phronesis's own deploy method on its first run against something real.
w = Workflow(goal='ship the site')
w.step('deploy', goal='put the build in front of users')      # NOT declared irreversible
found = w.lint()
under = [f for f in found if f['finding'] == 'under-declared']
# TWO findings, one per axis: deploy is both irreversible and outward, and each is
# separately wrong. Collapsing them into one would hide which half the author missed.
check('lint catches an undeclared irreversible verb', len(under) == 2)
check('  and names the verb', all(f['verb'] == 'deploy' for f in under))
check('  reporting each axis separately',
      any('irreversible' in f['note'] for f in under)
      and any('leaves this machine' in f['note'] for f in under))

# Declared correctly, it goes quiet.
w = Workflow(goal='ship the site')
w.step('deploy', goal='put the build in front of users', irreversible=True, outward=True)
check('a correctly declared step is not flagged',
      not [f for f in w.lint() if f['finding'] == 'under-declared'])

# Over-declaration is reported but is not a fault — it only asks more often.
w = Workflow(goal='ship the site')
w.step('test', goal='the suite passes', irreversible=True)
over = [f for f in w.lint() if f['finding'] == 'over-declared']
check('over-declaration is reported, not silent', len(over) == 1)

# A verb outside the vocabulary: not an error, but it makes methods incomparable.
w = Workflow(goal='ship the site')
w.step('frobnicate', goal='do the unnameable thing')
check('an off-vocabulary verb is reported',
      [f['finding'] for f in w.lint()] == ['unknown-verb'])

# A goal that restates the name cannot be scored against anything.
w = Workflow(goal='ship the site')
w.step('build', goal='build')
check('a goal restating its name is flagged',
      any(f['finding'] == 'goal-restates-name' for f in w.lint()))

# Verb-first naming: the verb carries the risk, so it must be extractable.
w = Workflow(goal='ship the release')
w.step('upload-pypi', goal='send the wheel to PyPI', irreversible=True, outward=True)
check('a verb-first compound name resolves its verb',
      not [f for f in w.lint() if f['finding'] == 'unknown-verb'])
w = Workflow(goal='ship the release')
w.step('pypi-upload', goal='send the wheel to PyPI', irreversible=True, outward=True)
check('  and a verb-last one does not — which is why naming is verb-first',
      [f['finding'] for f in w.lint()] == ['unknown-verb'])

# The linter advises; it never blocks. A method with findings still stores and runs.
w = Workflow(goal='ship the site')
w.step('frobnicate', lambda c: {'progress': 'advancing', 'distance': 1},
       goal='do the unnameable thing')
check('a method with findings still runs — lint advises, never overrides',
      w.run()['completed'] is True and len(w.lint()) == 1)

# ── 15 · the phase rules ───────────────────────────────────────────────────────────────
# Each of these is a real failure from 2026-07-28/29, rebuilt as a method. If the rules do
# not fire here they are decoration.
def phases_of(w):
    return [p for _, p in w.phases() if p]


w = Workflow(goal='ship the site')
w.step('build', goal='build the site')
w.step('commit', goal='save the source')
w.step('deploy', goal='put it in front of users', irreversible=True, outward=True)
kinds = {f['finding'] for f in w.lint()}
check('a method that records without verifying is caught',
      'verify-before-record' in kinds)
check('  and one that acts without confirming', 'confirm-after-act' in kinds)

w = Workflow(goal='publish the wheel')
w.step('build-wheel', goal='produce the distributable')
w.step('upload-pypi', goal='send the wheel out', irreversible=True, outward=True)
w.step('verify-published', goal='check it landed')
kinds = {f['finding'] for f in w.lint()}
check('a method that acts before recording is caught', 'record-before-act' in kinds)

w = Workflow(goal='sync the grammar')
w.step('edit-canonical', goal='change the one source')
w.step('sync', goal='propagate to every copy')
kinds = {f['finding'] for f in w.lint()}
check('a method that changes and never records is caught', 'change-is-recorded' in kinds)

# The backbone, and a well-shaped method passing all four.
w = Workflow(goal='ship a verified thing')
w.step('test', goal='the preconditions hold')
w.step('build', goal='produce the artifact')
w.step('verify-artifact', goal='the artifact is what it should be')
w.step('commit', goal='record the source of this')
w.step('publish', goal='make it available', irreversible=True, outward=True)
w.step('verify-published', goal='confirm it landed')
check('the canonical shape lints clean', w.lint() == [])
check('  and reads as the backbone',
      phases_of(w) == ['check', 'change', 'verify', 'record', 'act', 'verify'])

# stale-verify: the shape is right and the content is still wrong. This method has a
# verify, has a record, and the verify precedes the record — it passes all four earlier
# rules — but it changes something AFTER verifying, so what that change produced is
# committed unchecked. It is phronesis's own grammar-bump, and it is how two grammar
# copies were recorded sitting at 1.7.0 while canonical was 1.9.0.
w = Workflow(goal='keep every copy honest')
w.step('edit-canonical', goal='change the one source')
w.step('gate', goal='the hash describes the content')
w.step('sync', goal='propagate to every copy')
w.step('commit-copies', goal='record the propagated files')
kinds = {f['finding'] for f in w.lint()}
check('a change after the last verify is caught', 'stale-verify' in kinds)
check('  while the earlier four rules pass it',
      not {'verify-before-record', 'record-before-act',
           'confirm-after-act', 'change-is-recorded'} & kinds)

# Adding the verify back after the change clears it.
w = Workflow(goal='keep every copy honest')
w.step('edit-canonical', goal='change the one source')
w.step('gate', goal='the hash describes the content')
w.step('sync', goal='propagate to every copy')
w.step('verify-copies', goal='every copy matches the canonical file')
w.step('commit-copies', goal='record the propagated files')
check('  and verifying after the change clears it',
      'stale-verify' not in {f['finding'] for f in w.lint()})

# A trailing change with nothing recorded after it is fine — nothing ships unchecked.
w = Workflow(goal='publish and reconcile')
w.step('build', goal='make the artifact')
w.step('verify-artifact', goal='the artifact is right')
w.step('commit', goal='record the source')
w.step('publish', goal='send it out', irreversible=True, outward=True)
w.step('verify-published', goal='confirm it landed')
w.step('generate-vectors', goal='update what is derived from it')
check('a trailing reconcile is not flagged',
      'stale-verify' not in {f['finding'] for f in w.lint()})

# A read-only method needs no record, and must not be nagged for it.
w = Workflow(goal='find out what is there')
w.step('read', goal='load the current state')
w.step('measure', goal='take the reading')
check('a read-only method is not asked to record', w.lint() == [])

print()
raise SystemExit(0 if ok else 1)
