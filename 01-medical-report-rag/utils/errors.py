"""Errors whose message is safe and friendly to show directly to the user."""


class UserFacingError(Exception):
    """Base class: str(error) is shown in the UI. Technical details go to the terminal log."""


class OllamaNotRunningError(UserFacingError):
    pass


class ModelMissingError(UserFacingError):
    pass


class PDFError(UserFacingError):
    pass


class NoTextError(PDFError):
    pass


class EmbeddingError(UserFacingError):
    pass


class VectorStoreError(UserFacingError):
    pass


class LLMError(UserFacingError):
    pass
