"""2.8: people insights on the demo data."""
from pno.api import Api, load_demo
from pno.db import Database
from pno import people_insights as pi


def test_pearson():
    assert round(pi._pearson([1, 2, 3, 4, 5, 6], [2, 4, 6, 8, 10, 12]), 3) == 1.0
    assert pi._pearson([1, 2, 3], [1, 2, 3]) is None
