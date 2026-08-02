# -*- coding: utf-8 -*-
"""Gestion de la configuration JSON."""

import json
import os

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "config.json"
)


def load_config(path=None):
    path = path or DEFAULT_CONFIG_PATH
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_config(config, path=None):
    path = path or DEFAULT_CONFIG_PATH
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
