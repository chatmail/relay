"""Test rendering of the Postfix main.cf template."""

import jinja2

from cmdeploy.basedeploy import get_resource


def render_main_cf(config):
    template = jinja2.Template(get_resource("postfix/main.cf.j2").read_text())
    return template.render(
        config=config,
        disable_ipv6=config.disable_ipv6,
        config_dir="/etc/postfix",
        ca_path="/etc/ssl/certs",
    )


def test_main_cf_without_transport_maps(example_config):
    assert "transport_maps" not in render_main_cf(example_config)


def test_main_cf_with_transport_maps(make_config):
    config = make_config(
        "chat.example.org",
        {"postfix_transport_maps": "texthash:/etc/postfix/transport"},
    )
    lines = render_main_cf(config).splitlines()
    assert "transport_maps = texthash:/etc/postfix/transport" in lines
