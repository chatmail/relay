import requests

from cmdeploy.genqr import gen_qr_png_data


def test_gen_qr_png_data(maildomain):
    data = gen_qr_png_data(maildomain)
    assert data


def test_fastcgi_working(maildomain, chatmail_config):
    url = f"https://{maildomain}/new"
    print(url)
    verify = chatmail_config.tls_cert != "self"
    res = requests.post(url, verify=verify)
    assert maildomain in res.json().get("email")
    assert len(res.json().get("password")) > chatmail_config.password_min_length


def test_newemail_configure(maildomain, rpc, chatmail_config):
    """Test configuring accounts by scanning a QR code works."""
    url = f"DCACCOUNT:https://{maildomain}/new"
    for i in range(3):
        account_id = rpc.add_account()
        if chatmail_config.tls_cert == "self":
            # deltachat core's rustls rejects self-signed HTTPS certs during
            # set_config_from_qr, so fetch credentials via requests instead
            res = requests.post(f"https://{maildomain}/new", verify=False)
            data = res.json()
            rpc.add_or_update_transport(account_id, {
                "addr": data["email"],
                "password": data["password"],
                "imapServer": maildomain,
                "smtpServer": maildomain,
                "certificateChecks": "acceptInvalidCertificates",
            })
        else:
            rpc.set_config_from_qr(account_id, url)
        rpc.configure(account_id)
