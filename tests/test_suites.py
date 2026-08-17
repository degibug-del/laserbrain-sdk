"""Run every script-style suite as a subprocess and assert it exits clean.

This is the pytest-visible surface. The suites themselves are standalone scripts (see
../conftest.py for why) and are run here the same way a human runs them, so there is no
second code path that could pass while the real one fails.
"""
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SUITES = sorted(p.name for p in ROOT.glob('test_*.py'))


@pytest.mark.parametrize('suite', SUITES)
def test_suite_passes(suite):
    r = subprocess.run([sys.executable, suite], cwd=ROOT, capture_output=True, text=True,
                       timeout=300)
    # The script's own output is the useful failure message — it names the assertion that
    # broke, which an exit code alone cannot.
    assert r.returncode == 0, f'{suite} exited {r.returncode}\n{r.stdout[-3000:]}{r.stderr[-2000:]}'


def test_every_suite_is_collected():
    """A suite that stops being found is a suite that stops running, silently."""
    assert len(SUITES) >= 39, f'only {len(SUITES)} suites found — did a file get renamed?'
