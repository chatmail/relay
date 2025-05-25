function dovecot_lua_notify_begin_txn(user)
  return user
end

function dovecot_lua_notify_event_message_new(user, event)
  local mbox = user:mailbox(event.mailbox)
  mbox:sync()

  if user.username ~= event.from_address then
    -- Incoming message
    -- Notify METADATA server about new message.
    mbox:metadata_set("/private/messagenew", "")
  end

  mbox:free()
end

function dovecot_lua_notify_end_txn(ctx, success)
end
