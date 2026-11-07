from __future__ import annotations

import json
import os
import time
from pathlib import Path

APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sarman" / "TRANSLATE"
TEST_STATE = APP_DATA / "quota-test.json"


def set_quota_test(seconds: int) -> float:
    if seconds <= 0:
        raise ValueError("Test süresi pozitif olmalı.")
    TEST_STATE.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + int(seconds)
    temporary = TEST_STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": 1, "deadline": deadline}), encoding="utf-8")
    os.replace(temporary, TEST_STATE)
    return deadline


def quota_test_remaining() -> int:
    try:
        data = json.loads(TEST_STATE.read_text(encoding="utf-8"))
        deadline = float(data["deadline"])
        if data.get("version") != 1:
            return 0
        remaining = max(0, int(deadline - time.time()))
        if remaining == 0:
            clear_quota_test()
        return remaining
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return 0


def clear_quota_test() -> None:
    try:
        TEST_STATE.unlink(missing_ok=True)
    except OSError:
        pass
