#!/bin/bash
set -e

# 1. Update and install dependencies
echo "--- Installing dependencies ---"
sudo apt update
sudo apt install -y git curl wget python3-dev gcc python3 nano sed

# 1.1 Install uv
export PATH="$HOME/.local/bin:/root/.local/bin:$PATH"
if ! command -v uv > /dev/null 2>&1; then
    if [ -f "/root/.local/bin/uv" ]; then
        export PATH="/root/.local/bin:$PATH"
    elif [ -f "$HOME/.local/bin/uv" ]; then
        export PATH="$HOME/.local/bin:$PATH"
    fi
fi

if ! command -v uv > /dev/null 2>&1; then
    echo "--- Installing uv ---"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Ensure uv is in PATH for the current script
    export PATH="$HOME/.local/bin:/root/.local/bin:$PATH"
fi

# 2. Clone the repository if not already in it
if [ ! -d "relay-ir" ]; then
    echo "--- Cloning relay-ir ---"
    git clone https://github.com/omidz4t/relay-ir.git
    cd relay-ir
else
    echo "--- relay-ir directory already exists, entering ---"
    cd relay-ir
fi

# 3. Initialize environment
echo "--- Initializing environment ---"
./scripts/initenv.sh

# 4. Ask for domain and email
read -p "Enter your mail domain (e.g. example.com): " MAIL_DOMAIN
read -p "Enter your email for ACME/Let's Encrypt: " ACME_EMAIL

# 5. Initialize configuration
echo "--- Initializing chatmail configuration ---"
./scripts/cmdeploy init "$MAIL_DOMAIN" || true


# 6. Modify chatmail.ini with specific requirements
echo "--- Customizing chatmail.ini ---"
# Using sed to update the values. We use -i to edit in-place.
# Note: some lines might be commented or have different defaults, 
# so we'll try to replace existing keys or add them if they don't exist.

update_config() {
    local key=$1
    local value=$2
    if grep -q "^$key =" chatmail.ini; then
        sed -i "s/^$key =.*/$key = $value/" chatmail.ini
    else
        # If it's commented out or missing, we append it after [params] or at the end
        sed -i "/\[params\]/a $key = $value" chatmail.ini
    fi
}

update_config "max_mailbox_size" "500M"
update_config "max_message_size" "31457280"
update_config "delete_mails_after" "20"
update_config "username_min_length" "9"
update_config "username_max_length" "9"
update_config "password_min_length" "9"
update_config "acme_email" "$ACME_EMAIL"

echo "--- Current chatmail.ini configuration ---"
cat chatmail.ini

# 7. Run deployment
echo "--- Starting deployment ---"
# Adding /usr/sbin and /sbin to PATH as requested to ensure sysctl and other tools are found
export PATH=$PATH:/usr/sbin:/sbin
sudo -E PATH="$PATH" scripts/cmdeploy run --ssh-host @local --skip-dns-check

echo "--- Deployment finished ---"
