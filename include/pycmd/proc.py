import io
import os
import pycmd
import signal
import subprocess
import sys

from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Callable, Generator


def quote(v) -> str:
    """Quote the value if it contains whitespace."""
    s = str(v)
    return f"\"{s}\"" if " " in s else s


def quote_all(args: "Iterable") -> str:
    """Quote values and join by whitespace."""
    return " ".join(map(quote, args))


def relative(path: str | os.PathLike, base: str | os.PathLike) \
        -> Path | str | os.PathLike:
    """
    Get a path that is relative to a given base path.
    If the path is not relative, the original path is returned.
    :param path: Requested path.
    :param base: Base path.
    :return: Relative path, if applicable, or original path.
    """
    absolute = (Path.cwd() / base).resolve()

    try:
        return (absolute / path).relative_to(absolute)
    except ValueError:
        return path


def display_args(args: str | list[str], cwd: str | os.PathLike | None) -> str:
    """
    Get a string which displays the command being executed.
    The directory will be displayed if the working directory
    is different from the cwd.
    :param args: Command args.
    :param cwd: Command working directory.
    :return: Command display string.
    """
    cmd_cwd = Path(cwd or ".")
    if isinstance(args, str):
        content = args
    else:
        args[0] = str(relative(args[0], cmd_cwd))
        content = quote_all(args)
    return f"$ {content}" if cmd_cwd.samefile(Path.cwd()) \
        else f"[{cmd_cwd.absolute().resolve()}]$ {content}"


@contextmanager
def _forward_interrupts(get_proc: "Callable[[], subprocess.Popen | None]") \
        -> "Generator[None, None, None]":
    """
    Context manager which sends interrupts to a subprocess.
    :param get_proc: Function to get the active subprocess.
    """

    def _handler(signum, frame):
        p = get_proc()
        if p:
            pycmd.log.write(f"Forwarding signal {signum} to subprocess")
            p.send_signal(signum)
        else:
            raise KeyboardInterrupt

    old = signal.signal(signal.SIGINT, _handler)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, old)


def run(args,
        capture_stdout=True,
        capture_stderr=True,
        check=True,
        display=True,
        **kwargs) -> subprocess.CompletedProcess:
    """
    Wrapper for subprocess.Popen, similar to subprocess.run. Sends subprocess
    output to stdout and stderr in real time, capturing the output if desired.
    :param args: Popen command.
    :param capture_stdout: If True, stdout will be captured.
    :param capture_stderr: If True, stderr will be captured.
    :param check: Whether to check the return code of the process.
    :param display: Whether the command is printed or logged internally.
    :param kwargs: Arguments forwarded to subprocess.Popen.
    :return:
    """
    args_str = display_args(args, kwargs.get("cwd"))
    if display:
        print(args_str)
    else:
        pycmd.log.write(args_str)

    proc = None
    with _forward_interrupts(lambda: proc):
        proc = subprocess.Popen(args,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                bufsize=0,
                                text=True,
                                **kwargs)
        stdout_reader = StreamReader(proc.stdout, sys.stdout, capture_stdout)
        stderr_reader = StreamReader(proc.stderr, sys.stderr, capture_stderr)
        stdout = stdout_reader.get()
        stderr = stderr_reader.get()
        proc.wait()

    result = subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)
    if check:
        result.check_returncode()
    return result


class StreamReader:
    """Forwards one stream to another, optionally capturing the output."""

    def __init__(self, stream, target, capture=True):
        """
        :param stream: Input stream.
        :param target: Forward stream.
        :param capture: Whether to capture output.
        """
        self.stream = stream
        self.target = target
        self._result = "" if capture else None

        self._thread = Thread(target=self._read)
        self._thread.start()

    def _read(self) -> None:
        """Thread which forwards and captures stream output."""
        for s in iter(lambda: self.stream.read(io.DEFAULT_BUFFER_SIZE), ""):
            if self._result is not None:
                self._result += s
            print(s, file=self.target, end="")

    def get(self) -> str | None:
        """Block until the stream is complete and return the captured output."""
        self._thread.join()
        return self._result
