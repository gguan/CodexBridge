from .text import chunk_text

__all__ = ["chunk_text", "configure_logging"]


def configure_logging(*args, **kwargs):
    from .logger import configure_logging as _configure_logging

    return _configure_logging(*args, **kwargs)
