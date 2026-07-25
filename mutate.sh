#!/usr/bin/env bash
# mutate.sh — a suite that cannot go red is not a suite.
#
# Every gate this project wrote passed something broken until it was mutation-tested:
#
#   the Python suite   goal_min 0.30 -> 0.45 changed NOTHING; weights reshuffled, nothing
#   drift-parity (TS)  the threshold could move anywhere inside 0.30..0.45 undetected
#   the Swift parity   a dropped stopword and a moved stem boundary each changed NOTHING
#   check-contrast     exempted hues, so a 1.97:1 call-to-action shipped green
#
# In every case the tests were green and the instrument was unprotected. Green is a claim
# about the tests, not about the code, and the only way to earn it is to break the code on
# purpose and watch the tests notice.
#
# This does that mechanically. Each mutation below changes ONE thing the product forbids
# changing silently. If the suite still passes, the suite is not watching that thing, and
# this exits non-zero.
#
#   ./mutate.sh          run every mutation
#   ./mutate.sh --deep   run them WITHOUT test_frozen.py
#   ./mutate.sh --list   show them without running
#
# --deep is the interesting mode. test_frozen.py pins the constants by value, so it
# catches every constant mutation by construction — a green run only proves that file
# exists. Excluding it asks the sharper question: does any test notice the CHANGE IN
# BEHAVIOUR, or is the instrument protected by one assertion of its own numbers? Both
# guarantees are worth having and they are not the same thing.
set -uo pipefail
cd "$(dirname "$0")"

SRC=laserbrain/__init__.py
BAK=$(mktemp)
cp "$SRC" "$BAK"
restore() { cp "$BAK" "$SRC"; }
trap restore EXIT

# name | sed expression | why it must be caught
MUTATIONS=(
  "goal threshold 0.30 -> 0.45|s/goal_min=0.30/goal_min=0.45/|the drift boundary is the product; moving it must never be silent"
  "goal weight 0.5 -> 0.2|s/w_goal=0.5, w_distance=0.3, w_progress=0.2/w_goal=0.2, w_distance=0.3, w_progress=0.5/|Φ is reported against fixed thresholds; reweighting rescales every verdict"
  "self-report floor 0.15 -> 0.40|s/self_report_min=0.15/self_report_min=0.40/|a raised floor silently stops honouring the agent's own stuck report"
  "stall window 4 -> 9|s/stall_window=4/stall_window=9/|a wider window means a stall is reported far later, or never"
  "echo floor 0.25 -> 0.90|s/echo_min=0.25/echo_min=0.90/|teams stop detecting echo-spiral entirely"
  "detection disabled|s/if anchor < self.cal.goal_min:/if anchor < -1.0:/|the control: if THIS is not caught, nothing is wired up at all"
)

if [ "${1:-}" = "--list" ]; then
  printf '  %s\n' "${MUTATIONS[@]%%|*}"; exit 0
fi

SUITE=(test_metric test_adapters test_async test_ecosystem test_nested test_frozen
       test_vocab test_observe test_cli test_runtime test_behaviour)

DEEP=0
if [ "${1:-}" = "--deep" ]; then
  DEEP=1
  # drop test_frozen: what is left is behaviour, not a pinned value
  SUITE=(test_metric test_adapters test_async test_ecosystem test_nested
         test_vocab test_observe test_cli test_runtime test_behaviour)
fi

run_suite() {
  for t in "${SUITE[@]}"; do
    python3 "$t.py" >/dev/null 2>&1 || return 1
  done
  return 0
}

[ "$DEEP" = "1" ] && echo "  DEEP: running without test_frozen.py — behaviour only" && echo
echo "  baseline: the suite must be GREEN before anything is mutated"
if ! run_suite; then
  echo "  ✗ the suite is already failing — fix that before mutation testing means anything"
  exit 1
fi
echo "  ✓ green"
echo

survived=0
for m in "${MUTATIONS[@]}"; do
  name=${m%%|*}; rest=${m#*|}; expr=${rest%%|*}; why=${rest#*|}
  restore
  sed -i '' "$expr" "$SRC"
  if cmp -s "$SRC" "$BAK"; then
    echo "  ⚠ $name — the mutation did not apply; the code it targets has moved"
    survived=$((survived + 1)); continue
  fi
  if run_suite; then
    echo "  ✗ SURVIVED: $name"
    echo "      $why"
    survived=$((survived + 1))
  else
    echo "  ✓ caught: $name"
  fi
done
restore

echo
if [ "$survived" -gt 0 ]; then
  echo "  $([ "$DEEP" = 1 ] && echo "DEEP RESULT" || echo "FAIL") — $survived mutation(s) survived."
  if [ "$DEEP" = "1" ]; then
    echo "  These constants are pinned by test_frozen.py but NOT watched by any behavioural"
    echo "  test. That is a real gap: change one and only the pin notices, so the pin is the"
    echo "  entire protection. Worth a behavioural test each, or worth knowing."
    exit 1
  fi
  echo "  The suite is green on code it does not watch."
  echo "  Add a test that fails for each, or accept that the instrument is unprotected there."
  exit 1
fi
echo "  ok    every mutation was caught — the suite is watching what it claims to watch"
