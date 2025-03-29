[Unit]
Description=Incoming Chatmail Postfix before queue filter 

[Service]
ExecStart={execpath} {config_path} incoming
Restart=always
RestartSec=30
User=filtermail

[Install]
WantedBy=multi-user.target

