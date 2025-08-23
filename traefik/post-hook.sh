CERTS_DIR=${CERTS_DIR:-"/data/letsencrypt/certs"}

echo "CERTS_DIR: $CERTS_DIR"

for dir in "$CERTS_DIR"/*/; do
    echo "Processing: $dir"
    cd "$dir"
    if [ -f "certificate.crt" ]; then
        ln -sf certificate.crt fullchain
    fi
    if [ -f "privatekey.key" ]; then
        ln -sf privatekey.key privkey
    fi
    cd -
done
