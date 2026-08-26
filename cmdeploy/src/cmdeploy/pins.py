"""Versions, hashes, and download URLs for pre-built artifacts fetched during deploy."""

FILTERMAIL_VERSION = "v0.7.4"
FILTERMAIL_ARTIFACTS = {
    "x86_64": (
        f"https://github.com/chatmail/filtermail/releases/download/{FILTERMAIL_VERSION}/filtermail-x86_64",
        "484cb8dff083134aefba9fce4a6b7ef4784a0f0e28e5108ecf8bb9e58a44fd2c",
    ),
    "aarch64": (
        f"https://github.com/chatmail/filtermail/releases/download/{FILTERMAIL_VERSION}/filtermail-aarch64",
        "66aa0ca2ca9add7a12d92883d76f8786384092adfde24a3d3a1d0b1f30d23a9e",
    ),
    "mtail": (
        f"https://raw.githubusercontent.com/chatmail/filtermail/{FILTERMAIL_VERSION}/contrib/filtermail.mtail",
        "948f688bb89ad47e6eb0fc8fa107e201a689f5adc264ff926be487a2a8562b51",
    ),
}

MTAIL_VERSION = "3.4.9"
MTAIL_ARTIFACTS = {
    "x86_64": (
        f"https://github.com/jaqx0r/mtail/releases/download/v{MTAIL_VERSION}/mtail_{MTAIL_VERSION}_linux_amd64.tar.gz",
        "55f64a87f71955bb871c724b4aadf19fe9d854e6327196919c7fe44943427eab",
    ),
    "aarch64": (
        f"https://github.com/jaqx0r/mtail/releases/download/v{MTAIL_VERSION}/mtail_{MTAIL_VERSION}_linux_arm64.tar.gz",
        "e0a2b66b372ca257d7daeb7ba10f9233a2192a1f9057618fccc6be5c854a2a3c",
    ),
}

DOVECOT_VERSION = "2.3.21+dfsg1-3"
DOVECOT_SHA256 = {
    ("core", "amd64"): "dd060706f52a306fa863d874717210b9fe10536c824afe1790eec247ded5b27d",
    ("core", "arm64"): "e7548e8a82929722e973629ecc40fcfa886894cef3db88f23535149e7f730dc9",
    ("imapd", "amd64"): "8d8dc6fc00bbb6cdb25d345844f41ce2f1c53f764b79a838eb2a03103eebfa86",
    ("imapd", "arm64"): "178fa877ddd5df9930e8308b518f4b07df10e759050725f8217a0c1fb3fd707f",
    ("lmtpd", "amd64"): "2f69ba5e35363de50962d42cccbfe4ed8495265044e244007d7ccddad77513ab",
    ("lmtpd", "arm64"): "89f52fb36524f5877a177dff4a713ba771fd3f91f22ed0af7238d495e143b38f",
}
TURN_VERSION = "v0.4"
TURN_ARTIFACTS = {
    "x86_64": (
        f"https://github.com/chatmail/chatmail-turn/releases/download/{TURN_VERSION}/chatmail-turn-x86_64-linux",
        "1ec1f5c50122165e858a5a91bcba9037a28aa8cb8b64b8db570aa457c6141a8a",
    ),
    "aarch64": (
        f"https://github.com/chatmail/chatmail-turn/releases/download/{TURN_VERSION}/chatmail-turn-aarch64-linux",
        "0fb3e792419494e21ecad536464929dba706bb2c88884ed8f1788141d26fc756",
    ),
}

IROH_VERSION = "v0.35.0"
IROH_ARTIFACTS = {
    "x86_64": (
        f"https://github.com/n0-computer/iroh/releases/download/{IROH_VERSION}/iroh-relay-{IROH_VERSION}-x86_64-unknown-linux-musl.tar.gz",
        "45c81199dbd70f8c4c30fef7f3b9727ca6e3cea8f2831333eeaf8aa71bf0fac1",
    ),
    "aarch64": (
        f"https://github.com/n0-computer/iroh/releases/download/{IROH_VERSION}/iroh-relay-{IROH_VERSION}-aarch64-unknown-linux-musl.tar.gz",
        "f8ef27631fac213b3ef668d02acd5b3e215292746a3fc71d90c63115446008b1",
    ),
}
