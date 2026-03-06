"""Tests for file discovery and batching."""

import subprocess
from pathlib import Path

from triplecheck.file_grouper import batch_files, discover_files, load_files
from triplecheck.state import FileContent


def _init_git(path: Path) -> None:
    """Init a git repo and add all files so git ls-files works."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True)


class TestBatchFiles:
    def _make_files(self, sizes: list[int]) -> list[FileContent]:
        return [
            FileContent(path=f"file{i}.py", content="\n" * n)
            for i, n in enumerate(sizes)
        ]

    def test_single_batch(self):
        files = self._make_files([10, 20, 30])
        batches = batch_files(files, max_lines=100)
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_split_by_lines(self):
        files = self._make_files([50, 50, 50])
        batches = batch_files(files, max_lines=80)
        assert len(batches) == 3  # each file gets its own batch

    def test_split_by_file_count(self):
        files = self._make_files([1, 1, 1, 1, 1, 1])
        batches = batch_files(files, max_lines=10000, max_files=2)
        assert len(batches) == 3

    def test_empty_input(self):
        assert batch_files([], max_lines=100) == []


class TestDiscoverFiles:
    def test_finds_python_files(self, tmp_path):
        (tmp_path / "app.py").write_text("x = 1")
        (tmp_path / "test.py").write_text("y = 2")
        (tmp_path / "data.bin").write_bytes(b"\x00\x01")
        _init_git(tmp_path)
        files = discover_files(tmp_path)
        names = {f.name for f in files}
        assert "app.py" in names
        assert "data.bin" not in names  # not a text extension

    def test_include_filter(self, tmp_path):
        (tmp_path / "app.py").write_text("x")
        (tmp_path / "utils.py").write_text("y")
        (tmp_path / "main.go").write_text("package main")
        _init_git(tmp_path)
        files = discover_files(tmp_path, include=["*.py"])
        assert all(f.suffix == ".py" for f in files)

    def test_exclude_filter(self, tmp_path):
        (tmp_path / "app.py").write_text("x")
        (tmp_path / "test_app.py").write_text("y")
        _init_git(tmp_path)
        files = discover_files(tmp_path, exclude=["test_*"])
        names = {f.name for f in files}
        assert "app.py" in names
        assert "test_app.py" not in names


class TestLoadFiles:
    def test_loads_content(self, tmp_path):
        (tmp_path / "hello.py").write_text("print('hi')")
        paths = [tmp_path / "hello.py"]
        loaded = load_files(paths, tmp_path)
        assert len(loaded) == 1
        assert loaded[0].content == "print('hi')"
        assert loaded[0].language == "python"

    def test_skips_large_files(self, tmp_path):
        (tmp_path / "big.py").write_text("x" * 200)
        paths = [tmp_path / "big.py"]
        loaded = load_files(paths, tmp_path, max_size=100)
        assert len(loaded) == 0

    def test_skips_unreadable(self, tmp_path):
        missing = tmp_path / "nope.py"
        loaded = load_files([missing], tmp_path)
        assert len(loaded) == 0
