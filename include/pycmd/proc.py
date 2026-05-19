import functools
import io
import logging
import os
import shlex
import signal
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from typing import cast, TYPE_CHECKING

import pycmd

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Callable, Generator, Literal, Sequence

# kwargs for run to hide cmd but show output
THRU = {
    "display": False
}

# kwargs for run to hide cmd and output
HIDDEN = {
    "display": False,
    "output_stdout": False,
    "output_stderr": False
}

# kwargs for run to disable all output
SILENT = {
    "display": False,
    "output_stdout": None,
    "output_stderr": None
}


def quote(v: object) -> str:
    """Quote the value to display as a CLI argument."""
    return shlex.quote(str(v))


def join(args: "Iterable[object]") -> str:
    """Quote values and join by whitespace."""
    return shlex.join(map(str, args))


def shell_join(args: "Iterable[object]") -> str:
    """Similar to join but only values with whitespace are quoted."""
    return " ".join(shlex.quote(v) if " " in v else v for v in map(str, args))


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


def display_args(args: "Sequence[object]", cwd: str | os.PathLike) -> str:
    """
    Get a string which displays the command being executed.
    The first argument will be made relative if it is an existing file
    under the cwd.
    :param args: Command args.
    :param cwd: Command working directory.
    :return: Command display string.
    """
    rel = relative(str(args[0]), cwd)
    abs_cmd = Path(cwd, rel)
    content = join([rel, args[1:]] if abs_cmd.is_file() else args)
    return display_cmd(content, cwd)


def display_cmd(content: str, cwd: str | os.PathLike) -> str:
    """
    Get a string which displays the command being executed.
    The directory will be displayed if the working directory
    is different from the cwd.
    :param content: Command content.
    :param cwd: Command working directory.
    :return: Command display string.
    """
    return f"$ {content}" if Path.cwd().samefile(cwd) \
        else f"[{Path(cwd).absolute().resolve()}]$ {content}"


def process_args(
        args: "Sequence[object] | str | os.PathLike",
        shell: bool,
        cwd: str | os.PathLike | None,
) -> "tuple[Sequence[str] | str, str | os.PathLike]":
    """
    Convert the input to suitable Popen arguments and get a display string
    for the command.
    :param args: Command arguments.
    :param shell: Whether shell=True for the command.
    :param cwd: Command working directory.
    :return:
    """
    cmd_cwd = Path(cwd or ".")

    if shell:
        exec_args = (os.fspath(args)
                     if isinstance(args, (str, os.PathLike))
                     else shell_join(args))
        return exec_args, display_cmd(exec_args, cmd_cwd)

    if isinstance(args, str):
        exec_args = shlex.split(args)
    elif isinstance(args, os.PathLike):
        exec_args = [str(args)]
    else:
        exec_args = list(map(str, args))

    args_str = display_args(exec_args, cmd_cwd)
    return exec_args, args_str


@contextmanager
def _forward_interrupts(get_proc: "Callable[[], subprocess.Popen | None]") \
        -> "Generator[None, None, None]":
    """
    Context manager which sends interrupts to a subprocess.
    :param get_proc: Function to get the active subprocess.
    """

    def _handler(signum, _frame):
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


def run(
        args: "Sequence[object] | str | os.PathLike",
        capture_stdout: bool = True,
        capture_stderr: bool = True,
        check: "bool | Literal['check']" = False,
        display: bool = True,
        output_stdout: bool = True,
        output_stderr: bool = True,
        **kwargs
) -> subprocess.CompletedProcess:
    """
    Wrapper for subprocess.Popen, similar to subprocess.run. Sends subprocess
    output to stdout and stderr in real time, capturing the output if desired.
    :param args: Popen command.
    :param capture_stdout: If True, stdout will be captured.
    :param capture_stderr: If True, stderr will be captured.
    :param check: Whether to check the return code of the process.
    :param display: Whether the command is printed or logged internally.
    :param output_stdout: If True, stdout is forwarded to sys.stdout. If False,
        stdout is only logged internally. If None, no output is recorded.
    :param output_stderr: If True, stdout is forwarded to sys.stdout. If False,
        stdout is only logged internally. If None, no output is recorded.
    :param kwargs: Arguments forwarded to subprocess.Popen.
    :return:
    """
    exec_args, args_str = process_args(
        args,
        cast(bool, kwargs.get("shell")),
        cast(str | os.PathLike | None, kwargs.get("cwd"))
    )

    if display:
        print(args_str)
    else:
        pycmd.log.write(args_str)

    proc = None
    with _forward_interrupts(lambda: proc):
        proc = subprocess.Popen(exec_args,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                bufsize=0,
                                text=True,
                                **kwargs)
        hidden = pycmd.log.HIDDEN
        stdout_dest = sys.stdout if output_stdout else (
            pycmd.log.stream(hidden) if output_stdout is False else None)
        stderr_dest = sys.stderr if output_stderr else (
            pycmd.log.stream(logging.ERROR) if output_stderr is False else None)

        try:
            stdout_reader = StreamReader(proc.stdout,
                                         stdout_dest,
                                         capture_stdout)
            stderr_reader = StreamReader(proc.stderr,
                                         stderr_dest,
                                         capture_stderr)
            stdout = stdout_reader.get()
            stderr = stderr_reader.get()
            proc.wait()
        finally:
            if output_stdout is False:
                cast(pycmd.log.StreamLogger, stdout_dest).close()
            if output_stderr is False:
                cast(pycmd.log.StreamLogger, stderr_dest).close()

    result = subprocess.CompletedProcess(exec_args, proc.returncode, stdout, stderr)

    if check == "check":
        result.check_returncode()
    elif check and result.returncode:
        pycmd.error(f"Process exited with code {result.returncode}")

    return result


@functools.wraps(run)
def run_thru(*args, **kwargs):
    return run(*args, **THRU, **kwargs)


@functools.wraps(run)
def run_hidden(*args, **kwargs):
    return run(*args, **HIDDEN, **kwargs)


@functools.wraps(run)
def run_silent(*args, **kwargs):
    return run(*args, **SILENT, **kwargs)


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
        for s in iter(lambda: self.stream.read(1), ""):
            if self._result is not None:
                self._result += s
            if self.target is not None:
                print(s, file=self.target, end="")

    def get(self) -> str | None:
        """Block until the stream is complete and return the captured output."""
        self._thread.join()
        return self._result
