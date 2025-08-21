[Unit]
Description=A wrapper for the TURN server
After=network.target

[Service]
Type=simple
Restart=always
ExecStart=/usr/local/bin/chatmail-turn --realm {mail_domain} --socket /run/chatmail-turn/turn.socket

# Create /run/chatmail-turn
RuntimeDirectory=chatmail-turn
User=vmail
Group=vmail

[Install]
WantedBy=multi-user.target
