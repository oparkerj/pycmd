import io
import logging
import os
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

import pycmd

if TYPE_CHECKING:
    from typing import Generator

SUFFIX = ".log"
TEMP_SUFFIX = ".tmp"

# Custom log level for pycmd internal logs
HIDDEN = logging.INFO - 4
PYCMD = logging.INFO - 5
logging.addLevelName(HIDDEN, "HIDDEN")
logging.addLevelName(PYCMD, "PYCMD")

_logger = None  # Cached value for get_logger
_hook = None  # Cached value for init_hook
_init_log_dir, _log_dir = False, None  # Cached value for init_log_dir


def get_logger() -> "logging.Logger":
    """Initialize and get the pycmd logger."""
    global _logger
    if _logger:
        return _logger

    _logger = logging.getLogger("pycmd")
    _logger.setLevel(PYCMD)
    _logger.addHandler(logging.NullHandler())
    return _logger


def stream(level) -> StreamLogger:
    """Get a line-buffered stream which outputs logs at the given level."""
    return StreamLogger(None, get_logger(), level)


def write(msg, *args, **kwargs) -> None:
    """Log a message to the pycmd logger at PYCMD level."""
    logger = get_logger()
    if logger.isEnabledFor(PYCMD):
        logger.log(PYCMD, msg, *args, **kwargs)


@contextmanager
def init_hook() -> "Generator[None, None, None]":
    """
    Context manager which hooks into stdout and stderr.
    While active, output is captured and also sent to the
    original streams. Captured output is line-buffered and emitted
    to the pycmd logger.
    """
    global _hook
    if _hook is not None:
        yield
        return

    _hook = LogHook()
    try:
        yield
    finally:
        _hook.close()
        _hook = None


@contextmanager
def init_file(path: str | os.PathLike | None,
              level: int | str = logging.NOTSET) \
        -> "Generator[Path | None, None, None]":
    """
    Context manager which sets up a file handler for the pycmd logger.
    If the path is None, this manager does nothing.
    """
    if not path:
        yield
        return

    temp_path = Path(path).with_suffix(TEMP_SUFFIX)

    # Set up file handler
    logger = get_logger()
    handler = logging.FileHandler(temp_path)
    formatter = logging.Formatter("[%(asctime)s %(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(level)
    logger.addHandler(handler)

    try:
        yield temp_path
    finally:
        # Close file handler and remove temporary extension
        logger.removeHandler(handler)
        handler.close()
        temp_path.replace(path)


@contextmanager
def exception_logger():
    try:
        yield
    except Exception:
        get_logger().error(traceback.format_exc())
        raise


def init_log_dir() -> Path | None:
    """
    Get the directory which stores logs.
    The directory can be overridden via options or environment variable.
    The default location is a hidden folder in the user's home directory.
    """
    global _init_log_dir, _log_dir
    if _init_log_dir:
        return _log_dir

    log_dir = (pycmd.settings.get("log_dir", None) or
               os.getenv("PYCMD_LOGS", None))
    if log_dir is None:
        log_dir = Path.home() / ".pycmd"
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
    else:
        log_dir = None

    _log_dir = log_dir
    _init_log_dir = True
    return _log_dir


def prune(keep: int) -> None:
    """
    Deletes old logs from the log directory except for the
    specified number to keep.
    """
    if keep < 0:
        return

    log_dir = init_log_dir()
    if not log_dir:
        return

    logs = sorted(log_dir.glob(f"*{SUFFIX}"))
    remove = logs if keep == 0 else logs[:-keep]

    for p in remove:
        p.unlink(missing_ok=True)


class LogHook:
    """Replaces stdout and stderr with a StreamLogger."""

    def __init__(self):
        logger = get_logger()

        self._stdout = sys.stdout
        self._logout = StreamLogger(self._stdout, logger, logging.INFO)
        sys.stdout = self._logout
        self._stderr = sys.stderr
        self._logerr = StreamLogger(self._stderr, logger, logging.ERROR)
        sys.stderr = self._logerr

    def close(self) -> None:
        """Restore the previous stdout and stderr."""
        sys.stdout = self._stdout
        self._logout.close()
        sys.stderr = self._stderr
        self._logerr.close()


class StreamLogger(io.TextIOBase):
    """
    A stream which acts as a passthrough to another stream,
    while also capturing the content of the stream. Captured
    output is line-buffered and emitted to a logger.
    """

    def __init__(self, stream, logger, level):
        """
        :param stream: Passthrough stream
        :param logger: Logger instance
        :param level: Log level
        """
        self._lock = Lock()
        self._buffer = ""
        self._stream = stream
        self._logger = logger
        self._level = level

    def _log(self, s: str) -> None:
        """
        Capture the output. Content is line-buffered and logged.
        """
        if not s:
            return

        # Each line will be a separate log
        parts = s.splitlines()
        if s[-1] in os.linesep:
            # Content ends with newline, nothing to buffer
            rest = ""
        else:
            # Content does not have newline, last line will be buffered
            rest = parts[-1]
            parts = parts[:-1]

        if parts:
            # Add the buffer content to the first log
            with self._lock:
                if self._buffer is None:
                    return
                parts[0] = self._buffer + parts[0]
                self._buffer = rest

            for line in parts:
                self._logger.log(self._level, line)
        else:
            # Nothing to log, only append to the buffer
            with self._lock:
                if self._buffer is None:
                    return
                self._buffer += rest

    def close(self) -> None:
        """Close the stream, which will log any text remaining in the buffer."""
        with self._lock:
            if self._buffer is None:
                return
            buf, self._buffer = self._buffer, None

        if buf:
            self._logger.log(self._level, buf)

    def write(self, s: str) -> int:
        self._log(s)
        if self._stream is None:
            return len(s)
        return self._stream.write(s)

    def flush(self) -> None:
        if self._stream is not None:
            self._stream.flush()
