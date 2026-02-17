/* dclogin profile generator for self-signed chatmail relays.
 * Fetches credentials from /new and generates a dclogin: QR code.
 * Requires qrcode-svg.min.js to be loaded first.
 */
(function() {
    function generateProfile() {
        fetch('/new')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var url = data.dclogin_url;
                var link = document.getElementById('dclogin-link');
                link.href = url;
                var container = document.getElementById('qr-code');
                var qr = new QRCode({content: url, width: 300, height: 300, padding: 1, join: true});
                container.innerHTML = '<a href="' + url + '">' + qr.svg() + '</a>';
            });
    }
    generateProfile();
})();
