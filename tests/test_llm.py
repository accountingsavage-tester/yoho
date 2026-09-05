from unittest.mock import patch

from core.llm import run_llama


def test_llm_success():
    class Result:
        returncode = 0; stdout = "hello\n[ Prompt: 1 ]"; stderr = ""
    with patch("core.llm.shutil.which", return_value="llama-cli"), patch("core.llm.subprocess.run", return_value=Result()) as run:
        output, code, err = run_llama("model", "prompt", timeout=3)
    assert output == "hello" and code == 0
    assert run.call_args.kwargs["timeout"] == 3


def test_llm_timeout():
    import subprocess
    with patch("core.llm.shutil.which", return_value="llama-cli"), patch("core.llm.subprocess.run", side_effect=subprocess.TimeoutExpired("llama-cli", 1)):
        output, code, err = run_llama("model", "prompt", timeout=1)
    assert code == 124 and "timed out" in err


def test_llm_missing_executable():
    with patch("core.llm.shutil.which", return_value=None):
        output, code, err = run_llama("model", "prompt")
    assert code == 127 and "not found" in err


def test_llm_nonzero():
    class Result:
        returncode = 2; stdout = ""; stderr = "bad model"
    with patch("core.llm.shutil.which", return_value="llama-cli"), patch("core.llm.subprocess.run", return_value=Result()):
        output, code, err = run_llama("model", "prompt")
    assert code == 2 and err == "bad model"
