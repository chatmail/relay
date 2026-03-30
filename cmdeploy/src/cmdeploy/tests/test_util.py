import sys

from cmdeploy.util import Out, collapse, get_git_hash, get_version_string, shell


class TestOut:
    def test_prefix_default(self, capsys):
        out = Out()
        out.print("hello")
        assert capsys.readouterr().out == "hello\n"

    def test_prefix_custom(self, capsys):
        out = Out(prefix=">> ")
        out.print("hello")
        assert capsys.readouterr().out == ">> hello\n"

    def test_prefix_print_file(self):
        import io

        buf = io.StringIO()
        out = Out(prefix=":: ")
        out.print("msg", file=buf)
        assert ":: msg" in buf.getvalue()

    def test_new_prefixed_out(self, capsys):
        parent = Out(prefix="A")
        child = parent.new_prefixed_out("B")
        child.print("x")
        assert capsys.readouterr().out == "ABx\n"
        # shares section_timings
        assert child.section_timings is parent.section_timings

    def test_section_no_auto_indent(self, capsys):
        out = Out(prefix="")
        with out.section("test"):
            out.print("inside")
        captured = capsys.readouterr().out
        # "inside" should NOT be indented by section()
        lines = captured.strip().splitlines()
        inside_line = [l for l in lines if "inside" in l][0]
        assert inside_line == "inside"

    def test_section_records_timing(self):
        out = Out()
        with out.section("s1"):
            pass
        assert len(out.section_timings) == 1
        assert out.section_timings[0][0] == "s1"

    def test_shell_failure_shows_output(self):
        """When a shell command fails, its output and exit code are shown."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from cmdeploy.util import Out; Out(prefix='').shell("
                "\"echo 'boom on stderr' >&2; exit 42\")",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        # the command's stderr is merged into stdout by Popen
        assert "boom on stderr" in result.stdout
        # Out.red() prints the failure notice to stderr
        assert "exit code 42" in result.stderr


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
