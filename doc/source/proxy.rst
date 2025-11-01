
Setting up a reverse proxy
--------------------------

A chatmail relay MTA does not track or depend on the client IP address
for its operation, so it can be run behind a reverse proxy. This will
not even affect incoming mail authentication as DKIM only checks the
cryptographic signature of the message and does not use the IP address
as the input.

For example, you may want to self-host your chatmail relay and only use
hosted VPS to provide a public IP address for client connections and
incoming mail. You can connect chatmail relay to VPS using a tunnel
protocol such as `WireGuard <https://www.wireguard.com/>`_ and setup a
reverse proxy on a VPS to forward connections to the chatmail relay over
the tunnel. You can also setup multiple reverse proxies for your
chatmail relay in different networks to ensure your relay is reachable
even when one of the IPs becomes inaccessible due to hosting or routing
problems.

Note that your chatmail relay still needs to be able to make outgoing
connections on port 25 to send messages outside.

To setup a reverse proxy (or rather Destination NAT, DNAT) for your
chatmail relay, put the following configuration in
``/etc/nftables.conf``:

::

   #!/usr/sbin/nft -f

   flush ruleset

   define wan = eth0

   # Which ports to proxy.
   #
   # Note that SSH is not proxied
   # so it is possible to log into the proxy server
   # and not the original one.
   define ports = { smtp, http, https, imap, imaps, submission, submissions }

   # The host we want to proxy to.
   define ipv4_address = AAA.BBB.CCC.DDD
   define ipv6_address = [XXX::1]

   table ip nat {
           chain prerouting {
                   type nat hook prerouting priority dstnat; policy accept;
                   iif $wan tcp dport $ports dnat to $ipv4_address
           }

           chain postrouting {
                   type nat hook postrouting priority 0;

                   oifname $wan masquerade
           }
   }

   table ip6 nat {
           chain prerouting {
                   type nat hook prerouting priority dstnat; policy accept;
                   iif $wan tcp dport $ports dnat to $ipv6_address
           }

           chain postrouting {
                   type nat hook postrouting priority 0;

                   oifname $wan masquerade
           }
   }

   table inet filter {
           chain input {
                   type filter hook input priority filter; policy drop;

                   # Accept ICMP.
                   # It is especially important to accept ICMPv6 ND messages,
                   # otherwise IPv6 connectivity breaks.
                   icmp type { echo-request } accept
                   icmpv6 type { echo-request, nd-neighbor-solicit, nd-router-advert, nd-neighbor-advert } accept

                   # Allow incoming SSH connections.
                   tcp dport { ssh } accept

                   ct state established accept
           }
           chain forward {
                   type filter hook forward priority filter; policy drop;

                   ct state established accept
                   ip daddr $ipv4_address counter accept
                   ip6 daddr $ipv6_address counter accept
           }
           chain output {
                   type filter hook output priority filter;
           }
   }

Run ``systemctl enable nftables.service`` to ensure configuration is
reloaded when the proxy relay reboots.

Uncomment in ``/etc/sysctl.conf`` the following two lines:

::

   net.ipv4.ip_forward=1
   net.ipv6.conf.all.forwarding=1

Then reboot the relay or do ``sysctl -p`` and
``nft -f /etc/nftables.conf``.

Once proxy relay is set up, you can add its IP address to the DNS.

