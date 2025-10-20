[Unit]
Description=Run Daily Chatmail fsreport Job

[Timer]
OnCalendar=*-*-* 08:02:00
Persistent=true

[Install]
WantedBy=timers.target
