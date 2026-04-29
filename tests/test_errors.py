from keeper_sdk.core import CapabilityError, DeleteUnsupportedError
from keeper_sdk.core.errors import (
    DeleteUnsupportedError as DirectDeleteUnsupportedError,
)


def test_delete_unsupported_error_remains_public_capability_error() -> None:
    assert DirectDeleteUnsupportedError is DeleteUnsupportedError
    assert issubclass(DeleteUnsupportedError, CapabilityError)

    exc = DeleteUnsupportedError(reason="delete is not supported by this provider")

    assert isinstance(exc, CapabilityError)
    assert "delete is not supported" in str(exc)
