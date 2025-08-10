This diagram shows components of the chatmail server:

```mermaid
graph LR;
    cmdeploy --> sshd;
    cron --> expunge;
    cron --> acmetool;
    cron --> chatmail-metrics;
    chatmail-metrics --> /var/www/html;
    acmetool --> certs;
    acmetool --> acmetool-redirector;
    acmetool-redirector --> certs;
    nginx --> /var/www/html;
    nginx --> certs;
    nginx --> newemail.py;
    nginx --> |465|postfix;
    nginx --> autoconfig.xml;
    nginx --> |993|dovecot;
    autoconfig.xml --> postfix;
    autoconfig.xml --> dovecot;
    postfix --> certs;
    postfix --> /home/vmail/mail;
    postfix --> |10080,10081|filtermail;
    postfix --> echobot;
    postfix --> |doveauth.socket|doveauth;
    dovecot --> certs;
    dovecot --> |doveauth.socket|doveauth;
    dovecot --> /home/vmail/mail;
    dovecot --> |metadata.socket|chatmail-metadata;
    doveauth --> /home/vmail/mail;
    expunge --> /home/vmail/mail;
    chatmail-metadata --> iroh-relay;
```

(Arrows in this diagram do not have a specific formal meaning; they
signify "depends on", or "uses", or "sends data to", or just "relates
to".)
