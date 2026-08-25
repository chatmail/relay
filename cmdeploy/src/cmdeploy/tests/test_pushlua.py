"""Test the push_notification.lua we ship, against a mocked dovecot mail API."""

import textwrap

import pytest

USER1 = "user12345@chat.example.org"
USER2 = "user67890@chat.example.org"

DOVECOT_MOCKS = textwrap.dedent("""
    function make_user(username)
      local function mailbox(_, name)
        record("mailbox " .. name)
        return {
          sync = function() record("sync") end,
          metadata_set = function(_, k, v)
            record("metadata_set " .. k .. "=" .. v)
          end,
          free = function() record("free") end,
        }
      end
      return {username = username, mailbox = mailbox}
    end
""")


@pytest.fixture
def script(lua):
    lua.rt.execute(DOVECOT_MOCKS)
    lua.load("dovecot/push_notification.lua")
    return lua


@pytest.fixture
def deliver(script):
    def deliver(recipient, sender):
        calls = []
        script.g.record = calls.append
        user = script.g.make_user(recipient)
        ctx = script.g.dovecot_lua_notify_begin_txn(user)
        event = script.table(mailbox="INBOX", from_address=sender)
        script.g.dovecot_lua_notify_event_message_new(ctx, event)
        script.g.dovecot_lua_notify_end_txn(ctx, True)
        return calls

    return deliver


def test_entry_points_have_the_names_dovecot_calls(script):
    assert script.g.dovecot_lua_notify_begin_txn is not None
    assert script.g.dovecot_lua_notify_event_message_new is not None
    assert script.g.dovecot_lua_notify_end_txn is not None


def test_begin_txn_returns_the_user_as_event_context(script):
    user = script.g.make_user(USER1)
    ctx = script.g.dovecot_lua_notify_begin_txn(user)
    ctx.marker = "seen"
    assert user.marker == "seen"


def test_incoming_message_notifies_metadata_server(deliver):
    assert deliver(USER1, sender=USER2) == [
        "mailbox INBOX",
        "sync",
        "metadata_set /private/messagenew=",
        "free",
    ]


def test_own_message_does_not_wake_the_sending_device(deliver):
    assert deliver(USER1, sender=USER1) == [
        "mailbox INBOX",
        "sync",
        "free",
    ]


def test_message_without_from_address_is_notified(deliver):
    assert deliver(USER1, sender=None) == [
        "mailbox INBOX",
        "sync",
        "metadata_set /private/messagenew=",
        "free",
    ]
