import importlib.abc
import importlib.machinery
import importlib.util
import os
import pycmd
import sys

from pathlib import Path

MAIN = "pycmd.main"
PREFIX = __name__ + "."


def get_path() -> list[str]:
    """Read the PYCMD_PATH environment variable."""
    path = os.getenv("PYCMD_PATH")
    return path.split(os.pathsep) if path is not None else []


def __getattr__(name):
    if name == "__path__":
        return pycmd.path

    raise AttributeError


class Finder(importlib.abc.MetaPathFinder):
    """ Finder which provides the 'main' module and pycmd submodules.
        pycmd submodules are imported as submodules of this file,
        and are located using pycmd.path.
    """

    @staticmethod
    def _spec(module_name, file) -> "importlib.machinery.ModuleSpec | None":
        loader = importlib.machinery.SourceFileLoader(module_name, file)
        return importlib.util.spec_from_loader(module_name, loader)

    def find_spec(self, fullname, path, target=None):
        # Provide main module
        if fullname == MAIN:
            if pycmd.info.source is None:
                return None
            return self._spec(fullname, str(pycmd.info.source))

        # Check for pycmd submodule
        if path is None or not fullname.startswith(PREFIX):
            return None

        name = fullname[len(PREFIX):]
        if "." in name:
            return None

        source = pycmd.info.source
        module_dir = source.parent if source is not None else None
        module_dir_searched = module_dir is None

        # Search the directories specified in the pycmd path
        for d in path:
            p = Path(d)
            if p.is_dir():
                if module_dir is not None and p.samefile(module_dir):
                    module_dir_searched = True
                expected = p / name
                if expected.is_file():
                    return self._spec(fullname, str(expected))

        # The directory of the main module is always checked
        if not module_dir_searched:
            expected = module_dir / name
            if expected.is_file():
                return self._spec(fullname, str(expected))

        return None


sys.meta_path.append(Finder())
