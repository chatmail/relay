
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
chatmail relay, follow these instructions:

Linux
^^^^^

Put the following configuration in
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

FreeBSD / pf
^^^^^^^^^^^^

Put the following configuration in
``/etc/pf.conf``:

::

    ext_if = "em0"
    forward_ports = "{ 25, 80, 143, 443, 465, 587, 993 }"
    chatmail_ipv4 = "AAA.BBB.CCC.DDD"
    icmp_types = "{ echoreq, echorep, unreach, timex }"
    chatmail_ipv6 = "XXX::1"
    icmp6_types = "{ echorep, echoreq, neighbradv, neighbrsol, routeradv, routersol, unreach, toobig, timex }"

    set skip on lo0

    nat on $ext_if inet from any to any -> ($ext_if:0)
    nat on $ext_if inet6 from any to any -> ($ext_if:0)

    # Define the redirect rules
    rdr on $ext_if inet proto tcp from any to ($ext_if:0) port $forward_ports -> $chatmail_ipv4
    rdr on $ext_if inet6 proto tcp from any to ($ext_if:0) port $forward_ports -> $chatmail_ipv6

    # Accept the incoming traffic to the specified ports we will NAT redirect
    pass in quick on $ext_if inet proto tcp from any to any port $forward_ports flags S/SA modulate state
    pass in quick on $ext_if inet6 proto tcp from any to any port $forward_ports flags S/SA modulate state

    # Allow incoming SSH for host mgmt
    pass in quick on $ext_if proto tcp from any to ($ext_if) port 22 flags S/SA modulate state

    # Allow ICMP
    pass in quick on $ext_if inet proto icmp all icmp-type $icmp_types keep state
    pass in quick on $ext_if inet6 proto ipv6-icmp all icmp6-type $icmp6_types keep state

    # Allow traffic from anyone to go through the NAT
    pass on $ext_if inet proto tcp from any to $chatmail_ipv4 flags S/SA modulate state
    pass on $ext_if inet6 proto tcp from any to $chatmail_ipv6 flags S/SA modulate state

    # Default allow out
    pass out quick on $ext_if from any to any

    # Default block
    block drop in log all

Insert into ``/etc/sysctl.conf.local`` the following two lines:

::

    net.inet.ip.forwarding=1
    net.inet6.ip6.forwarding=1

Activate the sysctls with ``service sysctl onestart``.
Enable the pf firewall with ``service pf enable``.
Apply the firewall rules with ``service pf start`` or ``pfctl -f /etc/pf.conf``.
Note, enabling the firewall may interrupt your SSH session, but you can reconnect.

Once proxy relay is set up, you can add its IP address to the DNS.
