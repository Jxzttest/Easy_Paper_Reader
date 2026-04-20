#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pathlib
import yaml
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

_CONFIG_PATH = pathlib.Path(__file__).parent.parent.parent / "config" / "model_config.yaml"


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # 展开环境变量占位符 ${VAR}
    import re
    def expand(val):
        if isinstance(val, str):
            return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), val)
        return val

    def walk(obj):
        if isinstance(obj, dict):
            return {k: walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [walk(i) for i in obj]
        return expand(obj)

    return walk(raw)


_config: Optional[dict] = None


def get_config() -> dict:
    global _config
    if _config is None:
        _config = _load_config()
    return _config
