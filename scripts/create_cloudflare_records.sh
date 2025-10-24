#!/bin/bash
# go to https://dash.cloudflare.com/profile/api-tokens
# "create token" -> "Edit zone DNS"
## optionaly: rename token
## set your zone 
# "continue to summary" -> "create token"
# copy your created token

CLOUDFLARE_API_KEY=${CLOUDFLARE_API_KEY}
ZONE_ID=${ZONE_ID}

CHATMAIL_FULL_DNS_NAME=${CHATMAIL_FULL_DNS_NAME}
CHATMAIL_PUBLIC_IP=${CHATMAIL_PUBLIC_IP}

IPV6_ENABLED=${IPV6_ENABLED:-false}
CHATMAIL_PUBLIC_IPv6=${CHATMAIL_PUBLIC_IPv6}

#####################
# why 'proxied' is 'false'?
# I suppose that if Cloudflare is blocked in a country, clients cannot use Deltachat without a VPN.
#####################
PROXIED=${PROXIED:-"false"}

check_variables() {
    required_vars=(
    CLOUDFLARE_API_KEY
    ZONE_ID
    CHATMAIL_FULL_DNS_NAME
    CHATMAIL_PUBLIC_IP
    )

    missing_vars=()

    for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
    done

    if [ ${#missing_vars[@]} -ne 0 ]; then
    echo "❌ Error: this variables not set or empty:"
    for var in "${missing_vars[@]}"; do
        echo "  - $var"
    done
    echo "Please execute command 'export var_name=\"var_value\"' and restart script."
    exit 1
    fi
}


create_record() {
    local data=$1
    curl https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer ${CLOUDFLARE_API_KEY}" \
    -d "$1"
}

generate_post_data_a_aaaa_record()
{
    local name=$1
    local type=${2:-"A"}
    cat <<EOF
{
    "name": "${name}",
    "ttl": 3600,
    "type": "${type}",
    "comment": "",
    "content": "${CHATMAIL_PUBLIC_IP}",
    "proxied": ${PROXIED}
}
EOF
}

generate_post_data_cname_record()
{
    local name=$1
    cat <<EOF
{
    "name": "${name}",
    "ttl": 3600,
    "type": "CNAME",
    "comment": "",
    "content": "${CHATMAIL_FULL_DNS_NAME}",
    "proxied": ${PROXIED}
}
EOF
}

generate_post_data_mx_record()
{
    local name=$1
    cat <<EOF
{
    "name": "${name}",
    "ttl": 120,
    "type": "MX",
    "comment": "",
    "content": "${CHATMAIL_FULL_DNS_NAME}",
    "priority": 10,
    "proxied": ${PROXIED}
}
EOF
}

generate_post_data_txt_record()
{
    local name=$1
    local content=$2
    cat <<EOF
{
    "name": "${name}",
    "ttl": 120,
    "type": "TXT",
    "comment": "",
    "content": "$content",
    "proxied": ${PROXIED}
}
EOF
}

generate_post_data_srv_record()
{
    local name=$1
    local port=$2
    cat <<EOF
{
    "name": "${name}",
    "ttl": 120,
    "type": "SRV",
    "comment": "",
    "data": {
        "port": $port,
        "priority": 0,
        "target": "${CHATMAIL_FULL_DNS_NAME}",
        "weight": 1
    },
    "proxied": ${PROXIED}
}
EOF
}

check_variables

# A records
create_record "$(generate_post_data_a_record "$CHATMAIL_FULL_DNS_NAME" "A")"
create_record "$(generate_post_data_a_record "*.$CHATMAIL_FULL_DNS_NAME" "A")"

# AAAA records
if [ $IPV6_ENABLED = true ]; then # note: I don't have an IPv6 address, so this part hasn't been tested!
    create_record "$(generate_post_data_a_record "$CHATMAIL_FULL_DNS_NAME" "AAAA")"
    # create_record "$(generate_post_data_a_record "*.$CHATMAIL_FULL_DNS_NAME" "AAAA")"
fi

# CNAME records
create_record "$(generate_post_data_cname_record "mta-sts.$CHATMAIL_FULL_DNS_NAME")"
create_record "$(generate_post_data_cname_record "www.$CHATMAIL_FULL_DNS_NAME")"

# MX records
create_record "$(generate_post_data_mx_record "$CHATMAIL_FULL_DNS_NAME")"

# TXT records
create_record "$(generate_post_data_txt_record "$CHATMAIL_FULL_DNS_NAME" '\"v=spf1 a ~all\"')"
create_record "$(generate_post_data_txt_record "_dmarc.$CHATMAIL_FULL_DNS_NAME" '\"v=DMARC1;p=reject;adkim=s;aspf=s\"')"
create_record "$(generate_post_data_txt_record "_adsp._domainkey.$CHATMAIL_FULL_DNS_NAME" '\"dkim=discardable\"')"
create_record "$(generate_post_data_txt_record "opendkim._domainkey.$CHATMAIL_FULL_DNS_NAME" '\"v=DKIM1;k=rsa;p=;s=email;t=s\"')"
create_record "$(generate_post_data_txt_record "_mta-sts.$CHATMAIL_FULL_DNS_NAME" '\"v=STSv1; id='"$(date +"%Y%m%d%H%M")"'\"')"

# SRV records
create_record "$(generate_post_data_srv_record "_imap._tcp.$CHATMAIL_FULL_DNS_NAME" "143")"
create_record "$(generate_post_data_srv_record "_imaps._tcp.$CHATMAIL_FULL_DNS_NAME" "993")"
create_record "$(generate_post_data_srv_record "_submission._tcp.$CHATMAIL_FULL_DNS_NAME" "587")"
create_record "$(generate_post_data_srv_record "_submissions._tcp.$CHATMAIL_FULL_DNS_NAME" "465")"
