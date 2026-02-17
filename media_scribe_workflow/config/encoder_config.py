"""
encoder_config.py - エンコーダ設定ローダー

encoders.yaml からエンコーダ設定を読み込み、
ffmpeg引数を生成する。
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import yaml

from ..utils import get_platform_name


def _get_platform() -> str:
    """現在のプラットフォームを取得（utils.compatに委譲）"""
    return get_platform_name()


class EncoderConfig:
    """エンコーダ設定の読み込みと提供

    使用例:
        config = EncoderConfig()
        args = config.get_encoder_args("h264_nvenc", quality_index=1, bitrate_kbps=4000)
        encoders = config.get_available_encoders()
    """

    _instance: Optional['EncoderConfig'] = None

    def __init__(self, config_path: Optional[Path] = None):
        """初期化

        Args:
            config_path: 設定ファイルのパス。省略時はデフォルトのencoders.yamlを使用
        """
        if config_path is None:
            config_path = Path(__file__).parent / "encoders.yaml"

        self._config_path = config_path
        self._config: Dict[str, Any] = {}
        self._load_config()

    @classmethod
    def get_instance(cls) -> 'EncoderConfig':
        """シングルトンインスタンスを取得"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_config(self):
        """設定ファイルを読み込み"""
        if not self._config_path.exists():
            raise FileNotFoundError(f"Encoder config not found: {self._config_path}")

        with open(self._config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)

    def get_quality_labels(self) -> List[Dict[str, Any]]:
        """品質レベルのラベル一覧を取得

        Returns:
            [{"id": 0, "name": "High Quality", "description": "..."}, ...]
        """
        return self._config.get('quality_labels', [])

    def get_encoder_info(self, encoder_id: str) -> Optional[Dict[str, Any]]:
        """エンコーダ情報を取得

        Args:
            encoder_id: エンコーダID（例: "h264_nvenc"）

        Returns:
            エンコーダ設定辞書、存在しない場合はNone
        """
        return self._config.get('encoders', {}).get(encoder_id)

    def is_encoder_available_on_platform(self, encoder_id: str, platform: Optional[str] = None) -> bool:
        """指定エンコーダが現在のプラットフォームで利用可能か

        Args:
            encoder_id: エンコーダID
            platform: プラットフォーム（省略時は現在のプラットフォーム）

        Returns:
            利用可能ならTrue
        """
        if platform is None:
            platform = _get_platform()

        encoder = self.get_encoder_info(encoder_id)
        if not encoder:
            return False

        encoder_platform = encoder.get('platform', 'all')

        if encoder_platform == 'all':
            return True
        elif isinstance(encoder_platform, list):
            return platform in encoder_platform
        else:
            return platform == encoder_platform

    def get_platform_encoders(self, platform: Optional[str] = None) -> List[Tuple[str, str, str]]:
        """プラットフォームで利用可能なエンコーダ一覧を取得

        Args:
            platform: プラットフォーム（省略時は現在のプラットフォーム）

        Returns:
            [(encoder_id, display_name, description), ...]
        """
        if platform is None:
            platform = _get_platform()

        result = []
        for encoder_id, encoder in self._config.get('encoders', {}).items():
            if self.is_encoder_available_on_platform(encoder_id, platform):
                result.append((
                    encoder_id,
                    encoder.get('display_name', encoder_id),
                    encoder.get('description', '')
                ))

        # libx264を先頭に（CPUエンコーダはデフォルト）
        result.sort(key=lambda x: 0 if x[0] == 'libx264' else 1)
        return result

    def get_encoder_args(
        self,
        encoder_id: str,
        quality_index: int = 0,
        bitrate_kbps: int = 4000,
        crf: Optional[int] = None
    ) -> List[str]:
        """エンコーダ引数を生成

        Args:
            encoder_id: エンコーダID
            quality_index: 品質レベル（0=高画質, 1=標準, 2=高速）
            bitrate_kbps: ビットレート（kbps）
            crf: libx264用CRF値（省略時はプリセットから取得）

        Returns:
            ffmpegコマンド引数リスト
        """
        encoder = self.get_encoder_info(encoder_id)
        if not encoder:
            # フォールバック: libx264
            encoder = self.get_encoder_info('libx264')
            encoder_id = 'libx264'

        if not encoder:
            raise ValueError(f"Unknown encoder: {encoder_id}")

        # 品質プリセットを取得
        presets = encoder.get('quality_presets', {})
        preset = presets.get(quality_index, presets.get(0, {}))

        # ビットレート関連
        bitrate = f"{bitrate_kbps}k"
        maxrate = f"{int(bitrate_kbps * 1.2)}k"
        bufsize = f"{bitrate_kbps * 2}k"

        # エンコーダ別の引数を構築
        args = ['-c:v', encoder_id]

        if encoder_id == 'h264_videotoolbox':
            # VideoToolboxは-q:vをサポートしないため、ビットレート制御のみ使用
            args.extend(['-b:v', bitrate, '-maxrate', maxrate, '-bufsize', bufsize])

        elif encoder_id == 'h264_nvenc':
            args.extend(['-preset', preset.get('preset', 'p4')])
            args.extend(['-cq', str(preset.get('cq', 24))])
            args.extend(['-b:v', bitrate, '-maxrate', maxrate, '-bufsize', bufsize])

        elif encoder_id == 'h264_qsv':
            args.extend(['-preset', preset.get('preset', 'medium')])
            args.extend(['-global_quality', str(preset.get('global_quality', 26))])
            args.extend(['-b:v', bitrate, '-maxrate', maxrate, '-bufsize', bufsize])

        elif encoder_id == 'h264_amf':
            args.extend(['-quality', preset.get('quality', 'balanced')])
            qp = preset.get('qp', 24)
            args.extend(['-qp_i', str(qp), '-qp_p', str(qp)])
            args.extend(['-b:v', bitrate, '-maxrate', maxrate, '-bufsize', bufsize])

        elif encoder_id == 'h264_vaapi':
            args.extend(['-qp', str(preset.get('qp', 26))])
            args.extend(['-b:v', bitrate, '-maxrate', maxrate, '-bufsize', bufsize])

        else:  # libx264
            args.extend(['-preset', preset.get('preset', 'fast')])
            # crfが明示的に指定された場合はそれを使用
            crf_val = crf if crf is not None else preset.get('crf', 23)
            args.extend(['-crf', str(crf_val)])
            args.extend(['-maxrate', maxrate, '-bufsize', bufsize])

        # デフォルト引数を追加
        default_args = encoder.get('default_args', [])
        args.extend(default_args)

        return args


# グローバルアクセス用の関数
def get_encoder_config() -> EncoderConfig:
    """EncoderConfigのシングルトンインスタンスを取得"""
    return EncoderConfig.get_instance()
