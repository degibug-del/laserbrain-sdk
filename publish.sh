#!/usr/bin/env bash
# publish.sh — build, upload, and then VERIFY A FRESH INSTALL.
#
# The token is prompted for here and never written to disk, never exported into the
# environment, and never passed on a command line where it would land in shell history
# or a process list. Diego runs this; Claude does not handle the credential.
#
# The verify step exists because of 0.3.0: the PyPI JSON API reported the version as
# published while the wheel that actually installed was missing the async layer. The
# index is not the artefact. A release is not done until a clean venv can install it and
# import what it claims to ship.
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(python3 -c "import re,pathlib;print(re.search(r'version\s*=\s*\"([^\"]+)\"',pathlib.Path('pyproject.toml').read_text()).group(1))")
echo "  about to publish laserbrain ${VERSION}"

# A suite that cannot go red is not a suite. mutate.sh flips the constants the product
# forbids changing silently and fails if the tests stay green — on 2026-07-25 its --deep
# mode found 5 of 6 mutations surviving, meaning the calibration was protected by one
# pinned-value file and no behavioural test at all. A release where that is true again
# should not ship.
echo "  mutation gate — proving the suite can go red"
./mutate.sh >/dev/null 2>&1 || { echo "    FAIL: a mutation survived. Run ./mutate.sh to see which."; exit 1; }
./mutate.sh --deep >/dev/null 2>&1 || { echo "    FAIL (deep): a mutation survives without test_frozen.py."; echo "    The constants are pinned but not watched by behaviour. Run ./mutate.sh --deep."; exit 1; }
echo "    ok — every mutation caught, with and without the pin"

echo "  running the suite first — a red suite is not a release"
for t in test_metric test_adapters test_async test_ecosystem test_nested test_frozen test_behaviour test_vocab test_observe test_cli; do
  printf "    %-16s " "$t"
  python3 "$t.py" >/dev/null 2>&1 && echo pass || { echo FAIL; exit 1; }
done

rm -rf dist build ./*.egg-info
python3 -m build >/dev/null
echo "  built: $(ls dist | tr '\n' ' ')"

read -rsp "  PyPI token (input hidden): " TOKEN; echo
[ -z "$TOKEN" ] && { echo "  no token, nothing uploaded"; exit 1; }

TWINE_USERNAME=__token__ TWINE_PASSWORD="$TOKEN" python3 -m twine upload dist/* 
unset TOKEN

# The index propagates on its own schedule. A fixed sleep guessed at it and guessed
# wrong on the 0.4.0 release — the upload had succeeded and the check reported failure.
# Poll until it appears, and only then decide anything.
TMP=$(mktemp -d)
python3 -m venv "$TMP/venv"
echo "  waiting for the index (polling, not guessing)"
for i in $(seq 1 12); do
  if "$TMP/venv/bin/pip" install --quiet --no-cache-dir "laserbrain==${VERSION}" 2>/dev/null; then
    echo "  appeared on attempt $i"; break
  fi
  [ "$i" = 12 ] && { echo "  ✗ never appeared after 12 tries — check PyPI by hand"; rm -rf "$TMP"; exit 1; }
  sleep 10
done
"$TMP/venv/bin/python" - <<PYEOF
import laserbrain
from laserbrain import Calibration, PUBLISHED, Harness
from laserbrain.observe import Observer
from laserbrain.vocab import embedding_similarity
assert laserbrain.__version__ == "${VERSION}", laserbrain.__version__
assert PUBLISHED.is_published and PUBLISHED.goal_min == 0.30
h = Harness(); h.check(goal='a b c', progress='advancing', distance=5)
assert h.check(goal='x y z', progress='advancing', distance=5).reason == 'goal-drift'
o = Observer('a b c'); assert o.state()['distance'] is None
print("  ✓ fresh install of ${VERSION} imports Calibration, observe and vocab, and detects drift")
PYEOF
rm -rf "$TMP"
echo "  published and verified against a clean environment, not against the index"
