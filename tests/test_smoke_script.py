"""The logs-folder smoke script parses a directory cleanly (uses samples)."""

from __future__ import annotations


def test_smoke_logs_parses_samples(samples_dir):
    import smoke_logs  # on sys.path via conftest

    rc = smoke_logs.main(["smoke_logs.py", samples_dir["dir"]])
    assert rc == 0
