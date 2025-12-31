#!/usr/bin/python
# -*- coding: utf-8 -*-
import json
from pathlib import Path
from typing import Tuple


class CgsRuleMgr:
    RULE_FILENAME = ".cgsRule.json"
    _exist_flags = {}
    _cached_rules = {}

    @classmethod
    def _get_rule_file(cls, sv_path: Path) -> Path:
        return sv_path / cls.RULE_FILENAME

    @classmethod
    def exists(cls, sv_path: Path) -> bool:
        if sv_path in cls._exist_flags:
            return cls._exist_flags[sv_path]
        result = cls._get_rule_file(sv_path).exists()
        cls._exist_flags[sv_path] = result
        return result

    @classmethod
    def create(cls, sv_path: Path, conf_dh) -> bool:
        if cls.exists(sv_path):
            cls.create = lambda _, __: None
            return False
        try:
            rule_data = {"downloaded_handle": conf_dh}
            with open(cls._get_rule_file(sv_path), 'w', encoding='utf-8') as f:
                json.dump(rule_data, f, ensure_ascii=False, indent=2)
            key = str(sv_path)
            cls._exist_flags[key] = True
            cls._cached_rules[key] = rule_data
            return True
        except Exception:
            return False

    @classmethod
    def get_download_handle(cls, _conf) -> str:
        sv_path = _conf.sv_path
        if not cls.exists(sv_path):
            return _conf.downloaded_handle
        if sv_path in cls._cached_rules:
            return cls._cached_rules[sv_path].get("downloaded_handle", "-")
        try:
            with open(cls._get_rule_file(sv_path), 'r', encoding='utf-8') as f:
                rule_data = json.load(f)
            cls._cached_rules[sv_path] = rule_data
            return rule_data.get("downloaded_handle", "-")
        except Exception:
            return _conf.downloaded_handle

    @classmethod
    def validate(cls, sv_path: Path, new_handle: str) -> Tuple[bool, str]:
        if not cls.exists(sv_path):
            return True, ""
        if sv_path in cls._cached_rules:
            rule_data = cls._cached_rules[sv_path]
        else:
            try:
                with open(cls._get_rule_file(sv_path), 'r', encoding='utf-8') as f:
                    rule_data = json.load(f)
                cls._cached_rules[sv_path] = rule_data
            except Exception:
                return True, ""
        stored_handle = rule_data.get("downloaded_handle", "-")
        if stored_handle != new_handle:
            error_msg = f"「{sv_path}」 已存后处理规则：'{stored_handle}'\n请更换储存目录或删除 「{sv_path}/.cgsRule.json」"
            return False, error_msg
        return True, ""
