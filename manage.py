#!/usr/bin/env python3
"""Django entrypoint for the news portal backend."""

from __future__ import annotations

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "newsportal.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Couldn't import Django. Install requirements first: pip install -r requirements.txt"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

