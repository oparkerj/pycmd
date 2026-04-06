from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Callable, Generator

ATTR = "_pycmd_meta_"


def values(obj) -> dict | None:
    """Get metadata from the given object."""
    return getattr(obj, ATTR, None)


def get(obj, name, default=None):
    """Get metadata value from object."""
    meta = values(obj)
    return meta.get(name, default) if meta is not None else default


def set(obj, name, value, new=False):
    """
    Set metadata value on object.
    :param obj: Any object.
    :param name: Metadata name.
    :param value: Metadata value.
    :param new: If True, the value will only be set if name does not exist.
    :return: Whether the value was set.
    """
    meta = values(obj)
    if meta is None:
        meta = {}
        setattr(obj, ATTR, meta)
    if new and name in meta:
        return False
    meta[name] = value
    return True


def find_iter(obj, name) -> "Generator[Any, None, None]":
    """Get an iterator over attributes which contain the given name."""
    for attr_name in dir(obj):
        attr = getattr(obj, attr_name)
        meta = values(attr)
        if meta is not None and name in meta:
            yield attr


def exec[T](func: T) -> T:
    """Decorator which sets 'exec' metadata on the function."""
    set(func, "exec", None)
    return func


def main[T](func: T) -> T:
    """Decorate which sets 'main' metadata on the function."""
    set(func, "main", None)
    return func


def use_settings[T](**kwargs) -> "Callable[[T], T]":
    """
    Decorator which sets 'settings' metadata on the function.
    The specified key-value pairs will be applied as options when
    executing a module.
    """

    def _apply[U](func: U) -> U:
        set(func, "settings", kwargs)
        return func

    return _apply
