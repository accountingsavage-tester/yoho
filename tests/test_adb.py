from unittest.mock import patch

import pytest

from tools.system import ADBError, adb, check_adb


def test_adb_success():
    with patch("tools.system.shutil.which", return_value="adb"), patch("tools.system.subprocess.run") as run:
        run.return_value.returncode = 0; run.return_value.stdout = "device\n"; run.return_value.stderr = ""
        assert adb(None, "get-state") == "device"
        assert run.call_args.args[0] == ["adb", "get-state"]
        assert run.call_args.kwargs["timeout"] == 10


def test_adb_missing():
    with patch("tools.system.shutil.which", return_value=None):
        with pytest.raises(ADBError, match="not found"): adb(None, "get-state")


def test_adb_timeout():
    import subprocess
    with patch("tools.system.shutil.which", return_value="adb"), patch("tools.system.subprocess.run", side_effect=subprocess.TimeoutExpired("adb", 1)):
        with pytest.raises(ADBError, match="timed out"): adb(None, "get-state")


def test_adb_nonzero():
    with patch("tools.system.shutil.which", return_value="adb"), patch("tools.system.subprocess.run") as run:
        run.return_value.returncode = 1; run.return_value.stdout = ""; run.return_value.stderr = "device not found"
        with pytest.raises(ADBError, match="unavailable") as exc: adb(None, "get-state")


def test_check_adb_missing():
    with patch("tools.system.shutil.which", return_value=None):
        ok, message = check_adb(None)
    assert not ok and "not found" in message
