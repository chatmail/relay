[Unit]
Description=Chatmail echo bot for testing it works
Requires=dovecot.service

[Service]
ExecStart={execpath} {config_path}
Environment="PATH={remote_venv_dir}:$PATH"
Restart=always
RestartSec=30

User=echobot
Group=echobot

# Create /var/lib/echobot
StateDirectory=echobot

# Create /run/echobot
#
# echobot stores /run/echobot/password
# with a password there, which doveauth then reads.
RuntimeDirectory=echobot

WorkingDirectory=/var/lib/echobot

# Apply security restrictions suggested by
#   systemd-analyze security echobot.service
CapabilityBoundingSet=
LockPersonality=true
MemoryDenyWriteExecute=true
NoNewPrivileges=true
PrivateDevices=true
PrivateMounts=true
PrivateTmp=true

# We need to know about doveauth user to give it access to /run/echobot/password
PrivateUsers=false

ProtectClock=true
ProtectControlGroups=true
ProtectHostname=true
ProtectKernelLogs=true
ProtectKernelModules=true
ProtectKernelTunables=true
ProtectProc=noaccess

# Should be "strict", but we currently write /accounts folder in a protected path
ProtectSystem=full

RemoveIPC=true
RestrictAddressFamilies=AF_INET AF_INET6
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true
SystemCallArchitectures=native
SystemCallFilter=~@clock
SystemCallFilter=~@cpu-emulation
SystemCallFilter=~@debug
SystemCallFilter=~@module
SystemCallFilter=~@mount
SystemCallFilter=~@obsolete
SystemCallFilter=~@raw-io
SystemCallFilter=~@reboot
SystemCallFilter=~@resources
SystemCallFilter=~@swap
UMask=0077

[Install]
WantedBy=multi-user.target
