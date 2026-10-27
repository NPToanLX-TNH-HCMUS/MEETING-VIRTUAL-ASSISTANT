import tkinter as tk
from tkinter import filedialog

from ..audio.recorder import Recorder
from ..document.document import Document
from .config import (
    WindowConfig, ButtonConfig, EditorConfig,
    open_button, save_button, save_as_button,
    record_button, stop_button, play_button,
)

FILE_TYPES = [("Text", "*.txt"), ("Markdown", "*.md")]
DEFAULT_EXTENSION = ".txt"
REFRESH_MS = 100

class MainWindow(tk.Tk):
    def __init__(self, path=None):
        super().__init__()
        window_config = WindowConfig()
        self.title(window_config.title)
        self.geometry(window_config.size)

        self._document = Document()
        self._recorder = Recorder()
        self._make_buttons()
        self._make_audio_bar()
        self._make_editor()

        if path:
            self._show_file(path)

    def _make_buttons(self):
        toolbar = tk.Frame(self)
        toolbar.pack()
        buttons = [
            (open_button, self._open_file),
            (save_button, self._save_file),
            (save_as_button, self._save_file_as),
        ]
        for button_config, command in buttons:
            tk.Button(toolbar,
                      text=button_config.text,
                      bg=button_config.bg,
                      padx=button_config.padx,
                      pady=button_config.pady,
                      command=command).pack(side="left")

    def _make_audio_bar(self):
        audio_bar = tk.Frame(self)
        audio_bar.pack()
        self._time_label = tk.Label(audio_bar, text="Time: 0.0s")
        self._time_label.pack(side="left", padx=12)
        buttons = [
            (record_button, self._record),
            (stop_button, self._stop),
            (play_button, self._play),
        ]
        for button_config, command in buttons:
            tk.Button(audio_bar,
                      text=button_config.text,
                      bg=button_config.bg,
                      padx=button_config.padx,
                      pady=button_config.pady,
                      command=command).pack(side="left")

    def _make_editor(self):
        editor_config = EditorConfig()
        self._editor = tk.Text(self, font=editor_config.font, wrap=editor_config.wrap)
        self._editor.pack(fill="both", expand=True)

    def _get_text(self):
        # "end-1c" drops the newline tkinter always appends, so saving doesn't grow the file
        return self._editor.get("1.0", "end-1c")

    def _show_file(self, path):
        text = self._document.load(path)
        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", text)

    def _open_file(self):
        path = filedialog.askopenfilename(filetypes=FILE_TYPES)
        if path:
            self._show_file(path)

    def _save_file(self):
        if self._document.has_path:
            self._document.save(self._get_text())
        else:
            self._save_file_as()

    def _save_file_as(self):
        path = filedialog.asksaveasfilename(filetypes=FILE_TYPES,
                                            defaultextension=DEFAULT_EXTENSION)
        if path:
            self._document.save(self._get_text(), path)

    def _show_time(self):
        if not self._recorder.is_recording:
            return
        self._time_label.config(text=f"Time: {self._recorder.elapsed:.1f}s")
        self.after(REFRESH_MS, self._show_time)

    def _record(self):
        if self._recorder.is_recording:
            return
        self._recorder.start()
        self._show_time()

    def _stop(self):
        duration = self._recorder.stop()
        self._time_label.config(text=f"Time: {duration:.1f}s")

    def _play(self):
        self._recorder.play()
