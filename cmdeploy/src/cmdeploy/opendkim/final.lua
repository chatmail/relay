if odkim.internal_ip(ctx) == 1 then
	-- Outgoing message will be signed,
	-- no need to look for signatures.
	return nil
end

nsigs = odkim.get_sigcount(ctx)
if nsigs == nil then
	return nil
end

local valid = false
for i = 1, nsigs do
	sig = odkim.get_sighandle(ctx, i - 1)
	sigres = odkim.sig_result(sig)

	-- All signatures that do not correspond to From: 
	-- were ignored in screen.lua and return sigres -1.
	-- 
	-- Any valid signature that was not ignored like this
	-- means the message is acceptable.
	if sigres == 0 then
		valid = true
	end
end

if valid then
	-- Strip all DKIM-Signature headers after successful validation
	-- Delete in reverse order to avoid index shifting.
	for i = nsigs, 1, -1 do
		odkim.del_header(ctx, "DKIM-Signature", i)
	end
else
	odkim.set_reply(ctx, "554", "5.7.1", "No valid DKIM signature found")
	odkim.set_result(ctx, SMFIS_REJECT)
end

return nil
