#!/usr/bin/env python3
"""Ротация MASTER_KEY. Логика и порядок действий — в `app/core/key_rotation.py`.

    cd apps/api && python scripts/rotate_master_key.py --dry-run
    cd apps/api && python scripts/rotate_master_key.py

Старый ключ берётся из `MASTER_KEY_PREVIOUS`, а не из аргумента: аргументы командной
строки видны в списке процессов и попадают в историю shell.
"""

from __future__ import annotations

from app.core.key_rotation import main

if __name__ == "__main__":
    raise SystemExit(main())
