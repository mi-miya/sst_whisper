import subprocess
import os
from pathlib import Path
from .settings import current_settings
from .logger import logger

class Transcriber:
    def __init__(self):
        self.cli_path = current_settings.whisper_cli_path
        self.model_path = current_settings.model_path

    def transcribe(self, audio_file: str) -> str:
        if not os.path.exists(self.cli_path):
             logger.error(f"Whisper CLI not found at {self.cli_path}")
             return ""

        if not os.path.exists(self.model_path):
             logger.error(f"Model file not found at {self.model_path}")
             return ""

        # Build command: whisper-cli -m model -f wav -l lang -nt
        # -nt: no timestamps (output just text)
        cmd = [
            self.cli_path,
            "-m", self.model_path,
            "-f", audio_file,
            "-l", current_settings.language,
            "-nt"
        ]

        if current_settings.initial_prompt:
             cmd.extend(["--prompt", current_settings.initial_prompt])

        # Note: Current version of whisper-cli detects GPU automatically if DLLs are present.
        # -ngl option is invalid for this binary version.

        logger.info(f"Running transcription: {' '.join(cmd)}")

        try:
            # Run subprocess
            # startupinfo to hide console window on Windows
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                startupinfo=startupinfo
            )

            if result.returncode != 0:
                logger.error(f"Transcription process failed with code {result.returncode}")
                logger.error(f"Stderr: {result.stderr}")
                return ""

            # Retrieve output.
            # whisper-cli typically outputs to stdout with -nt.
            text = result.stdout.strip()

            # Some versions might output logs to stdout or stderr.
            # If text is empty, check stderr just in case or if output file was generated.
            # For now assume stdout has the text.

            if not text:
                logger.warning("Transcription returned empty text")
                if result.stderr:
                    logger.warning(f"Stderr content: {result.stderr}")
            else:
                logger.info(f"Transcribed length: {len(text)}")

            return text

        except Exception as e:
            logger.error(f"Transcription execution error: {e}")
            return ""
