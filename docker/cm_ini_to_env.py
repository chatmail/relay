#!/usr/bin/env python3
"""Convert a chatmail.ini to a Docker .env file.

Usage: python docker/cm_ini_to_env.py [chatmail.ini] [.env]

Reads the ini file, extracts all non-default key=value pairs,
and writes them as UPPER_CASE env vars suitable for docker-compose.
"""

import configparser
import sys
from pathlib import Path

# Keys that only make sense for bare-metal deploys or are handled
# separately by the Docker setup and should not appear in .env.
SKIP_KEYS = set()

# Keys that exist in .env but have a different name than the ini key.
# ini_key -> env_key
RENAMES = {}


def read_ini(path):
    """Return dict of key=value from [params] section."""
    cp = configparser.ConfigParser()
    cp.read(path)
    if not cp.has_section("params"):
        sys.exit(f"Error: {path} has no [params] section")
    return dict(cp.items("params"))


def read_defaults():
    """Return dict of default values from the ini template."""
    template = Path(__file__).resolve().parent.parent / "chatmaild/src/chatmaild/ini/chatmail.ini.f"
    if not template.exists():
        return {}
    cp = configparser.ConfigParser()
    cp.read(template)
    if not cp.has_section("params"):
        return {}
    defaults = {}
    for key, value in cp.items("params"):
        # Template placeholders like {mail_domain} aren't real defaults.
        if "{" not in value:
            defaults[key] = value
    return defaults


def ini_to_env(ini_path, only_non_default=True):
    """Yield (ENV_KEY, value) pairs from an ini file."""
    params = read_ini(ini_path)
    defaults = read_defaults() if only_non_default else {}

    for key, value in sorted(params.items()):
        if key in SKIP_KEYS:
            continue
        if only_non_default and key in defaults and value.strip() == defaults[key].strip():
            continue
        env_key = RENAMES.get(key, key.upper())
        yield env_key, value.strip()


def main():
    ini_path = sys.argv[1] if len(sys.argv) > 1 else "chatmail.ini"
    env_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not Path(ini_path).exists():
        sys.exit(f"Error: {ini_path} not found")

    lines = []
    for env_key, value in ini_to_env(ini_path):
        lines.append(f'{env_key}="{value}"')

    output = "\n".join(lines) + "\n"

    if env_path:
        Path(env_path).write_text(output)
        print(f"Wrote {len(lines)} variables to {env_path}")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
