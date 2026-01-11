
# No-DNS Chatmail relay

With this branch, you don't need DNS at all,
just a VPS with an IPv4 address,
let's take `77.42.80.106` as an example.
First, choose a random domain name (it doesn't need working DNS)
and create a chatmail.ini config file:

```
cmdeploy init whatever.you.want
```

Then, in `cmdeploy/src/cmdeploy/postfix/transport`,
remove the line corresponding to your relay,
and add other for relays you know.
Now you can deploy the relay to your IP address:

```
cmdeploy run --skip-dns-check --ssh-host 77.42.80.106
```

Finally, you can login with a `dclogin://` code like this, with the correct "domain name" and IP address:

`dclogin:s0m3r4nd0@whatever.you.want?p=w7i8da7h8uads92ycc2rufyl&v=1&ih=77.42.80.106&sh=77.42.80.106&sp=443&ip=443&ic=3&sc=3`
