import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, ConfigDict
from .logger import logger


# 共有定数: モデル、言語、デバイス、計算精度
AVAILABLE_MODELS = [
    ("large-v3-turbo", "高精度・高速・推奨", "~800 MB"),
    ("large-v3", "最高精度", "~1.5 GB"),
    ("medium", "バランス型", "~800 MB"),
    ("small", "高速・軽量", "~250 MB"),
    ("base", "最軽量", "~75 MB"),
]

LANGUAGES = [
    ("日本語", "ja"),
    ("英語", "en"),
    ("中国語", "zh"),
    ("韓国語", "ko"),
    ("自動検出", "auto"),
]

DEVICE_OPTIONS = [
    ("auto (自動検出)", "auto"),
    ("cuda:0 (GPU)", "cuda:0"),
    ("cpu (CPUのみ)", "cpu"),
]

COMPUTE_TYPE_OPTIONS = [
    ("float16 (高速・推奨)", "float16"),
    ("int8_float16 (最速・省メモリ)", "int8_float16"),
    ("float32 (互換性重視)", "float32"),
]

# 非推奨フィールド（保存時に自動削除）
_DEPRECATED_KEYS = ['whisper_cli_path', 'model_path', 'n_gpu_layers', 'best_of', 'carry_initial_prompt', 'batch_size', 'chunk_length_s']

# 旧モデルパス/HuggingFace IDから faster-whisper モデル名へのマッピング
MODEL_MIGRATION_MAP = {
    "ggml-large-v3-turbo": "large-v3-turbo",
    "ggml-large-v3": "large-v3",
    "ggml-large": "large-v3",
    "ggml-medium": "medium",
    "ggml-small": "small",
    "ggml-base": "base",
    "ggml-tiny": "tiny",
}

HF_MODEL_MIGRATION_MAP = {
    "openai/whisper-large-v3-turbo": "large-v3-turbo",
    "openai/whisper-large-v3": "large-v3",
    "openai/whisper-medium": "medium",
    "openai/whisper-small": "small",
    "openai/whisper-base": "base",
    "openai/whisper-tiny": "tiny",
}


def migrate_config(data: dict) -> dict:
    """旧形式の config.json を新形式にマイグレーションする"""
    migrated = data.copy()

    # model_path → model_name (whisper.cpp 形式からの移行)
    if 'model_path' in migrated and 'model_name' not in migrated:
        old_path = migrated.pop('model_path', '')
        filename = Path(old_path).stem  # e.g. "ggml-large-v3-turbo"
        model_name = "large-v3-turbo"  # デフォルト
        for key, value in MODEL_MIGRATION_MAP.items():
            if key in filename:
                model_name = value
                break
        migrated['model_name'] = model_name
        logger.info(f"Migrated model_path '{old_path}' -> model_name '{model_name}'")

    # HuggingFace モデルID → faster-whisper 短縮名
    if 'model_name' in migrated and migrated['model_name'] in HF_MODEL_MIGRATION_MAP:
        old_name = migrated['model_name']
        migrated['model_name'] = HF_MODEL_MIGRATION_MAP[old_name]
        logger.info(f"Migrated HF model '{old_name}' -> '{migrated['model_name']}'")

    # n_gpu_layers → device
    if 'n_gpu_layers' in migrated and 'device' not in migrated:
        gpu_layers = migrated.pop('n_gpu_layers', 0)
        migrated['device'] = 'auto' if gpu_layers > 0 else 'cpu'
        logger.info(f"Migrated n_gpu_layers={gpu_layers} -> device='{migrated['device']}'")

    # 不要になったフィールドを削除
    for old_key in _DEPRECATED_KEYS:
        if old_key in migrated:
            migrated.pop(old_key)
            logger.info(f"Removed deprecated config key: {old_key}")

    return migrated


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hotkey: str = "<ctrl>+<alt>+<shift>+j"
    language: str = "ja"
    model_name: str = "large-v3-turbo"
    device: str = "auto"
    compute_type: str = "float16"
    auto_paste: bool = True
    keep_trailing_newline: bool = False
    temp_dir: str = ""
    audio_device: Optional[int] = None
    sample_rate: int = 16000
    initial_prompt: str = "日本語の音声認識を行います。以下の文章は日本語で、日常会話やビジネス文書の内容です。句読点や改行を適切に挿入してください。専門用語や固有名詞は正確に認識してください。"
    sound_enabled: bool = True
    beam_size: int = 1
    temperature: float = 0.0
    silence_threshold: int = 500  # 発話/無音の判定閾値
    noise_floor: int = 200  # この振幅以下の音は無視
    widget_x: Optional[int] = None  # フローティングアイコンの保存位置 (未設定なら画面左下)
    widget_y: Optional[int] = None

    def resolve_paths(self):
        # Resolve relative paths
        if self.temp_dir:
            self.temp_dir = str(Path(self.temp_dir).resolve())

def load_settings(path: str = "config.json") -> Settings:
    config_path = Path(path)
    if not config_path.exists():
        logger.warning(f"Config file {path} not found. Using defaults.")
        return Settings()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 旧形式からのマイグレーション
        data = migrate_config(data)
        settings = Settings(**data)
        settings.resolve_paths()
        logger.info("Settings loaded successfully")
        return settings
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        return Settings()


def save_settings(settings_dict: dict, path: str = "config.json") -> bool:
    """設定をJSONファイルに保存する

    Args:
        settings_dict: 保存する設定の辞書
        path: 保存先のパス

    Returns:
        成功した場合はTrue、失敗した場合はFalse
    """
    config_path = Path(path)

    try:
        save_dict = {k: v for k, v in settings_dict.items() if k not in _DEPRECATED_KEYS}

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(save_dict, f, ensure_ascii=False, indent=2)

        logger.info(f"Settings saved to {path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return False


def load_settings_as_dict(path: str = "config.json") -> dict:
    """設定を辞書として読み込む（ダイアログ用）"""
    config_path = Path(path)
    if not config_path.exists():
        # デフォルト設定を返す
        return Settings().model_dump()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # マイグレーションを適用して返す
        return migrate_config(data)
    except Exception as e:
        logger.error(f"Failed to load settings as dict: {e}")
        return Settings().model_dump()


# Global settings instance
current_settings = load_settings()
