function dovecot_lua_notify_begin_txn(user)
  return user
end

function contains(v, needle)
  for _, keyword in ipairs(v) do
    if keyword == needle then
      return true
    end
  end
  return false
end

function dovecot_lua_notify_event_message_new(user, event)
  local mbox = user:mailbox(event.mailbox)
  mbox:sync()

  if user.username ~= event.from_address then
    -- Incoming message
    if not contains(event.keywords, "$Auto") then
      -- Not an Auto-Submitted message, notifying.

      -- Notify METADATA server about new message.
      mbox:metadata_set("/private/messagenew", "")
    end
  end

  mbox:free()
end

function dovecot_lua_notify_end_txn(ctx, success)
end
