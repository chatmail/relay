[Unit]
Description=A wrapper for the TURN server
After=network.target

[Service]
Type=simple
Restart=always
ExecStart=/usr/local/bin/chatmail-turn --realm {mail_domain}

[Install]
WantedBy=multi-user.target
