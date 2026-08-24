[Unit]
Description=Chatmail HTTP authentication service for dovecot

[Service]
ExecStart={execpath} {config_path}
Restart=always
RestartSec=5
User=vmail
UMask=0077

[Install]
WantedBy=multi-user.target
