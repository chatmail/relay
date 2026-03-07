from cmdeploy.util import collapse, get_git_hash, get_version_string, shell


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
