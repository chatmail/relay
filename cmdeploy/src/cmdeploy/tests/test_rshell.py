from unittest.mock import patch

from cmdeploy.remote.rshell import dovecot_recalc_quota


def test_dovecot_recalc_quota_normal_output():
    """Normal doveadm output returns parsed dict."""
    normal_output = (
        "Quota name Type    Value  Limit  %\n"
        "User quota STORAGE     5 102400  0\n"
        "User quota MESSAGE     2      -  0\n"
    )

    with patch("cmdeploy.remote.rshell.shell", return_value=normal_output):
        result = dovecot_recalc_quota("user@example.org")

    # shell is called twice (recalc + get), patch returns same for both
    assert result == {"value": 5, "limit": 102400, "percent": 0}


def test_dovecot_recalc_quota_empty_output():
    """Empty doveadm output (trailing newline) must not IndexError."""

    def mock_shell(cmd):
        if "recalc" in cmd:
            return ""
        # quota get returns only empty lines
        return "\n\n"

    with patch("cmdeploy.remote.rshell.shell", side_effect=mock_shell):
        result = dovecot_recalc_quota("user@example.org")

    assert result is None


def test_dovecot_recalc_quota_malformed_output():
    """Malformed output with too few columns must not crash."""

    def mock_shell(cmd):
        if "recalc" in cmd:
            return ""
        # partial line, fewer than 6 parts
        return "Quota name\nUser quota STORAGE\n"

    with patch("cmdeploy.remote.rshell.shell", side_effect=mock_shell):
        result = dovecot_recalc_quota("user@example.org")

    assert result is None


def test_dovecot_recalc_quota_header_only():
    """Only header line, no data rows."""

    def mock_shell(cmd):
        if "recalc" in cmd:
            return ""
        return "Quota name Type    Value  Limit  %\n"

    with patch("cmdeploy.remote.rshell.shell", side_effect=mock_shell):
        result = dovecot_recalc_quota("user@example.org")

    assert result is None
