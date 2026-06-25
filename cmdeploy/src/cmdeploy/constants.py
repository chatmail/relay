CHATMAILD_PATHS = {
    "base_dir": "/usr/local/lib/chatmaild",
    "dist_dir": "/usr/local/lib/chatmaild/dist",
    "venv_dir": "/usr/local/lib/chatmaild/venv",
    "config": "/usr/local/lib/chatmaild/chatmail.ini",
}

BINARY_PATHS = {
    "chatmail_turn": "/usr/local/bin/chatmail-turn",
    "filtermail": "/usr/local/bin/filtermail",
    "iroh_relay": "/usr/local/bin/iroh-relay",
    "mtail": "/usr/local/bin/mtail",
}

CONFIG_DIRS = {
    "dkimkeys": "/etc/dkimkeys",
    "dovecot": "/etc/dovecot",
    "mtail": "/etc/mtail",
    "nginx": "/etc/nginx",
    "opendkim": "/etc/opendkim",
    "postfix": "/etc/postfix",
    "unbound": "/etc/unbound",
}

CONFIG_FILES = {
    "apt_install_recommends": "/etc/apt/apt.conf.d/00InstallRecommends",
    "apt_obs_keyring": "/etc/apt/keyrings/obs-home-deltachat.gpg",
    "apt_pin_dovecot": "/etc/apt/preferences.d/pin-dovecot",
    "chatmail_nocreate": "/etc/chatmail-nocreate",
    "chatmail_version": "/etc/chatmail-version",
    "cron_acmetool": "/etc/cron.d/acmetool",
    "cron_chatmail_metrics": "/etc/cron.d/chatmail-metrics",
    "cron_expunge": "/etc/cron.d/expunge",
    "dovecot_auth": "/etc/dovecot/auth.conf",
    "dovecot_conf": "/etc/dovecot/dovecot.conf",
    "dovecot_push_notification": "/etc/dovecot/push_notification.lua",
    "iroh_relay": "/etc/iroh-relay.toml",
    "journald": "/etc/systemd/journald.conf",
    "mailname": "/etc/mailname",
    "mtail_program": "/etc/mtail/delivered_mail.mtail",
    "mtasts_daemon": "/etc/mta-sts-daemon.yml",
    "nginx_conf": "/etc/nginx/nginx.conf",
    "opendkim_conf": "/etc/opendkim.conf",
    "policy_rc_d": "/usr/sbin/policy-rc.d",
    "postfix_lmtp_header_cleanup": "/etc/postfix/lmtp_header_cleanup",
    "postfix_login_map": "/etc/postfix/login_map",
    "postfix_main": "/etc/postfix/main.cf",
    "postfix_master": "/etc/postfix/master.cf",
    "postfix_smtp_tls_policy_map": "/etc/postfix/smtp_tls_policy_map",
    "postfix_smtp_tls_policy_map_db": "/etc/postfix/smtp_tls_policy_map.db",
    "postfix_submission_header_cleanup": "/etc/postfix/submission_header_cleanup",
    "systemd_dovecot_restart": "/etc/systemd/system/dovecot.service.d/10_restart.conf",
    "systemd_mtasts_daemon": "/etc/systemd/system/mta-sts-daemon.service",
    "systemd_opendkim_restart": "/etc/systemd/system/opendkim.service.d/10-prevent-memory-leak.conf",
    "systemd_postfix_restart": "/etc/systemd/system/postfix@.service.d/10_restart.conf",
    "unbound_chatmail": "/etc/unbound/unbound.conf.d/chatmail.conf",
}

WEB_PATHS = {
    "html_dir": "/var/www/html",
    "autoconfig": "/var/www/html/.well-known/autoconfig/mail/config-v1.1.xml",
    "mta_sts": "/var/www/html/.well-known/mta-sts.txt",
    "metrics": "/var/www/html/metrics",
    "newemail_cgi": "/usr/lib/cgi-bin/newemail.py",
}

ACME_PATHS = {
    "etc_dir": "/etc/acme",
    "var_dir": "/var/lib/acme",
    "hook_nginx": "/etc/acme/hooks/nginx",
    "legacy_hook_nginx": "/usr/lib/acme/hooks/nginx",
    "responses": "/var/lib/acme/conf/responses",
    "target": "/var/lib/acme/conf/target",
    "desired_dir": "/var/lib/acme/desired",
}

TLS_PATHS = {
    "self_cert": "/etc/ssl/certs/mailserver.pem",
    "self_key": "/etc/ssl/private/mailserver.key",
}

STATE_DIRS = {
    "from_cmdeploy": "/root/from-cmdeploy",
    "postfix_mta_sts_resolver": "/usr/local/lib/postfix-mta-sts-resolver",
    "var_lib_dovecot": "/var/lib/dovecot",
    "var_lib_nginx": "/var/lib/nginx",
    "var_lib_postfix": "/var/lib/postfix",
    "var_lib_unbound": "/var/lib/unbound",
    "var_log_nginx": "/var/log/nginx",
    "var_spool_postfix": "/var/spool/postfix",
}
