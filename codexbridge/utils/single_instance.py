from __future__ import annotations

from pathlib import Path


class SingleInstanceError(RuntimeError):
    pass


class SingleInstanceLock:
    def __init__(self, lock_path: Path) -> None:
        self.lock_path = Path(lock_path)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = None

    def acquire(self) -> None:
        self._handle = self.lock_path.open("a+b")
        try:
            self._lock_handle()
            self._handle.seek(0)
            self._handle.truncate()
            self._handle.write(str(self._get_pid()).encode("ascii"))
            self._handle.flush()
        except Exception:
            self.release()
            raise

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            self._unlock_handle()
        finally:
            self._handle.close()
            self._handle = None

    def _lock_handle(self) -> None:
        assert self._handle is not None
        try:
            import msvcrt

            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except ImportError:
            pass
        except OSError as exc:
            raise SingleInstanceError(
                f"Another CodexBridge instance is already running (lock: {self.lock_path})"
            ) from exc

        try:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SingleInstanceError(
                f"Another CodexBridge instance is already running (lock: {self.lock_path})"
            ) from exc

    def _unlock_handle(self) -> None:
        assert self._handle is not None
        try:
            import msvcrt

            self._handle.seek(0)
            try:
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            return
        except ImportError:
            pass

        try:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass

    @staticmethod
    def _get_pid() -> int:
        import os

        return os.getpid()
