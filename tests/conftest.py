"""Keep launcher fixtures offline and independent of the startup filter."""
import os
import shutil
import pytest


@pytest.fixture(autouse=True)
def offline_launchers(tmp_path, monkeypatch):
    folder = tmp_path / 'offline-aws'
    folder.mkdir()
    node = shutil.which('node')
    if node:
        (folder / 'node').symlink_to(node)
    for program in ('aws', 'codex'):
        stub = folder / program
        stub.write_text('#!/bin/sh\nexit 1\n')
        stub.chmod(0o755)
    # Older fixtures exercise other launcher responsibilities with their own stubs.
    monkeypatch.setenv('CODEX_SKILLS_FILTER', 'off')
    monkeypatch.delenv('CODEX_SKILLS_ALLOW', raising=False)
    monkeypatch.delenv('CODEX_MEMORIES', raising=False)
    monkeypatch.setenv('NVM_DIR', str(tmp_path / 'empty-nvm'))
    monkeypatch.delenv('CODEX_WATCH_CODEX', raising=False)
    path = [p for p in os.environ['PATH'].split(os.pathsep) if '/.nvm/' not in p]
    monkeypatch.setenv('PATH', os.pathsep.join([str(folder), *path]))


@pytest.fixture(autouse=True)
def offline_routing_adapter(tmp_path, monkeypatch):
    """Existing CLI tests must not execute a user's installed routing adapter."""
    monkeypatch.setenv('CODEX_REVIEW_ADAPTER', str(tmp_path / 'missing-routing-adapter.py'))
