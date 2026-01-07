#!/bin/bash
set -e

# 0. Ask for domain and email at the beginning
get_config_value() {
    local key=$1
    local file=$2
    if [ -f "$file" ]; then
        grep "^$key =" "$file" | head -n 1 | cut -d'=' -f2 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
    fi
}

INI_FILE="chatmail.ini"
if [ -d "relay-ir" ]; then
    INI_FILE="relay-ir/chatmail.ini"
fi

if [ -z "$MAIL_DOMAIN" ]; then
    MAIL_DOMAIN=$(get_config_value "mail_domain" "$INI_FILE")
fi

if [ -z "$ACME_EMAIL" ]; then
    ACME_EMAIL=$(get_config_value "acme_email" "$INI_FILE")
fi

if [ -z "$MAIL_DOMAIN" ]; then
    read -p "Enter your mail domain (e.g. example.com): " MAIL_DOMAIN < /dev/tty
fi

if [ -z "$ACME_EMAIL" ]; then
    read -p "Enter your email for ACME/Let's Encrypt: " ACME_EMAIL < /dev/tty
fi

# 1. Update and install dependencies
echo "--- Installing dependencies ---"
# Ubuntu 24.04 and others might need universe for python3-dev
if command -v add-apt-repository > /dev/null 2>&1; then
    sudo add-apt-repository -y universe
fi

# We use a timeout for the lock to handle automatic updates running in the background
sudo apt-get update -o DPkg::Lock::Timeout=120
sudo apt-get install -y -o DPkg::Lock::Timeout=120 git curl wget python3-dev build-essential python3 nano sed

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
    # Check if we are already inside a relay-ir directory
    if [ -f "scripts/cmdeploy" ]; then
        echo "--- Already inside relay-ir directory ---"
        git pull
    else
        echo "--- Cloning relay-ir ---"
        git clone https://github.com/omidz4t/relay-ir.git
        cd relay-ir
    fi
else
    echo "--- relay-ir directory already exists, updating ---"
    cd relay-ir
    git pull
fi

# 3. Initialize environment
echo "--- Initializing environment ---"
./scripts/initenv.sh

# 4. Ask for domain and email (already handled at the beginning)


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
