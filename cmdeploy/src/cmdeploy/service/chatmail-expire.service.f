[Unit]
Description=chatmail mail storage expiration job
After=network.target

[Service]
Type=oneshot
User=vmail
ExecStart={execpath} {config_path} -v --remove

