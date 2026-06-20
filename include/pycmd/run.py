import argparse
import os
import sys
from contextlib import closing
from datetime import datetime as DateTime
from functools import partial, wraps
from pathlib import Path
from typing import TYPE_CHECKING

import pycmd

if TYPE_CHECKING:
    from types import ModuleType
    from typing import Any, Callable, cast, Generator, Never, Sequence


class MainModuleInfo:
    """Holds information about the main pycmd module."""

    def __init__(self):
        self.module: "ModuleType" = sys.modules["__main__"]
        source = getattr(self.module, "__file__", None)
        self.source: Path | None = Path(source) if source else None


class Error(BaseException):
    """
    Represents an error in the program which causes it to exit immediately
    with an error status.
    """

    def __init__(self, msg: str):
        super().__init__(msg)


def error(msg: str) -> "Never":
    """Raise an error which prints and exits with an error status."""
    raise Error(msg)


def _one[T](gen: "Generator[T, None, None]",
            empty_err: str | None,
            extra_err: str) -> T | None:
    """
    Expect exactly one element from an iterator.
    :param gen: Iterator instance.
    :param empty_err: Error message if the iterator is empty, or None to
        return None for an empty iterator.
    :param extra_err: Error message if the iterator contains more than
        one element.
    :return:
    """
    with closing(gen) as g:
        try:
            first = next(g)
        except StopIteration:
            if empty_err is not None:
                raise ValueError(empty_err)
            return None

        try:
            next(g)
        except StopIteration:
            return first

        raise ValueError(extra_err)


def wrap[**P, R](func: "Callable[P, R]", cmd: "Sequence[str] | None" = None) \
        -> "Callable[P, R]":
    """
    Wrap a function so that it executes as a pycmd.
    """

    @wraps(func)
    def _wrapper(*args, **kwargs):
        pycmd.settings.update_user(os.getenv("PYCMD_OPTIONS"))
        run_main(partial(func, *args, **kwargs), cmd if cmd is not None else ())

    return _wrapper


def main(module: "ModuleType") -> None:
    """
    Run the function in the module which is marked with "main" metadata.
    This is considered the "standard" execution of a module. Settings are
    applied, logging is initialized, and some simple stats are logged.
    """
    main_func = _one(pycmd.meta.find_iter(module, "main"),
                     "Module missing 'main' function",
                     "At most one 'main' function is permitted in a module")

    run_main(cast("Callable[[], Any]", main_func), sys.argv)


def run_main(main_func: "Callable[[], Any]", cmd: "Sequence[str]") -> None:
    if not callable(main_func):
        raise TypeError(f"'{main_func}' is not callable")

    pycmd.settings.update(pycmd.meta.get(main_func, "settings"))
    pycmd.settings.update(pycmd.settings.user)

    log_file = None
    log_level = pycmd.settings.get("log_level", "NOTSET")

    if (pycmd.settings.get("log", True)
            and (log_dir := pycmd.log.init_log_dir())):
        timestamp = DateTime.now().strftime("%Y%m%d%H%M%S%f")
        if pycmd.info.source is None:
            log_file = log_dir / f"{timestamp}{pycmd.log.SUFFIX}"
        else:
            log_file = log_dir / (f"{timestamp}_{pycmd.info.source.name}"
                                  f"{pycmd.log.SUFFIX}")

    try:
        with (pycmd.log.init_hook(),
              pycmd.log.init_file(log_file, log_level),
              pycmd.log.exception_logger()):
            pycmd.log.write(f"PYCMD: {pycmd.proc.join(cmd)}")
            pycmd.log.write(f"CWD: {os.getcwd()}")
            pycmd.log.write("BEGIN")
            start_time = DateTime.now()
            try:
                main_func()
            except Error as e:
                print(e)
                raise
            finally:
                end_time = DateTime.now()
                pycmd.log.write("END")
                pycmd.log.write(f"TIME: {end_time - start_time}")
    finally:
        try:
            pycmd.log.prune(int(os.getenv("PYCMD_PRUNE", 10)))
        except ValueError:
            pass


def exec(module: "ModuleType") -> None:
    """
    Run the function in the module which is marked with "exec" metadata.
    If no function is defined, then pycmd.run.main(module) is used
    as a fallback.
    """
    exec_func = _one(pycmd.meta.find_iter(module, "exec"),
                     None,
                     "At most one 'exec' function is permitted in a module")
    if exec_func is None:
        exec_func = partial(main, module)

    old_module = pycmd.info.module
    pycmd.info.module = module
    try:
        exec_func()
    except Error:
        exit(1)
    finally:
        pycmd.info.module = old_module


def module_main() -> None:
    """
    Run the pycmd module.
    Reads pycmd options and then executes the main script.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--pycmd", action="append", metavar="OPTIONS")
    parser.add_argument("script")
    pycmd_args, args = parser.parse_known_args()

    pycmd.info.source = Path(pycmd_args.script)
    if not pycmd.info.source.is_file():
        parser.error(f"File doesn't exist: {pycmd.info.source}")

    # Set args so the main module can read argv as if it were executed directly
    sys.argv = [str(pycmd.info.source.resolve()), *args]
    pycmd.args = args
    pycmd.settings.update_user(os.getenv("PYCMD_OPTIONS"))
    pycmd.settings.update_user(pycmd_args.pycmd)

    import pycmd.main as module  # ty:ignore[unresolved-import]
    pycmd.run.exec(module)
