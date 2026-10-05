"""Terminal styling out of CLI output, so a test can look for an option name as written."""

import re

_STYLE = re.compile(r"\x1b\[[0-9;]*m")


def plain(output: str) -> str:
    """`output` without ANSI styling, which CI forces on (FORCE_COLOR) and which splits option names."""
    return _STYLE.sub("", output)
