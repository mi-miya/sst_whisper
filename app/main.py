import pystray
from PIL import Image, ImageDraw
import threading
import sys
import ctypes
import time
from pathlib import Path
from .settings import current_settings, load_settings_as_dict, save_settings
from .logger import logger
from .recorder import Recorder
from .transcriber import Transcriber
from .clipboard_win import set_text, paste_text
from .hotkey_win import HotkeyListener
from . import sounds

# States
IDLE = "IDLE"
RECORDING = "RECORDING"
TRANSCRIBING = "TRANSCRIBING"

VK_ESCAPE = 0x1B

MUTEX_NAME = "LocalWhisperDictation_Mutex"
ERROR_ALREADY_EXISTS = 183

_mutex_handle = None


def ensure_single_instance():
    """二重起動を防止する。既に起動中ならメッセージを表示して終了する。"""
    global _mutex_handle
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(
            0, "音声入力ツールは既に起動しています。\nタスクトレイまたは画面上のアイコンを確認してください。",
            "音声入力ツール", 0x40)
        sys.exit(0)


def release_single_instance():
    """再起動時に新プロセスがミューテックスを取得できるよう解放する。"""
    global _mutex_handle
    if _mutex_handle:
        ctypes.windll.kernel32.CloseHandle(_mutex_handle)
        _mutex_handle = None

class MainApp:
    def __init__(self):
        self.state = IDLE
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.icon = None
        self.hotkey_thread = None
        self.gui = None # Tkinter widget reference

        # Lock for state transition
        self.lock = threading.Lock()

        # バックグラウンドでWhisperモデルをウォームアップ
        self._start_warmup()

    def _start_warmup(self):
        """バックグラウンドでWhisperモデルをウォームアップ開始"""
        def warmup_task():
            logger.info("Starting background warmup...")
            success = self.transcriber.warmup()
            if success:
                logger.info("Background warmup completed successfully")
            else:
                logger.warning("Background warmup failed or skipped")

        warmup_thread = threading.Thread(target=warmup_task, daemon=True)
        warmup_thread.start()

    def create_image(self, color):
        # Generate generic icon
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color)
        dc = ImageDraw.Draw(image)
        # Draw a circle/mic shape
        dc.ellipse((16, 16, 48, 48), fill=(255, 255, 255))
        return image

    def setup_tray(self):
        self.icon = pystray.Icon(
            "LocalDictation",
            self.create_image("green"),
            menu=pystray.Menu(
                pystray.MenuItem("Exit", self.exit_app)
            )
        )

    def update_icon_state(self):
        color = "green"
        if self.state == RECORDING:
            color = "red"
        elif self.state == TRANSCRIBING:
            color = "yellow"

        # Update Tray
        if self.icon:
            try:
                self.icon.icon = self.create_image(color)
                self.icon.title = f"Local Whisper: {self.state}"
            except Exception as e:
                logger.error(f"Failed to update tray: {e}")

        # Update Floating GUI
        if self.gui:
            self.gui.set_state(self.state, color)

    def on_hotkey(self):
        """ホットキーコールバック"""
        # 状態を確認してアクションを決定（ロックを最小限に保持）
        with self.lock:
            current_state = self.state
            if current_state == TRANSCRIBING:
                logger.info("Ignored hotkey during transcription")
                return

        # ロックの外で各アクションを実行（デッドロック回避）
        if current_state == IDLE:
            self.start_recording()
        elif current_state == RECORDING:
            self.stop_and_transcribe()

    def start_recording(self):
        logger.info("Start Recording")
        sounds.play_start()

        self.recorder.start()
        self.state = RECORDING
        self.update_icon_state()

        # Start monitoring for Esc key
        threading.Thread(target=self._monitor_cancellation, daemon=True).start()

    def _monitor_cancellation(self):
        logger.info("Started cancellation monitor")
        while self.state == RECORDING:
            # Check if Esc is pressed
            # GetAsyncKeyState returns short (16-bit). MSB set means key is down.
            if ctypes.windll.user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                logger.info("Esc pressed! Cancelling...")
                self.cancel_recording()
                break
            time.sleep(0.05) # Poll every 50ms

    def cancel_recording(self):
        with self.lock:
            if self.state != RECORDING:
                return

            logger.info("Cancelling recording...")
            self.state = IDLE
            self.update_icon_state()

        self.recorder.stop(discard=True)
        sounds.play_cancel()

    def stop_and_transcribe(self):
        logger.info("Hotkey: Stop Recording")
        # 先に状態を遷移させてから、停止処理（配列結合・無音判定）ごと
        # ワーカースレッドに逃がす。ホットキーの message loop を
        # ブロックしないようにするため
        with self.lock:
            self.state = TRANSCRIBING
            self.update_icon_state()

        t = threading.Thread(target=self._transcribe_task)
        t.start()

    def _transcribe_task(self):
        try:
            audio = self.recorder.stop()
            if audio is None:
                # Failed to record or short or silent
                logger.info("Recording was silent or invalid. Returning to IDLE.")
                sounds.play_cancel()
                return

            # モデルロード中なら待機中であることをGUIに表示
            if not self.transcriber.is_ready():
                logger.info("Model still loading, showing LOADING state...")
                if self.gui:
                    self.gui.set_state("LOADING", "orange")
                self.transcriber.wait_until_ready()
                self.update_icon_state()

            text = self.transcriber.transcribe(audio)
            if text:
                set_text(text)
                if current_settings.auto_paste:
                    paste_text()
                sounds.play_finish()
            else:
                sounds.play_cancel()
        finally:
            with self.lock:
                self.state = IDLE
                self.update_icon_state()

    def run_hotkey(self):
        logger.info(f"App starting. Hotkey: {current_settings.hotkey}")
        # Start hotkey listener
        self.hotkey_thread = HotkeyListener(current_settings.hotkey, self.on_hotkey, hotkey_id=1)
        self.hotkey_thread.start()

    def run_tray(self):
        self.setup_tray()
        self.update_icon_state()
        logger.info("System tray initialized.")
        self.icon.run()

    def show_settings_dialog(self):
        """設定ダイアログを表示"""
        if not self.gui:
            return

        # 遅延インポート
        from .settings_dialog import SettingsDialog

        current_dict = load_settings_as_dict()

        def on_save(new_settings: dict):
            if save_settings(new_settings):
                logger.info("Settings saved. Restarting application...")
                self.restart_app()

        SettingsDialog(self.gui.root, current_dict, on_save)

    def restart_app(self):
        """アプリケーションを再起動"""
        logger.info("Restarting application...")

        # 現在のプロセスを終了して再起動
        python = sys.executable
        script = sys.argv[0]

        # リソースをクリーンアップ
        self.transcriber.cleanup()
        if self.icon:
            try:
                self.icon.stop()
            except:
                pass
        if self.hotkey_thread:
            try:
                self.hotkey_thread.stop()
            except:
                pass

        # 新しいプロセスがミューテックスを取得できるよう先に解放する
        release_single_instance()

        # 新しいプロセスを起動
        import subprocess
        subprocess.Popen([python, "-m", "app.main"], cwd=str(Path.cwd()))

        # 現在のプロセスを終了
        sys.exit(0)

    def exit_app(self, icon, item):
        logger.info("Exit requested")
        self.transcriber.cleanup()
        if self.icon:
            self.icon.stop()
        if self.hotkey_thread:
            self.hotkey_thread.stop()
        sys.exit(0)

import signal
import time
from .gui import FloatingWidget


def check_first_run() -> bool:
    """初回起動かどうかをチェック"""
    config_path = Path.cwd() / "config.json"
    return not config_path.exists()


def run_setup_wizard_and_start():
    """セットアップウィザードを実行してからアプリを起動"""
    from .setup_wizard import SetupWizard

    def on_complete(settings):
        logger.info("Setup wizard completed, starting app...")
        # アプリを再起動（設定を反映するため）
        release_single_instance()
        import subprocess
        subprocess.Popen([sys.executable, "-m", "app.main"], cwd=str(Path.cwd()))
        sys.exit(0)

    def on_cancel():
        logger.info("Setup wizard cancelled")
        sys.exit(0)

    wizard = SetupWizard(on_complete, on_cancel)
    wizard.run()


if __name__ == "__main__":
    # 二重起動チェック
    ensure_single_instance()

    # 初回起動チェック
    if check_first_run():
        logger.info("First run detected, starting setup wizard...")
        run_setup_wizard_and_start()
    else:
        app = MainApp()

        # Initialize GUI
        app.gui = FloatingWidget(
            on_click_callback=app.on_hotkey,
            on_exit_callback=lambda: app.exit_app(None, None),
            on_settings_callback=app.show_settings_dialog
        )

        # Override exit to close GUI too
        original_exit = app.exit_app
        def exit_wrapper(icon, item):
            logger.info("Exit wrapper called")
            if app.gui:
                app.gui.quit()
            original_exit(icon, item)

        app.exit_app = exit_wrapper

        # Handle Ctrl+C
        def signal_handler(sig, frame):
            logger.info("Ctrl+C detected")
            exit_wrapper(None, None)

        signal.signal(signal.SIGINT, signal_handler)

        # Run Tray in background thread
        tray_thread = threading.Thread(target=app.run_tray, daemon=True)
        tray_thread.start()

        # Run Hotkey in background thread (MainApp.run logic split)
        app.run_hotkey()

        # Run GUI on Main Thread (Blocking)
        logger.info("Starting GUI...")
        try:
            app.gui.run()
        except KeyboardInterrupt:
            signal_handler(None, None)
