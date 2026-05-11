from __future__ import annotations


def test_package_imports():
    import recipebrain

    assert recipebrain.__version__


def test_version_is_string():
    import recipebrain

    assert isinstance(recipebrain.__version__, str)
    assert recipebrain.__version__  # non-empty
