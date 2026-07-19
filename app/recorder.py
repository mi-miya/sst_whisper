# 遅延インポート用（メモリ最適化）
# sounddevice, numpy, scipy は録音開始時に初めてインポートされる
from .settings import current_settings
from .logger import logger
from .error_handler import show_error

# Whisperが要求するサンプルレート
WHISPER_SAMPLE_RATE = 16000

# グローバル変数（遅延インポート後に設定）
_sd = None
_np = None
_wav = None


def _lazy_import():
    """numpy, sounddevice, scipy を遅延インポート"""
    global _sd, _np, _wav
    if _sd is None:
        import sounddevice as sd
        import numpy as np
        import scipy.io.wavfile as wav
        _sd = sd
        _np = np
        _wav = wav
        logger.info("Audio libraries loaded (lazy import)")
    return _sd, _np, _wav


class Recorder:
    def __init__(self):
        self.frames = []
        self.stream = None
        self.sample_rate = current_settings.sample_rate
        self.channels = 1
        self.is_recording = False

    def callback(self, indata, frames, time, status):
        if status:
            logger.warning(f"Audio status: {status}")
        self.frames.append(indata.copy())

    def start(self):
        if self.is_recording:
            logger.warning("Attempted to start recording while already recording")
            return

        try:
            # 遅延インポート
            sd, np, wav = _lazy_import()

            self.frames = []

            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=self.callback,
                dtype='int16',
                device=current_settings.audio_device
            )
            self.stream.start()
            self.is_recording = True
            logger.info("Recording started")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.is_recording = False
            show_error("recording_failed", str(e))

    def stop(self, discard=False):
        """録音を停止し、Whisperにそのまま渡せる float32 / 16kHz の
        numpy 配列を返す。破棄・無音・失敗時は None を返す。

        WAVファイルへの書き出しは行わない（ディスクI/Oとデコードの
        往復を省き、文字起こし開始までのレイテンシを削減するため）。
        """
        if not self.is_recording:
            return None

        try:
            # 遅延インポート
            sd, np, wav = _lazy_import()

            self.stream.stop()
            self.stream.close()
            self.is_recording = False
            logger.info("Recording stopped")

            frames = self.frames
            self.frames = []

            if discard:
                logger.info("Recording discarded")
                return None

            if not frames:
                logger.warning("No frames recorded")
                return None

            recording = np.concatenate(frames, axis=0)

            # --- VAD Check ---
            # Calculate RMS amplitude
            # frames are int16, so values are between -32768 and 32767
            # We want to check if the audio is mostly silence

            # Simple RMS of the entire clip
            float_data = recording.astype(np.float32)
            rms = np.sqrt(np.mean(float_data**2))
            max_amp = np.max(np.abs(float_data))

            logger.info(f"Audio Stats: RMS={rms:.2f}, Max={max_amp:.2f}")

            # 最大振幅チェック
            if max_amp < current_settings.silence_threshold:
                logger.info(f"Audio ignored: Max amplitude too low ({max_amp:.2f} < {current_settings.silence_threshold})")
                return None

            # RMSチェック：環境ノイズレベルを除外（人の声のRMSは通常600以上、キーボード音は200-300程度）
            noise_floor = current_settings.noise_floor
            if rms < noise_floor:
                logger.info(f"Audio ignored: RMS too low ({rms:.2f} < {noise_floor}), likely background noise or keyboard")
                return None

            # -----------------

            # int16 -> float32 [-1.0, 1.0] に正規化し、1次元モノラルにする
            audio = (float_data / 32768.0).reshape(-1)

            # Whisperは16kHz前提のため、異なる場合はリサンプリング
            if self.sample_rate != WHISPER_SAMPLE_RATE:
                from scipy.signal import resample_poly
                audio = resample_poly(audio, WHISPER_SAMPLE_RATE, self.sample_rate).astype(np.float32)
                logger.info(f"Resampled audio from {self.sample_rate}Hz to {WHISPER_SAMPLE_RATE}Hz")

            return audio
        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            return None
