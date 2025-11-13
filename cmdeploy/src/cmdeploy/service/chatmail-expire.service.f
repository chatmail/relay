[Unit]
Description=chatmail mail storage expiration job
After=network.target

[Service]
Type=oneshot
User=vmail
ExecStart=/usr/local/lib/chatmaild/venv/bin/chatmail-expire /usr/local/lib/chatmaild/chatmail.ini -v --remove

