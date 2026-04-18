import os
import time

from chatmaild.quota_expire import expire_to_target, main, scan_mailbox_messages

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
    assert len(scan_mailbox_messages(str(tmp_path))) == 3


def test_scan_ignores_subfolders(tmp_path):
    _create_message(tmp_path, "cur/a", 10)
    _create_message(tmp_path, ".DeltaChat/cur/b", 20)
    assert len(scan_mailbox_messages(str(tmp_path))) == 1


def test_removes_to_target(tmp_path):
    for i in range(15):
        _create_message(tmp_path, f"cur/msg{i:02d}", MB, days_old=i + 1)
    removed, _ = expire_to_target(str(tmp_path), 10 * MB)
    assert removed == 5
    assert len(scan_mailbox_messages(str(tmp_path))) == 10


def test_removes_oldest_first(tmp_path):
    _create_message(tmp_path, "cur/old_small", MB, days_old=30)
    _create_message(tmp_path, "cur/new_huge", 10 * MB, days_old=1)
    # the 10MB file is kept, the 1MB file is removed because it's older
    removed, _ = expire_to_target(str(tmp_path), 10 * MB)
    assert removed == 1
    assert not (tmp_path / "cur/old_small").exists()
    assert (tmp_path / "cur/new_huge").exists()


def test_exact_limit(tmp_path):
    _create_message(tmp_path, "cur/msg1", 5 * MB)
    removed, _ = expire_to_target(str(tmp_path), 5 * MB)
    assert removed == 0


def test_removes_stale_caches(tmp_path):
    _create_message(tmp_path, "cur/msg1", 2 * MB, days_old=5)
    (tmp_path / "maildirsize").write_text("x")
    (tmp_path / "dovecot.index.cache").write_bytes(b"y" * 4096)
    removed, cache_bytes = expire_to_target(str(tmp_path), MB)
    assert removed == 1
    assert cache_bytes == 4096
    assert not (tmp_path / "maildirsize").exists()
    assert not (tmp_path / "dovecot.index.cache").exists()


def test_logging_output_is_mtail_compatible(tmp_path, capsys):
    mbox = tmp_path / "user@example.org"
    _create_message(mbox, "cur/msg1", 2 * MB, days_old=5)
    (mbox / "dovecot.index.cache").write_bytes(b"c" * 2 * MB)
    main([str(1), str(mbox)])
    _, err = capsys.readouterr()
    assert "quota-expire: removed 1 message(s) from user@example.org" in err
    assert "cache=2.0MB" in err
