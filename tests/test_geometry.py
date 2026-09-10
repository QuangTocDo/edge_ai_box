"""Test geometry dung chung (crossing_sign, allowed_vec).
Chay tu project root: python -m tests.test_geometry
"""
from src.geometry import allowed_vec, crossing_sign


def test_crossing_sign():
    line = ((0, 100), (200, 100))
    assert crossing_sign((100, 80), (100, 120), *line) == 1   # xuong
    assert crossing_sign((100, 120), (100, 80), *line) == -1  # len
    assert crossing_sign((10, 50), (50, 50), *line) == 0       # song song
    # allowed_vec phai nhat quan voi dau cat
    av = allowed_vec((0, 100), (200, 100), 1)
    assert av[1] > 0, av  # sign +1 <-> huong xuong
    print("crossing_sign OK")


if __name__ == "__main__":
    test_crossing_sign()
    print("ALL GEOMETRY TESTS PASSED")
