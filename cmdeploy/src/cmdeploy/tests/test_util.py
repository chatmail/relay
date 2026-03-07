import pytest

from cmdeploy.util import (
    build_chatmaild_sdist,
    collapse,
    get_chatmaild_sdist,
    get_git_hash,
    get_version_string,
    shell,
)


def test_collapse():
    text = """
        line 1
        line 2
    """
    assert collapse(text) == "line 1 line 2"
    assert collapse("  single line  ") == "single line"


def test_git_helpers_no_git(tmp_path):
    # Not a git repo
    assert get_git_hash(root=tmp_path) is None
    assert get_version_string(root=tmp_path) == "unknown"


def test_git_helpers_empty_repo(tmp_path):
    shell("git init", cwd=tmp_path, check=True)
    # No commits yet
    assert get_git_hash(root=tmp_path) is None
    assert get_version_string(root=tmp_path) == "unknown"


def test_git_helpers_with_commits_and_diffs(tmp_path):
    shell("git init", cwd=tmp_path, check=True)
    shell("git config user.email you@example.com", cwd=tmp_path, check=True)
    shell("git config user.name 'Your Name'", cwd=tmp_path, check=True)

    # First commit
    path = tmp_path / "file.txt"
    path.write_text("content")
    shell("git add file.txt", cwd=tmp_path, check=True)
    shell("git commit -m initial", cwd=tmp_path, check=True)

    git_hash = get_git_hash(root=tmp_path)
    assert len(git_hash) >= 7  # usually 40, but git is git
    assert get_version_string(root=tmp_path) == git_hash

    # Create a diff
    path.write_text("new content")
    v = get_version_string(root=tmp_path)
    assert v.startswith(git_hash + "\n")
    assert "new content" in v
    assert not v.endswith("\n")

    # Commit again -> no diff
    shell("git add file.txt", cwd=tmp_path, check=True)
    shell("git commit -m second", cwd=tmp_path, check=True)
    new_hash = get_git_hash(root=tmp_path)
    assert new_hash != git_hash
    assert get_version_string(root=tmp_path) == new_hash


def test_build_chatmaild_sdist(tmp_path):
    dist_dir = tmp_path / "dist"

    # First call builds the sdist
    result = build_chatmaild_sdist(dist_dir)
    assert result.name.endswith(".tar.gz")
    assert result.stat().st_size > 0

    # Second call is idempotent — returns the same file, no rebuild
    mtime = result.stat().st_mtime
    result2 = build_chatmaild_sdist(dist_dir)
    assert result2 == result
    assert result2.stat().st_mtime == mtime


def test_get_chatmaild_sdist_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        get_chatmaild_sdist(tmp_path / "nonexistent")

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        get_chatmaild_sdist(empty)
