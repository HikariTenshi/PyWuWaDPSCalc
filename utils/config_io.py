"""
Config I/O
=====================================

by @HikariTenshi

This module loads data from a JSON configuration file.
"""

import json

def load_config(config_path):
    """
    Load the configuration from a JSON file.

    :param config_path: The path to the configuration file.
    :type config_path: str
    :return: The configuration as a dictionary.
    :rtype: dict
    """
    with open(config_path, "r") as config_file:
        return json.load(config_file)