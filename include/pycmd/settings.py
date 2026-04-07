from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Iterable
    from typing import Any

user = {}
values = {}


def _parse_value(s: str):
    """Parse a pycmd configuration option."""
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if s.endswith("f"):
        return float(s[:-1])
    if s.endswith("hz"):
        return 1 / float(s[:-2])
    if s.startswith("0x"):
        return int(s, 16)
    if ((s.startswith("'") and s.endswith("'"))
            or (s.startswith("\"") and s.endswith("\""))):
        return s[1:-1]
    try:
        return int(s)
    except ValueError:
        return s


def update_user(user_settings: "str | Iterable[str] | None") -> None:
    """Add the given configuration options to the user settings."""
    if not user_settings:
        return

    if isinstance(user_settings, str):
        options = (option.strip() for option in user_settings.split(","))
    else:
        options = (option.strip() for updates in user_settings
                   for option in updates.split(","))

    for option in options:
        key, eq, val = option.partition("=")
        if eq:
            val = _parse_value(val)
        else:
            key, val = (key[1:], False) if key.startswith("~") else (key, True)
        key = key.strip()

        user[key] = val


def clear() -> None:
    """Clear current settings."""
    values.clear()


def get(key, default=None):
    """Get a value from the current settings."""
    return values.get(key, default)


def set(key, value) -> None:
    """Set a value in the current settings."""
    values[key] = value


def update(settings: "Mapping | Iterable[tuple[Any, Any]] | None") -> None:
    """Update the current settings."""
    if settings:
        values.update(settings)
