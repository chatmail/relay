[Unit]
Description=A wrapper for the TURN server
After=network.target

[Service]
Type=simple
Restart=always
ExecStart={execpath} {mail_domain}

[Install]
WantedBy=multi-user.target
