"""CGI entry module."""

from __future__ import annotations

import os

from .cgiapp import handle


def main() -> None:
    handle(os.environ.get("OTPAUTHENTICATION_HANDLER", "pin"))


if __name__ == "__main__":
    main()