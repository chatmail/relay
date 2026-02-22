import time
def test_tls_imap(benchmark, imap):
    def imap_connect():
        imap.connect()

    benchmark(imap_connect, 10)


def test_login_imap(benchmark, imap, gencreds):
    def imap_connect_and_login():
        imap.connect()
        imap.login(*gencreds())

    benchmark(imap_connect_and_login, 10)


def test_tls_smtp(benchmark, smtp):
    def smtp_connect():
        smtp.connect()

    benchmark(smtp_connect, 10)


def test_login_smtp(benchmark, smtp, gencreds):
    def smtp_connect_and_login():
        smtp.connect()
        smtp.login(*gencreds())

    benchmark(smtp_connect_and_login, 10)


class TestDC:
    def test_autoconfigure(self, benchmark, cmfactory):
        def dc_autoconfig_and_idle_ready():
            cmfactory.get_online_accounts(1)

        benchmark(dc_autoconfig_and_idle_ready, 5)

    def test_ping_pong(self, benchmark, cmfactory):
        ac1, ac2 = cmfactory.get_online_accounts(2)
        chat = cmfactory.get_accepted_chat(ac1, ac2)

        def dc_ping_pong():
            chat.send_text("ping")
            msg = ac2._evtracker.wait_next_incoming_message()
            msg.chat.send_text("pong")
            ac1._evtracker.wait_next_incoming_message()

        benchmark(dc_ping_pong, 5)

    def test_send_10_receive_10(self, request, cmfactory, chatmail_config, lp):
        ac1, ac2 = cmfactory.get_online_accounts(2)
        chat = cmfactory.get_accepted_chat(ac1, ac2)

        def dc_send_10_receive_10():
            for i in range(10):
                chat.send_text(f"hello {i}")
            for i in range(10):
                ac2._evtracker.wait_next_incoming_message()

        per_minute = max(chatmail_config.max_user_send_per_minute, 1)
        cooldown = chatmail_config.max_user_send_burst_size * 60 / per_minute
        durations = []
        num = 5
        for i in range(num):
            now = time.time()
            dc_send_10_receive_10()
            durations.append(time.time() - now)
            if i + 1 < num:
                # Keep post-run cooldown out of measured benchmark duration.
                time.sleep(cooldown)
        durations.sort()
        request.config._benchresults["dc_send_10_receive_10"] = (None, durations)
