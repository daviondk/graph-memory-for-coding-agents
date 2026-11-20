class BlockContextError(Exception):
    """Base error for block-context failures."""


class WorkspacePathError(BlockContextError):
    """Raised when a requested workspace path escapes the workspace root."""


class SourceChangedError(BlockContextError):
    """Raised when an expected source version no longer matches the source."""


class BlockNotFoundError(BlockContextError):
    """Raised when a document references an unknown block id."""
