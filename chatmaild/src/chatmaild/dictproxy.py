import logging
import os
from socketserver import StreamRequestHandler, ThreadingUnixStreamServer


class DictProxy:
    def loop_forever(self, rfile, wfile):
        # Transaction storage is local to each handler loop.
        # Dovecot reuses transaction IDs across connections,
        # starting transaction with the name `1`
        # on two different connections to the same proxy sometimes.
        transactions = {}

        while True:
            msg = rfile.readline().strip().decode()
            if not msg:
                break

            res = self.handle_dovecot_request(msg, transactions)
            if res:
                wfile.write(res.encode("ascii"))
                wfile.flush()

    def handle_dovecot_request(self, msg, transactions):
        # see https://doc.dovecot.org/2.3/developer_manual/design/dict_protocol/#dovecot-dict-protocol
        short_command = msg[0]
        parts = msg[1:].split("\t")

        if short_command == "L":
            return self.handle_lookup(parts)
        elif short_command == "I":
            return self.handle_iterate(parts)
        elif short_command == "H":
            return  # no version checking

        if short_command not in ("BSC"):
            logging.warning(f"unknown dictproxy request: {msg!r}")
            return

        transaction_id = parts[0]

        if short_command == "B":
            return self.handle_begin_transaction(transaction_id, parts, transactions)
        elif short_command == "C":
            return self.handle_commit_transaction(transaction_id, parts, transactions)
        elif short_command == "S":
            addr = transactions[transaction_id]["addr"]
            if not self.handle_set(addr, parts):
                transactions[transaction_id]["res"] = "F\n"
                logging.error(f"dictproxy-set failed for {addr!r}: {msg!r}")

    def handle_lookup(self, parts):
        logging.warning(f"lookup ignored: {parts!r}")
        return "N\n"

    def handle_iterate(self, parts):
        # Empty line means ITER_FINISHED.
        # If we don't return empty line Dovecot will timeout.
        return "\n"

    def handle_begin_transaction(self, transaction_id, parts, transactions):
        addr = parts[1]
        transactions[transaction_id] = dict(addr=addr, res="O\n")

    def handle_set(self, addr, parts):
        # For documentation on key structure see
        # https://github.com/dovecot/core/blob/main/src/lib-storage/mailbox-attribute.h
        return False

    def handle_commit_transaction(self, transaction_id, parts, transactions):
        # return whatever "set" command(s) set as result.
        return transactions.pop(transaction_id)["res"]

    def serve_forever_from_socket(self, socket):
        dictproxy = self

        class Handler(StreamRequestHandler):
            def handle(self):
                try:
                    dictproxy.loop_forever(self.rfile, self.wfile)
                except Exception:
                    logging.exception("Exception in the handler")
                    raise

        try:
            os.unlink(socket)
        except FileNotFoundError:
            pass

        with CustomThreadingUnixStreamServer(socket, Handler) as server:
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


class CustomThreadingUnixStreamServer(ThreadingUnixStreamServer):
    request_queue_size = 1000
