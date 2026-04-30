"""Preview Crossplane provider surface for DSK.

The implementation is intentionally capability-gated. Importing
``CrossplaneProvider`` is safe offline, but every reconciliation method raises
``CapabilityError`` until the Crossplane function/controller runtime exists.
"""

from keeper_sdk.crossplane.provider import CrossplaneProvider

__all__ = ["CrossplaneProvider"]
