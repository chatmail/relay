import os
import time

from chatmaild.quota_expire import expire_to_target, scan_mailbox_messages

MB = 1024 * 1024


def _create_message(basedir, relpath, size, days_old=0):
    path = basedir / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    mtime = time.time() - days_old * 86400
    os.utime(path, (mtime, mtime))
    return path


def test_scan_cur_new_tmp(tmp_path):
    _create_message(tmp_path, "cur/msg1", 100)
    _create_message(tmp_path, "new/msg2", 200)
    _create_message(tmp_path, "tmp/msg3", 300)
    messages = scan_mailbox_messages(str(tmp_path))
    assert len(messages) == 3
    sizes = sorted(m.size for m in messages)
    assert sizes == [100, 200, 300]


def test_scan_ignores_subfolders(tmp_path):
    _create_message(tmp_path, "cur/a", 10)
    _create_message(tmp_path, ".DeltaChat/cur/b", 20)
    assert len(scan_mailbox_messages(str(tmp_path))) == 1


def test_scan_empty(tmp_path):
    assert scan_mailbox_messages(str(tmp_path)) == []
    assert scan_mailbox_messages(str(tmp_path / "nope")) == []


def test_noop_under_limit(tmp_path):
    _create_message(tmp_path, "cur/msg1", MB)
    assert expire_to_target(str(tmp_path), 2 * MB) == []
    assert (tmp_path / "cur" / "msg1").exists()


def test_removes_to_target(tmp_path):
    now = time.time()
    for i in range(15):
        _create_message(tmp_path, f"cur/msg{i:02d}", MB, days_old=i + 1)
    removed = expire_to_target(str(tmp_path), 10 * MB, now=now)
    assert len(removed) == 5
    assert len(scan_mailbox_messages(str(tmp_path))) == 10


def test_scoring_prefers_large_old(tmp_path):
    now = time.time()
    _create_message(tmp_path, "cur/large_old", 2 * MB, days_old=30)
    _create_message(tmp_path, "cur/small_new", MB, days_old=1)
    removed = expire_to_target(str(tmp_path), 2 * MB, now=now)
    assert len(removed) == 1
    assert "large_old" in removed[0]


def test_scoring_large_new_beats_small_old(tmp_path):
    now = time.time()
    _create_message(tmp_path, "cur/big_new", 10 * MB, days_old=1)
    _create_message(tmp_path, "cur/small_old", MB, days_old=5)
    # big_new score: 10MB * 1d = 10  vs  small_old score: 1MB * 5d = 5
    removed = expire_to_target(str(tmp_path), 10 * MB, now=now)
    assert len(removed) == 1
    assert "big_new" in removed[0]


def test_exact_limit(tmp_path):
    _create_message(tmp_path, "cur/msg1", 5 * MB)
    assert expire_to_target(str(tmp_path), 5 * MB) == []


def test_removes_stale_caches(tmp_path):
    _create_message(tmp_path, "cur/msg1", 2 * MB, days_old=5)
    (tmp_path / "maildirsize").write_text("x")
    (tmp_path / "dovecot.index.cache").write_text("x")
    expire_to_target(str(tmp_path), MB)
    assert not (tmp_path / "maildirsize").exists()
    assert not (tmp_path / "dovecot.index.cache").exists()


def test_no_cache_removal_when_under_limit(tmp_path):
    _create_message(tmp_path, "cur/msg1", MB)
    (tmp_path / "maildirsize").write_text("x")
    expire_to_target(str(tmp_path), 2 * MB)
    assert (tmp_path / "maildirsize").exists()
