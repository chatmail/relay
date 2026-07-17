"""Detect whether the system is at its limits."""

import logging

import psutil

MB = 1024 * 1024


def read_value(getter):
    try:
        return getter()
    except Exception as e:
        logging.warning("ignoring unreadable system limit: %s", e)
        return None


def has_sufficient_resources(config):
    """Return False if load, memory or disk exceeds a configured limit."""
    load = read_value(lambda: psutil.getloadavg()[0])
    mem = read_value(lambda: psutil.virtual_memory().available // MB)
    disk = read_value(lambda: psutil.disk_usage(str(config.mailboxes_dir)).free // MB)
    if load is not None and load > config.max_load_1m:
        msg = f"load avg {load:.2f} > {config.max_load_1m:.2f}"
    elif mem is not None and mem < config.min_available_memory_mb:
        msg = f"available memory {mem}MB < {config.min_available_memory_mb}MB"
    elif disk is not None and disk < config.min_free_disk_space_mb:
        msg = f"free disk {disk}MB < {config.min_free_disk_space_mb}MB"
    else:
        return True
    logging.warning("registration rejected: %s", msg)
    return False
