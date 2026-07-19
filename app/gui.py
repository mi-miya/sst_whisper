import tkinter as tk
from tkinter import ttk, messagebox
import threading
import sys
import os
from .logger import logger

class FloatingWidget:
    def __init__(self, on_click_callback, on_exit_callback, on_settings_callback=None):
        self.root = tk.Tk()
        self.on_click_callback = on_click_callback
        self.on_exit_callback = on_exit_callback
        self.on_settings_callback = on_settings_callback

        # Window configuration
        self.root.overrideredirect(True)  # Frameless
        self.root.attributes('-topmost', True)  # Always on top
        self.root.attributes('-alpha', 0.8)  # Transparency
        self.root.geometry("60x60+100+100")  # Size and initial position
        self.root.configure(bg='black')

        # Make generic window transparent color (chroma key) if needed,
        # but for now we just use a dark bg.
        # self.root.wm_attributes("-transparentcolor", "white")

        self.canvas = tk.Canvas(self.root, width=60, height=60, bg='black', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)

        # Draw circle button
        self.circle = self.canvas.create_oval(5, 5, 55, 55, fill='green', outline='white', width=2)

        # Draw "MIC" text or icon representation
        self.text_id = self.canvas.create_text(30, 30, text="MIC", fill="white", font=("Arial", 10, "bold"))

        # Bind events
        # Use ButtonRelease for click to distinguish from drag
        self.canvas.bind("<ButtonPress-1>", self.start_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.do_move)
        self.canvas.bind("<Button-3>", self.show_context_menu) # Right click

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="設定", command=self.show_settings)
        self.menu.add_separator()
        self.menu.add_command(label="終了", command=self.exit_app)

        self.start_x = 0
        self.start_y = 0
        self.win_x = 0
        self.win_y = 0
        self.has_moved = False

    def start_move(self, event):
        self.start_x = event.x_root
        self.start_y = event.y_root
        self.win_x = self.root.winfo_x()
        self.win_y = self.root.winfo_y()
        self.has_moved = False

    def do_move(self, event):
        # Calculate delta from screen coordinates to avoid jitter
        dx = event.x_root - self.start_x
        dy = event.y_root - self.start_y

        if abs(dx) > 3 or abs(dy) > 3:
            self.has_moved = True
            new_x = self.win_x + dx
            new_y = self.win_y + dy
            self.root.geometry(f"+{new_x}+{new_y}")

    def on_click(self, event):
        # Only trigger click if we haven't dragged properly
        if not self.has_moved:
            if self.on_click_callback:
                threading.Thread(target=self.on_click_callback).start()

    def show_context_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

    def show_settings(self):
        """設定ダイアログを表示"""
        if self.on_settings_callback:
            self.on_settings_callback()

    def exit_app(self):
        if self.on_exit_callback:
            self.on_exit_callback()

    def set_state(self, state, color):
        # This must be called from the main thread
        # We can use self.root.after to ensure thread safety
        self.root.after(0, lambda: self._update_ui(state, color))

    def _update_ui(self, state, color):
        try:
            self.canvas.itemconfig(self.circle, fill=color)
            # Maybe update text too
            short_text = "MIC"
            if state == "RECORDING": short_text = "REC"
            elif state == "TRANSCRIBING": short_text = "..."
            elif state == "LOADING": short_text = "LOAD"
            self.canvas.itemconfig(self.text_id, text=short_text)
        except Exception as e:
            logger.error(f"GUI Error: {e}")

    def run(self):
        self.root.mainloop()

    def quit(self):
        self.root.quit()
