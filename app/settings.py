import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from .logger import logger

class Settings(BaseModel):
    hotkey: str = "<ctrl>+<alt>+<shift>+h"
    language: str = "ja"
    model_path: str = "./models/ggml-small.bin"
    whisper_cli_path: str = "./bin/whisper-cli.exe"
    auto_paste: bool = False
    keep_trailing_newline: bool = False
    temp_dir: str = ""
    audio_device: Optional[int] = None
    sample_rate: int = 16000
    n_gpu_layers: int = 0
    initial_prompt: str = ""
    sound_enabled: bool = True

    def resolve_paths(self):
        # Resolve relative paths
        base = Path.cwd()
        self.model_path = str((base / self.model_path).resolve())
        self.whisper_cli_path = str((base / self.whisper_cli_path).resolve())
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
        settings = Settings(**data)
        settings.resolve_paths()
        logger.info("Settings loaded successfully")
        return settings
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        return Settings()

# Global settings instance
current_settings = load_settings()
