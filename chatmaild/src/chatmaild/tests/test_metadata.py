import io
import time

import pytest
import requests

from chatmaild.metadata import (
    Metadata,
    MetadataDictProxy,
)
from chatmaild.notifier import (
    Notifier,
    NotifyThread,
    PersistentQueueItem,
)


@pytest.fixture
def notifier(metadata):
    queue_dir = metadata.vmail_dir.joinpath("pending_notifications")
    queue_dir.mkdir()
    return Notifier(queue_dir)


@pytest.fixture
def metadata(tmp_path):
    vmail_dir = tmp_path.joinpath("vmaildir")
    vmail_dir.mkdir()
    return Metadata(vmail_dir)


@pytest.fixture
def dictproxy(notifier, metadata):
    return MetadataDictProxy(notifier=notifier, metadata=metadata)


@pytest.fixture
def testaddr2():
    return "user2@example.org"


@pytest.fixture
def token():
    return "01234"


def get_mocked_requests(statuslist):
    class ReqMock:
        requests = []

        def post(self, url, data, timeout):
            self.requests.append((url, data, timeout))
            res = statuslist.pop(0)
            if isinstance(res, Exception):
                raise res

            class Result:
                status_code = res

            return Result()

    return ReqMock()


def test_metadata_persistence(tmp_path, testaddr, testaddr2):
    metadata1 = Metadata(tmp_path)
    metadata2 = Metadata(tmp_path)
    assert not metadata1.get_tokens_for_addr(testaddr)
    assert not metadata2.get_tokens_for_addr(testaddr)

    metadata1.add_token_to_addr(testaddr, "01234")
    metadata1.add_token_to_addr(testaddr2, "456")
    assert metadata2.get_tokens_for_addr(testaddr) == ["01234"]
    assert metadata2.get_tokens_for_addr(testaddr2) == ["456"]
    metadata2.remove_token_from_addr(testaddr, "01234")
    assert not metadata1.get_tokens_for_addr(testaddr)
    assert metadata1.get_tokens_for_addr(testaddr2) == ["456"]


def test_remove_nonexisting(metadata, tmp_path, testaddr):
    metadata.add_token_to_addr(testaddr, "123")
    metadata.remove_token_from_addr(testaddr, "1l23k1l2k3")
    assert metadata.get_tokens_for_addr(testaddr) == ["123"]


def test_notifier_remove_without_set(metadata, testaddr):
    metadata.remove_token_from_addr(testaddr, "123")
    assert not metadata.get_tokens_for_addr(testaddr)


def test_handle_dovecot_request_lookup_fails(dictproxy, testaddr):
    transactions = {}
    res = dictproxy.handle_dovecot_request(
        f"Lpriv/123/chatmail\t{testaddr}", transactions
    )
    assert res == "N\n"


def test_handle_dovecot_request_happy_path(dictproxy, testaddr, token):
    metadata = dictproxy.metadata
    transactions = {}
    notifier = dictproxy.notifier

    # set device token in a transaction
    tx = "1111"
    msg = f"B{tx}\t{testaddr}"
    res = dictproxy.handle_dovecot_request(msg, transactions)
    assert not res and not metadata.get_tokens_for_addr(testaddr)
    assert transactions == {tx: dict(addr=testaddr, res="O\n")}

    msg = f"S{tx}\tpriv/guid00/devicetoken\t{token}"
    res = dictproxy.handle_dovecot_request(msg, transactions)
    assert not res
    assert len(transactions) == 1
    assert metadata.get_tokens_for_addr(testaddr) == [token]

    msg = f"C{tx}"
    res = dictproxy.handle_dovecot_request(msg, transactions)
    assert res == "O\n"
    assert len(transactions) == 0
    assert metadata.get_tokens_for_addr(testaddr) == [token]

    # trigger notification for incoming message
    tx2 = "2222"
    assert dictproxy.handle_dovecot_request(f"B{tx2}\t{testaddr}", transactions) is None
    msg = f"S{tx2}\tpriv/guid00/messagenew"
    assert dictproxy.handle_dovecot_request(msg, transactions) is None
    queue_item = notifier.retry_queues[0].get()[1]
    assert queue_item.token == token
    assert dictproxy.handle_dovecot_request(f"C{tx2}", transactions) == "O\n"
    assert not transactions
    assert queue_item.path.exists()


def test_handle_dovecot_protocol_set_devicetoken(dictproxy):
    rfile = io.BytesIO(
        b"\n".join(
            [
                b"HELLO",
                b"Btx00\tuser@example.org",
                b"Stx00\tpriv/guid00/devicetoken\t01234",
                b"Ctx00",
            ]
        )
    )
    wfile = io.BytesIO()
    dictproxy.loop_forever(rfile, wfile)
    assert wfile.getvalue() == b"O\n"
    assert dictproxy.metadata.get_tokens_for_addr("user@example.org") == ["01234"]


def test_handle_dovecot_protocol_set_get_devicetoken(dictproxy):
    rfile = io.BytesIO(
        b"\n".join(
            [
                b"HELLO",
                b"Btx00\tuser@example.org",
                b"Stx00\tpriv/guid00/devicetoken\t01234",
                b"Ctx00",
            ]
        )
    )
    wfile = io.BytesIO()
    dictproxy.loop_forever(rfile, wfile)
    assert dictproxy.metadata.get_tokens_for_addr("user@example.org") == ["01234"]
    assert wfile.getvalue() == b"O\n"

    rfile = io.BytesIO(
        b"\n".join([b"HELLO", b"Lpriv/0123/devicetoken\tuser@example.org"])
    )
    wfile = io.BytesIO()
    dictproxy.loop_forever(rfile, wfile)
    assert wfile.getvalue() == b"O01234\n"


def test_handle_dovecot_protocol_iterate(dictproxy):
    rfile = io.BytesIO(
        b"\n".join(
            [
                b"H",
                b"I9\t0\tpriv/5cbe730f146fea6535be0d003dd4fc98/\tci-2dzsrs@nine.testrun.org",
            ]
        )
    )
    wfile = io.BytesIO()
    dictproxy.loop_forever(rfile, wfile)
    assert wfile.getvalue() == b"\n"


def test_notifier_thread_deletes_persistent_file(metadata, notifier, testaddr):
    reqmock = get_mocked_requests([200])
    metadata.add_token_to_addr(testaddr, "01234")
    notifier.new_message_for_addr(testaddr, metadata)
    NotifyThread(notifier, 0, None).retry_one(reqmock)
    url, data, timeout = reqmock.requests[0]
    assert data == "01234"
    assert metadata.get_tokens_for_addr(testaddr) == ["01234"]
    notifier.requeue_persistent_queue_items()
    assert notifier.retry_queues[0].qsize() == 0


@pytest.mark.parametrize("status", [requests.exceptions.RequestException(), 404, 500])
def test_notifier_thread_connection_failures(
    metadata, notifier, testaddr, status, caplog
):
    """test that tokens keep getting retried until they are given up."""
    metadata.add_token_to_addr(testaddr, "01234")
    notifier.new_message_for_addr(testaddr, metadata)
    notifier.NOTIFICATION_RETRY_DELAY = 5
    max_tries = len(notifier.retry_queues)
    for i in range(max_tries):
        caplog.clear()
        reqmock = get_mocked_requests([status])
        sleep_calls = []
        NotifyThread(notifier, i, None).retry_one(reqmock, sleep=sleep_calls.append)
        assert notifier.retry_queues[i].qsize() == 0
        assert "request failed" in caplog.records[0].msg
        if i > 0:
            assert len(sleep_calls) == 1
        if i + 1 < max_tries:
            assert notifier.retry_queues[i + 1].qsize() == 1
            assert len(caplog.records) == 1
        else:
            assert len(caplog.records) == 2
            assert "deadline" in caplog.records[1].msg
    notifier.requeue_persistent_queue_items()
    assert notifier.retry_queues[0].qsize() == 0


def test_requeue_removes_tmp_files(notifier, metadata, testaddr, caplog):
    metadata.add_token_to_addr(testaddr, "01234")
    notifier.new_message_for_addr(testaddr, metadata)
    p = notifier.queue_dir.joinpath("1203981203.tmp")
    p.touch()
    notifier2 = notifier.__class__(notifier.queue_dir)
    notifier2.requeue_persistent_queue_items()
    assert "spurious" in caplog.records[0].msg
    assert not p.exists()
    assert notifier2.retry_queues[0].qsize() == 1
    when, queue_item = notifier2.retry_queues[0].get()
    assert when <= int(time.time())
    assert queue_item.addr == testaddr


def test_requeue_removes_invalid_files(notifier, metadata, testaddr, caplog):
    metadata.add_token_to_addr(testaddr, "01234")
    notifier.new_message_for_addr(testaddr, metadata)
    # empty/invalid files should be ignored
    p = notifier.queue_dir.joinpath("1203981203")
    p.touch()
    notifier2 = notifier.__class__(notifier.queue_dir)
    notifier2.requeue_persistent_queue_items()
    assert "spurious" in caplog.records[0].msg
    assert not p.exists()
    assert notifier2.retry_queues[0].qsize() == 1
    when, queue_item = notifier2.retry_queues[0].get()
    assert when <= int(time.time())
    assert queue_item.addr == testaddr


def test_start_and_stop_notification_threads(notifier, testaddr):
    threads = notifier.start_notification_threads(None)
    for retry_num, threadlist in threads.items():
        for t in threadlist:
            t.stop()
            t.join()


def test_multi_device_notifier(metadata, notifier, testaddr):
    metadata.add_token_to_addr(testaddr, "01234")
    metadata.add_token_to_addr(testaddr, "56789")
    notifier.new_message_for_addr(testaddr, metadata)
    reqmock = get_mocked_requests([200, 200])
    NotifyThread(notifier, 0, None).retry_one(reqmock)
    NotifyThread(notifier, 0, None).retry_one(reqmock)
    assert notifier.retry_queues[0].qsize() == 0
    assert notifier.retry_queues[1].qsize() == 0
    url, data, timeout = reqmock.requests[0]
    assert data == "01234"
    url, data, timeout = reqmock.requests[1]
    assert data == "56789"
    assert metadata.get_tokens_for_addr(testaddr) == ["01234", "56789"]


def test_notifier_thread_run_gone_removes_token(metadata, notifier, testaddr):
    metadata.add_token_to_addr(testaddr, "01234")
    metadata.add_token_to_addr(testaddr, "45678")
    notifier.new_message_for_addr(testaddr, metadata)

    reqmock = get_mocked_requests([410, 200])
    NotifyThread(notifier, 0, metadata.remove_token_from_addr).retry_one(reqmock)
    NotifyThread(notifier, 0, None).retry_one(reqmock)
    url, data, timeout = reqmock.requests[0]
    assert data == "01234"
    url, data, timeout = reqmock.requests[1]
    assert data == "45678"
    assert metadata.get_tokens_for_addr(testaddr) == ["45678"]
    assert notifier.retry_queues[0].qsize() == 0
    assert notifier.retry_queues[1].qsize() == 0


def test_persistent_queue_items(tmp_path, testaddr, token):
    queue_item = PersistentQueueItem.create(tmp_path, testaddr, 432, token)
    assert queue_item.addr == testaddr
    assert queue_item.start_ts == 432
    assert queue_item.token == token
    item2 = PersistentQueueItem.read_from_path(queue_item.path)
    assert item2.addr == testaddr
    assert item2.start_ts == 432
    assert item2.token == token
    assert item2 == queue_item
    item2.delete()
    assert not item2.path.exists()
    assert not queue_item < item2 and not item2 < queue_item


def test_iroh_relay(dictproxy):
    rfile = io.BytesIO(
        b"\n".join(
            [
                b"H",
                b"Lshared/0123/vendor/vendor.dovecot/pvt/server/vendor/deltachat/irohrelay\tuser@example.org",
            ]
        )
    )
    wfile = io.BytesIO()
    dictproxy.iroh_relay = "https://example.org/"
    dictproxy.loop_forever(rfile, wfile)
    assert wfile.getvalue() == b"Ohttps://example.org/\n"
