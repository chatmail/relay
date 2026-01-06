[Unit]
Description=Chatmail dict proxy for IMAP METADATA

[Service]
ExecStart={execpath} /run/chatmail-metadata/metadata.socket {config_path}
Restart=always
RestartSec=30
User=vmail
RuntimeDirectory=chatmail-metadata
RuntimeDirectoryMode=0755
UMask=0022

[Install]
WantedBy=multi-user.target
