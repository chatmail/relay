[Unit]
Description=chatmail file system storage reporting job 
After=network.target

[Service]
Type=oneshot
User=vmail
ExecStart=/usr/local/lib/chatmaild/venv/bin/chatmail-fsreport /usr/local/lib/chatmaild/chatmail.ini 

