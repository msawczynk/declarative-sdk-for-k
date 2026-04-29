import declarative_sdk_k
import keeper_sdk


def test_declarative_sdk_k_imports() -> None:
    assert declarative_sdk_k is not None


def test_declarative_sdk_k_version_matches_keeper_sdk() -> None:
    assert declarative_sdk_k.__version__ == keeper_sdk.__version__


def test_keeper_sdk_import_still_works() -> None:
    assert keeper_sdk is not None
