"""Historical retained WGC-frame transport candidate adapter."""

from .capture_mailbox import Mailbox


class RetainedCaptureMailbox:
    """Factory for a single latest-frame slot with no fixed pixel allocation."""

    @classmethod
    def create(cls, context, *, sbs=False, metadata_only=False):
        if sbs or metadata_only:
            raise ValueError("Retained capture is input-only")
        return Mailbox.create(context, metadata_only=True)


def install():
    """Remain compatible with evidence commands after product promotion.

    The canonical worker now uses the same retained-frame transport directly,
    so the old benchmark switch intentionally has nothing left to patch.
    """
