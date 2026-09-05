import pytest

from tools.files import FileSandbox, SandboxError


def test_read_write_list(tmp_path):
    box = FileSandbox(tmp_path / "workspace")
    assert box.write("hello.txt", "hello") == "Saved to hello.txt"
    assert box.read("hello.txt") == "hello"
    assert "hello.txt" in box.list_dir()


def test_missing_file(tmp_path):
    box = FileSandbox(tmp_path / "workspace")
    with pytest.raises(SandboxError): box.read("missing.txt")


@pytest.mark.parametrize("path", ["../outside.txt", "../../etc/passwd", "/etc/passwd"])
def test_traversal_rejected(tmp_path, path):
    box = FileSandbox(tmp_path / "workspace")
    with pytest.raises(SandboxError): box.read(path)


def test_symlink_escape_rejected(tmp_path):
    root = tmp_path / "workspace"; box = FileSandbox(root)
    outside = tmp_path / "outside"; outside.mkdir(); (outside / "secret.txt").write_text("secret")
    link = root / "escape"
    try: link.symlink_to(outside, target_is_directory=True)
    except OSError: pytest.skip("symlinks unavailable")
    with pytest.raises(SandboxError): box.read("escape/secret.txt")


def test_oversized_file_rejected(tmp_path):
    box = FileSandbox(tmp_path / "workspace", max_read_bytes=4)
    box.write("large.txt", "12345")
    with pytest.raises(SandboxError, match="read limit"): box.read("large.txt")
