[Unit]
Description=chatmail file system storage reporting job 
After=network.target

[Service]
Type=oneshot
User=vmail
ExecStart={execpath} {config_path}

