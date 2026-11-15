"""Offline default: entry-point tests must never reach the real AWS CLI."""
import os
import pytest


@pytest.fixture(autouse=True)
def offline_aws(tmp_path, monkeypatch):
    folder = tmp_path / 'offline-aws'
    folder.mkdir()
    aws = folder / 'aws'
    aws.write_text('#!/bin/sh\nexit 1\n')
    aws.chmod(0o755)
    monkeypatch.setenv('PATH', str(folder) + os.pathsep + os.environ['PATH'])


@pytest.fixture(autouse=True)
def offline_routing_adapter(tmp_path, monkeypatch):
    """Existing CLI tests must not execute a user's installed routing adapter."""
    monkeypatch.setenv('CODEX_REVIEW_ADAPTER', str(tmp_path / 'missing-routing-adapter.py'))
