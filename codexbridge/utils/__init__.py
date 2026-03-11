from .text import chunk_text

__all__ = ["chunk_text", "configure_logging", "SingleInstanceError", "SingleInstanceLock"]


def configure_logging(*args, **kwargs):
    from .logger import configure_logging as _configure_logging

    return _configure_logging(*args, **kwargs)


def __getattr__(name: str):
    if name in {"SingleInstanceError", "SingleInstanceLock"}:
        from .single_instance import SingleInstanceError, SingleInstanceLock

        return {
            "SingleInstanceError": SingleInstanceError,
            "SingleInstanceLock": SingleInstanceLock,
        }[name]
    raise AttributeError(name)
