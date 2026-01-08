"""
UI共通スタイル定義

アプリケーション全体で使用する色定数とスタイルシート生成関数を集約。
"""


class Colors:
    """アプリケーション共通カラー定数"""

    # Primary (Blue)
    PRIMARY = "#3b82f6"
    PRIMARY_HOVER = "#2563eb"
    PRIMARY_DISABLED = "#1e3a5f"

    # Danger (Red)
    DANGER = "#dc2626"
    DANGER_HOVER = "#ef4444"
    DANGER_PRESSED = "#b91c1c"
    DANGER_DISABLED = "#7f1d1d"

    # Background
    BACKGROUND_DARK = "#1a1a1a"
    BACKGROUND_MEDIUM = "#2d2d2d"
    BACKGROUND_HOVER = "#363636"

    # Border
    BORDER = "#3a3a3a"

    # Text
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#f0f0f0"
    TEXT_DISABLED = "#666666"


class ButtonStyles:
    """ボタンスタイル生成"""

    @staticmethod
    def primary() -> str:
        """プライマリボタン（青）"""
        return f"""
            QPushButton {{
                background: {Colors.PRIMARY};
                color: {Colors.TEXT_PRIMARY};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {Colors.PRIMARY_HOVER};
            }}
            QPushButton:disabled {{
                background: {Colors.PRIMARY_DISABLED};
                color: {Colors.TEXT_DISABLED};
            }}
        """

    @staticmethod
    def secondary() -> str:
        """セカンダリボタン（グレー枠）"""
        return f"""
            QPushButton {{
                background: {Colors.BACKGROUND_MEDIUM};
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background: {Colors.BACKGROUND_HOVER};
            }}
        """

    @staticmethod
    def primary_compact() -> str:
        """プライマリボタン（青・コンパクト）"""
        return f"""
            QPushButton {{
                background: {Colors.PRIMARY};
                color: {Colors.TEXT_PRIMARY};
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {Colors.PRIMARY_HOVER};
            }}
            QPushButton:disabled {{
                background: {Colors.PRIMARY_DISABLED};
                color: {Colors.TEXT_DISABLED};
            }}
        """

    @staticmethod
    def secondary_compact() -> str:
        """セカンダリボタン（グレー枠・コンパクト）"""
        return f"""
            QPushButton {{
                background: {Colors.BACKGROUND_MEDIUM};
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background: {Colors.BACKGROUND_HOVER};
            }}
        """

    @staticmethod
    def danger() -> str:
        """危険ボタン（赤）"""
        return f"""
            QPushButton {{
                background: {Colors.DANGER};
                color: {Colors.TEXT_PRIMARY};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {Colors.DANGER_HOVER};
            }}
            QPushButton:pressed {{
                background: {Colors.DANGER_PRESSED};
            }}
            QPushButton:disabled {{
                background: {Colors.DANGER_DISABLED};
                color: {Colors.TEXT_DISABLED};
            }}
        """

    @staticmethod
    def danger_compact() -> str:
        """危険ボタン（赤・コンパクト）"""
        return f"""
            QPushButton {{
                background: {Colors.DANGER};
                color: {Colors.TEXT_PRIMARY};
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {Colors.DANGER_HOVER};
            }}
            QPushButton:pressed {{
                background: {Colors.DANGER_PRESSED};
            }}
            QPushButton:disabled {{
                background: {Colors.DANGER_DISABLED};
                color: {Colors.TEXT_DISABLED};
            }}
        """
