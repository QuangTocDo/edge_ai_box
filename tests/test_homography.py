"""Test homography pixel -> met.
Chay tu project root: python -m tests.test_homography
"""
from src.homography import (build_H, longitudinal_dist, pixel_to_road)


def test_uniform_scale():
    # 10px = 1m deu khap frame
    src = [[0, 0], [100, 0], [100, 100], [0, 100]]
    dst = [[0, 0], [10, 0], [10, 10], [0, 10]]
    H, inl, err = build_H(src, dst)
    assert inl == 4 and err < 1e-6, (inl, err)
    X, Y = pixel_to_road(H, 50, 50)
    assert abs(X - 5.0) < 1e-6 and abs(Y - 5.0) < 1e-6, (X, Y)
    print("uniform scale OK")


def test_degenerate_rejected():
    try:
        build_H([[0, 0], [1, 1], [2, 2], [3, 3]],
                [[0, 0], [1, 0], [2, 0], [3, 0]])
        raise AssertionError("diem thang hang phai loi")
    except ValueError:
        pass
    try:
        build_H([[0, 0]], [[0, 0]])
        raise AssertionError("thieu diem phai loi")
    except ValueError:
        pass
    print("degenerate rejected OK")


def test_longitudinal():
    assert abs(longitudinal_dist((0, 0), (3, 4), [1, 0]) - 3.0) < 1e-9
    assert abs(longitudinal_dist((0, 0), (3, 4), [0, 1]) - 4.0) < 1e-9
    # road_dir chua chuan hoa cung duoc
    assert abs(longitudinal_dist((0, 0), (6, 8), [3, 4]) - 10.0) < 1e-9
    try:
        longitudinal_dist((0, 0), (1, 1), [0, 0])
        raise AssertionError("dir suy bien phai loi")
    except ValueError:
        pass
    print("longitudinal OK")


if __name__ == "__main__":
    test_uniform_scale()
    test_degenerate_rejected()
    test_longitudinal()
    print("ALL HOMOGRAPHY TESTS PASSED")
