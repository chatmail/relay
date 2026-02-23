# Watch the TLS certificate file for changes.
# When the cert is updated (e.g. renewed by an external process),
# this triggers tls-cert-reload.service to reload the affected services.
#
# NOTE: changes to the certificates are not detected if they cross bind-mount boundaries. 
# After cert renewal, you must then trigger the reload explicitly:
#   systemctl start tls-cert-reload.service
[Unit]
Description=Watch TLS certificate for changes

[Path]
PathChanged={cert_path}

[Install]
WantedBy=multi-user.target
