"""Versions, hashes, and download URLs for pre-built artifacts fetched during deploy."""

FILTERMAIL_VERSION = "v0.7.10"
FILTERMAIL_ARTIFACTS = {
    "x86_64": (
        f"https://github.com/chatmail/filtermail/releases/download/{FILTERMAIL_VERSION}/filtermail-x86_64",
        "c800e39e37d81c504f48dee2e61c10fcdd679c23e7ab958d6f0e6413c19d2be3",
    ),
    "aarch64": (
        f"https://github.com/chatmail/filtermail/releases/download/{FILTERMAIL_VERSION}/filtermail-aarch64",
        "eaf2a46c7c39e898bb37b82716a0a866cea5bbbc642675c78c259e0f98517ceb",
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

DOVECOT_VERSION = "2.3.21+dfsg1-3+chatmail3"
DOVECOT_SHA256 = {
    ("core", "amd64"): "8064ca9a940684007063d4a4f60ec265b364f07d26cb4a7ffec83fc775812ebe",
    ("core", "arm64"): "5f5665735a01c70fb22ac0415b3aea00d23c1301b52effab96bf92c1b1e4366c",
    ("imapd", "amd64"): "1175a1dafb755e393385306bbe109fccacd31d5177a72db16c0f0b1731a83221",
    ("imapd", "arm64"): "48399b20ab600a20eaf377f8de34eb8e2a393954e53c6636b1e37c7ea99fd8a6",
    ("lmtpd", "amd64"): "d0681cd5ae6680d13338ee2e2bad290f929cac8b62d913d842576f2413cde48e",
    ("lmtpd", "arm64"): "3ad2a4484b2fa52f33e536cb8e36d13d9a86cb5c98732d5fe0f5e4898af03de5",
    ("auth-lua", "amd64"): "d2764bd247abb6dd90ee8026cea277cb044f9ac02348abd45c692ce52a2ed6f4",
    ("auth-lua", "arm64"): "5164b74a47a70aa265097f66a7f38985ebd6c575f8432ba64122ae6267749286",
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
