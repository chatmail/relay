"""
This modules provides notification machinery for transmitting device tokens to
a central notification server which in turn contacts a phone provider's notification server
to trigger Delta Chat apps to retrieve messages and provide instant notifications to users.

The Notifier class arranges the queuing of tokens in separate PriorityQueues
from which NotifyThreads take and transmit them via HTTPS
to the `notifications.delta.chat` service.
The current lack of proper HTTP/2-support in Python leads us
to use multiple threads and connections to the Rust-implemented `notifications.delta.chat`
which itself uses HTTP/2 and thus only a single connection to phone-notification providers.

If a token fails to cause a successful notification
it is moved to a retry-number specific PriorityQueue
which handles all tokens that failed a particular number of times
and which are scheduled for retry using exponential back-off timing.
If a token notification would be scheduled more than DROP_DEADLINE seconds
after its first attempt, it is dropped with a log error.

Note that tokens are opaque to the notification machinery here
and are encrypted foreclosing all ability to distinguish
which device token ultimately goes to which phone-provider notification service,
or to understand the relation of "device tokens" and chatmail addresses.
The meaning and format of tokens is basically a matter of chatmail Core and
the `notification.delta.chat` service.
"""

import logging
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from queue import PriorityQueue
from threading import Thread
from uuid import uuid4

import requests


@dataclass
class PersistentQueueItem:
    path: Path
    addr: str
    start_ts: int
    token: str

    def delete(self):
        self.path.unlink(missing_ok=True)

    @classmethod
    def create(cls, queue_dir, addr, start_ts, token):
        queue_id = uuid4().hex
        start_ts = int(start_ts)
        path = queue_dir.joinpath(queue_id)
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(f"{addr}\n{start_ts}\n{token}")
        os.rename(tmp_path, path)
        return cls(path, addr, start_ts, token)

    @classmethod
    def read_from_path(cls, path):
        addr, start_ts, token = path.read_text().split("\n", maxsplit=2)
        return cls(path, addr, int(start_ts), token)

    def __lt__(self, other):
        return self.start_ts < other.start_ts


class Notifier:
    URL = "https://notifications.delta.chat/notify"
    CONNECTION_TIMEOUT = 60.0  # seconds until http-request is given up
    BASE_DELAY = 8.0  # base seconds for exponential back-off delay
    DROP_DEADLINE = 5 * 60 * 60  #  drop notifications after 5 hours

    def __init__(self, queue_dir):
        self.queue_dir = queue_dir
        max_tries = int(math.log(self.DROP_DEADLINE, self.BASE_DELAY)) + 1
        self.retry_queues = [PriorityQueue() for _ in range(max_tries)]

    def compute_delay(self, retry_num):
        return 0 if retry_num == 0 else pow(self.BASE_DELAY, retry_num)

    def new_message_for_addr(self, addr, metadata):
        start_ts = int(time.time())
        for token in metadata.get_tokens_for_addr(addr):
            queue_item = PersistentQueueItem.create(
                self.queue_dir, addr, start_ts, token
            )
            self.queue_for_retry(queue_item)

    def requeue_persistent_queue_items(self):
        for queue_path in self.queue_dir.iterdir():
            if queue_path.name.endswith(".tmp"):
                logging.warning(f"removing spurious queue item: {queue_path!r}")
                queue_path.unlink()
                continue
            try:
                queue_item = PersistentQueueItem.read_from_path(queue_path)
            except ValueError:
                logging.warning(f"removing spurious queue item: {queue_path!r}")
                queue_path.unlink()
                continue
            self.queue_for_retry(queue_item)

    def queue_for_retry(self, queue_item, retry_num=0):
        delay = self.compute_delay(retry_num)
        when = int(time.time()) + delay
        deadline = queue_item.start_ts + self.DROP_DEADLINE
        if retry_num >= len(self.retry_queues) or when > deadline:
            queue_item.delete()
            logging.error(f"notification exceeded deadline: {queue_item.token!r}")
            return

        self.retry_queues[retry_num].put((when, queue_item))

    def start_notification_threads(self, remove_token_from_addr):
        self.requeue_persistent_queue_items()
        threads = {}
        for retry_num in range(len(self.retry_queues)):
            # use 4 threads for first-try tokens and less for subsequent tries
            num_threads = 4 if retry_num == 0 else 2
            threads[retry_num] = []
            for _ in range(num_threads):
                thread = NotifyThread(self, retry_num, remove_token_from_addr)
                threads[retry_num].append(thread)
                thread.start()
        return threads


class NotifyThread(Thread):
    def __init__(self, notifier, retry_num, remove_token_from_addr):
        super().__init__(daemon=True)
        self.notifier = notifier
        self.retry_num = retry_num
        self.remove_token_from_addr = remove_token_from_addr

    def stop(self):
        self.notifier.retry_queues[self.retry_num].put((None, None))

    def run(self):
        requests_session = requests.Session()
        while self.retry_one(requests_session):
            pass

    def retry_one(self, requests_session, sleep=time.sleep):
        when, queue_item = self.notifier.retry_queues[self.retry_num].get()
        if when is None:
            return False
        wait_time = when - int(time.time())
        if wait_time > 0:
            sleep(wait_time)
        self.perform_request_to_notification_server(requests_session, queue_item)
        return True

    def perform_request_to_notification_server(self, requests_session, queue_item):
        timeout = self.notifier.CONNECTION_TIMEOUT
        token = queue_item.token
        try:
            res = requests_session.post(self.notifier.URL, data=token, timeout=timeout)
        except requests.exceptions.RequestException as e:
            res = e
        else:
            if res.status_code in (200, 410):
                if res.status_code == 410:
                    self.remove_token_from_addr(queue_item.addr, token)
                queue_item.delete()
                return

        logging.warning(f"Notification request failed: {res!r}")
        self.notifier.queue_for_retry(queue_item, retry_num=self.retry_num + 1)
