[Unit]
Description=Run Daily chatmail-expire job

[Timer]
OnCalendar=*-*-* 00:02:00
Persistent=true

[Install]
WantedBy=timers.target
