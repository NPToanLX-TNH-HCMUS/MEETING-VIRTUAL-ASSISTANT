from tkinter import *
import sounddevice as sd
from scipy.io.wavfile import write, read
import time
import wavio as wv


def main():
    root = Tk()
    
    root.title("MEETING ASSISITANT")
    root.minsize(width=500, height=500)

    recording = None
    freq = 44100
    start_time = 0
    MAX_TIME = 300
    has_show_time = False

    time_label = Label(root, text="Time: 0.0s")
    time_label.pack(pady=10)

    def show_time():
        if has_show_time == False:
            return
        duration = time.monotonic() - start_time
        time_label.config(text=f"Time: {duration:.1f}s")
        if duration < MAX_TIME:
            root.after(100, show_time)

    def stop_record():
        nonlocal recording, start_time, has_show_time
        if recording is None:
            return
        duration = time.monotonic() - start_time
        sd.stop()

        frames = min(int(duration * freq), len(recording))
        time_label.config(text=f"Time: {frames / freq:.1f}s")
        recording2 = recording[:frames]
        write("record.wav", freq, recording2)
        recording = None
        has_show_time = False

    def record():
        nonlocal recording, start_time, has_show_time
        if recording is not None:
            return
        
        recording = sd.rec(MAX_TIME * freq, samplerate=freq, channels=1, dtype="int16")
        start_time = time.monotonic()
        has_show_time = True
        show_time()

    def play():
        freq, audio = read("record.wav")
        sd.play(audio, samplerate=freq)

    record_button = Button(root, text="Record", command=record).pack(pady=10)
    stop_button = Button(root, text="Stop", command=stop_record).pack(pady=10)
    play_button = Button(root, text="Play", command=play).pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    main()