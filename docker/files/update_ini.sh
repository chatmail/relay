#!/bin/bash
set -eo pipefail

INI_FILE="${INI_FILE:-chatmail.ini}"

if [ ! -f "$INI_FILE" ]; then
    echo "Error: file $INI_FILE not found." >&2
    exit 1
fi

TMP_FILE="$(mktemp)"

convert_to_bytes() {
    local value="$1"
    if [[ "$value" =~ ^([0-9]+)([KkMmGgTt])$ ]]; then
        local num="${BASH_REMATCH[1]}"
        local unit="${BASH_REMATCH[2]}"
        case "$unit" in
            [Kk]) echo $((num * 1024)) ;;
            [Mm]) echo $((num * 1024 * 1024)) ;;
            [Gg]) echo $((num * 1024 * 1024 * 1024)) ;;
            [Tt]) echo $((num * 1024 * 1024 * 1024 * 1024)) ;;
        esac
    elif [[ "$value" =~ ^[0-9]+$ ]]; then
        echo "$value"
    else
        echo "Error: incorrect size format: $value." >&2
        return 1
    fi
}

process_specific_params() {
    local key=$1
    local value=$2
    local destination_file=$3

    if [[ "$key" == "max_message_size" ]]; then
        converted=$(convert_to_bytes "$value") || exit 1
        if grep -q -e "## .* = .* bytes" "$destination_file"; then 
            sed "s|## .* = .* bytes|## $value = $converted bytes|g" "$destination_file";
        else
            echo "## $value = $converted bytes"  >> "$destination_file"
        fi
        echo "$key = $converted" >> "$destination_file"
    else
        echo "$key = $value" >> "$destination_file"
    fi
}

while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*#.* || "$line" =~ ^[[:space:]]*$ ]]; then
        echo "$line" >> "$TMP_FILE"
        continue
    fi

    if [[ "$line" =~ ^([a-z0-9_]+)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
        key="${BASH_REMATCH[1]}"
        current_value="${BASH_REMATCH[2]}"
        env_var_name=$(echo "$key" | tr 'a-z' 'A-Z')
        env_value="${!env_var_name}"

        if [[ -n "$env_value" ]]; then
            process_specific_params "$key" "$env_value" "$TMP_FILE"
        else
            echo "$line" >> "$TMP_FILE"
        fi
    else
        echo "$line" >> "$TMP_FILE"
    fi
done < "$INI_FILE"

PERMS=$(stat -c %a "$INI_FILE")
OWNER=$(stat -c %u "$INI_FILE")
GROUP=$(stat -c %g "$INI_FILE")

chmod "$PERMS" "$TMP_FILE"
chown "$OWNER":"$GROUP" "$TMP_FILE"

mv "$TMP_FILE" "$INI_FILE"
