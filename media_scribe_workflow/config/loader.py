"""
MSW Configuration Loader

設定ファイル階層:
1. defaults.yaml - グローバルデフォルト
2. templates/{template}.yaml - テンプレート固有設定
3. project.vce.json["msw"] - プロジェクト固有設定

マージ順序: defaults → template → project
"""

import json
from pathlib import Path
from typing import Any

import yaml


class ConfigLoader:
    """MSW設定ローダー"""

    def __init__(self, config_dir: Path | str | None = None):
        """
        Args:
            config_dir: 設定ディレクトリ（デフォルト: ~/.config/msw）
        """
        if config_dir is None:
            self.config_dir = Path("~/.config/msw").expanduser()
        else:
            self.config_dir = Path(config_dir).expanduser()

    def load_defaults(self) -> dict[str, Any]:
        """defaults.yaml を読み込み"""
        defaults_path = self.config_dir / "defaults.yaml"
        if not defaults_path.exists():
            return {}
        return self._load_yaml(defaults_path)

    def load_template(self, template_name: str) -> dict[str, Any]:
        """
        テンプレートを読み込み

        Args:
            template_name: テンプレート名（例: "rehearsal", "instrument_lesson"）

        Returns:
            テンプレート設定（extendsは解決済み）
        """
        template_path = self.config_dir / "templates" / f"{template_name}.yaml"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        template = self._load_yaml(template_path)

        # extends の処理
        extends = template.pop("extends", None)
        if extends == "defaults":
            # defaults とマージ
            defaults = self.load_defaults()
            return self._deep_merge(defaults, template)
        elif extends:
            # 別のテンプレートを継承（将来拡張用）
            parent = self.load_template(extends)
            return self._deep_merge(parent, template)

        return template

    def load_project_msw(self, project_path: Path | str) -> dict[str, Any]:
        """
        プロジェクトファイルから msw セクションを読み込み

        Args:
            project_path: .vce.json ファイルのパス

        Returns:
            msw セクションの内容（存在しない場合は空dict）
        """
        project_path = Path(project_path)
        if not project_path.exists():
            raise FileNotFoundError(f"Project file not found: {project_path}")

        with open(project_path, "r", encoding="utf-8") as f:
            project = json.load(f)

        return project.get("msw", {})

    def get_merged_config(self, project_path: Path | str) -> dict[str, Any]:
        """
        最終的なマージ済み設定を取得

        マージ順序:
        1. defaults.yaml
        2. templates/{template}.yaml
        3. project.vce.json["msw"]

        Args:
            project_path: .vce.json ファイルのパス

        Returns:
            マージ済み設定
        """
        # プロジェクトの msw セクションを読み込み
        project_msw = self.load_project_msw(project_path)

        # テンプレート名を取得
        template_name = project_msw.get("template")
        if not template_name:
            # テンプレート未指定の場合は defaults のみ
            defaults = self.load_defaults()
            return self._deep_merge(defaults, project_msw)

        # テンプレートを読み込み（defaults とのマージ済み）
        template_config = self.load_template(template_name)

        # プロジェクト設定をマージ
        return self._deep_merge(template_config, project_msw)

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """YAMLファイルを読み込み"""
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """
        辞書を再帰的にマージ

        Args:
            base: ベースとなる辞書
            override: 上書きする辞書

        Returns:
            マージ済み辞書
        """
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result


def expand_path(path_str: str) -> Path:
    """パス文字列を展開（~ を展開）"""
    return Path(path_str).expanduser()
