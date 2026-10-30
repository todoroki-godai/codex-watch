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

from pathlib import Path
VALID_REVIEW_PROMPT = (Path(__file__).resolve().parents[1] / "templates/review-request.md").read_text()
