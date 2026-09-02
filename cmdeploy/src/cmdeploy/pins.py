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

# distro-neutral base version, as committed in chatmail/dovecot debian/changelog
DOVECOT_VERSION = "2.3.21+dfsg1-3+chatmail2"
DOVECOT_SHA256 = {
    ("amd64", 12, "auth-lua"): "ef1b8e1db45147a74b48d63125bd61b2cc2f250e1006656ba1c58b9c12f5cde6",
    ("arm64", 12, "auth-lua"): "c1a06ee9374439893e397ba3b0cacf532a733290c184f4f30ea39df8699be329",
    ("amd64", 13, "auth-lua"): "6c0946d2516efcbcaa09a27df9b8ea701861cce270d71941056b3c69831a5ea2",
    ("arm64", 13, "auth-lua"): "5e6c9cfe47f7f3b8aa0d68a3e607161b6abaee1ad696cb1419e997b3099b2985",
    ("amd64", 12, "core"): "ac3977264d9b9a6fcec53fd3f5cdd2a79ca8aa0324de530c07e535008540826e",
    ("arm64", 12, "core"): "21626c9c9b52cbdcf1a17b5c09e3c4043e69aa371bf83cc2fcb3b7ddaecdc109",
    ("amd64", 13, "core"): "47c242ef23c17e700ac19d52d82c9fdb2ebd757d8beb3a7f6781d2de59f87bd0",
    ("arm64", 13, "core"): "c14c53f112c875f698c4cb6e5870c605cd0a9dd98d35a66e94ceb1827f8020a3",
    ("amd64", 12, "imapd"): "92a7ab5fc7dc32886a0c34404f919f1335d397b48c467e0c1ef77e56978f60ea",
    ("arm64", 12, "imapd"): "9369fd566fec4df109ef23debf34ea0417ae85beb29cbe7de619d4d1f31b120c",
    ("amd64", 13, "imapd"): "e38cc1266455f937ed62f971ea859c47e1a99247841ed0ad946963b524cfdbc5",
    ("arm64", 13, "imapd"): "11d97dabf23171b37f8b1335dfdb81d408f8b95391aea6d4066aecc9fde01dfe",
    ("amd64", 12, "lmtpd"): "dc3de473789969f7dd3504ac8783da5e42a446d2d7a305a4e9d7081a6dfe71ab",
    ("arm64", 12, "lmtpd"): "ae2cbd6c5c43f6d8e2172997b055448f4c79238e2f99cd9ab9200a7d9f548908",
    ("amd64", 13, "lmtpd"): "833b243e28c7baff141ecf37456e310f5d836e7944a3b9f2fe5074adf0d6a418",
    ("arm64", 13, "lmtpd"): "55af47a121ba7e23966b20ddaab2dff7feba4b34677864e045e31a702afa180d",
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
