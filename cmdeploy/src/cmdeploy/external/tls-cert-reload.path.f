# Watch the TLS certificate file for changes.
# When the cert is updated (e.g. renewed by an external process),
# this triggers tls-cert-reload.service to restart the affected services.
[Unit]
Description=Watch TLS certificate for changes

[Path]
PathChanged={cert_path}

[Install]
WantedBy=multi-user.target
