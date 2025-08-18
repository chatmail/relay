This diagram shows components of the chatmail server; this is a draft
overview as of mid-August 2025:

```mermaid
graph LR;
    cmdeploy --- sshd;
    letsencrypt --- |80|acmetool-redirector;
    acmetool-redirector --- |443|nginx-right(["`nginx
    (external)`"]);
    nginx-external --- |465|postfix;
    nginx-external(["`nginx
    (external)`"]) --- |8443|nginx-internal["`nginx
    (internal)`"];
    nginx-internal --- website["`Website
    /var/www/html`"];
    nginx-internal --- newemail.py;
    nginx-internal --- autoconfig.xml;
    certs-nginx[("`TLS certs
    /var/lib/acme`")] --> nginx-internal;
    cron --- chatmail-metrics;
    cron --- acmetool;
    cron --- expunge;
    chatmail-metrics --- website;
    acmetool --> certs[("`TLS certs
    /var/lib/acme`")];
    nginx-external --- |993|dovecot;
    autoconfig.xml --- postfix;
    autoconfig.xml --- dovecot;
    postfix --- echobot;
    postfix --- |10080,10081|filtermail;
    postfix --- users["`User data
    home/vmail/mail`"];
    postfix --- |doveauth.socket|doveauth;
    dovecot --- |doveauth.socket|doveauth;
    dovecot --- users;
    dovecot --- |metadata.socket|chatmail-metadata;
    doveauth --- users;
    expunge --- users;
    chatmail-metadata --- iroh-relay;
    certs-nginx --> postfix;
    certs-nginx --> dovecot;
    style certs fill:#ff6;
    style certs-nginx fill:#ff6;
    style nginx-external fill:#fc9;
    style nginx-right fill:#fc9;
```

The edges in this graph should not be taken too literally; they
reflect some sort of communication path or dependency relationship
between components of the chatmail server.
