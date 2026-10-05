"""Shared fixtures. Every test runs against throwaway databases filled with the fictional demo data."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["PNO_HOME"] = tempfile.mkdtemp(prefix="pno-tests-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
for k in ("NO_PROXY", "no_proxy"):
    os.environ[k] = ",".join(filter(None, [os.environ.get(k, ""), "127.0.0.1", "localhost"]))

from pno import demo as demo_mod  # noqa: E402
from pno.api import Api, load_demo  # noqa: E402
from pno.db import Database  # noqa: E402


@pytest.fixture(scope="session")
def demo():
    return demo_mod.build()


@pytest.fixture(scope="session")
def demo_db_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("demo") / "demo.sqlite3"
    db = Database(path)
    load_demo(db)
    db.close()
    return path


@pytest.fixture
def db(demo_db_file, tmp_path):
    """A private copy of the demo database, so a test can change anything."""
    p = tmp_path / "pno.sqlite3"
    shutil.copy(demo_db_file, p)
    d = Database(p)
    yield d
    d.close()


@pytest.fixture
def api(db):
    return Api(db)


@pytest.fixture
def empty_db(tmp_path):
    d = Database(tmp_path / "empty.sqlite3")
    yield d
    d.close()
