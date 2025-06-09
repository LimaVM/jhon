import os
import subprocess
import tempfile
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk


@dataclass
class Track:
    name: str
    start: int
    end: int | None = None


class TrackParser:
    @staticmethod
    def time_to_seconds(t: str) -> int:
        parts = [int(p) for p in t.strip().split(":")]
        if len(parts) == 3:
            h, m, s = parts
        elif len(parts) == 2:
            h = 0
            m, s = parts
        else:
            raise ValueError(f"Tempo invalido: {t}")
        return h * 3600 + m * 60 + s

    @staticmethod
    def seconds_to_str(sec: int) -> str:
        h, r = divmod(sec, 3600)
        m, s = divmod(r, 60)
        if h:
            return f"{h:02}:{m:02}:{s:02}"
        return f"{m:02}:{s:02}"

    @classmethod
    def parse(cls, text: str) -> list[Track]:
        tracks: list[Track] = []
        for line in text.strip().splitlines():
            if not line.strip():
                continue
            try:
                time_part, name_part = line.split(maxsplit=1)
                start = cls.time_to_seconds(time_part)
                tracks.append(Track(name=name_part.strip(), start=start))
            except Exception:
                continue
        tracks.sort(key=lambda t: t.start)
        for i in range(len(tracks) - 1):
            tracks[i].end = tracks[i + 1].start
        return tracks


class DownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("YouTube Downloader")
        self.geometry("600x500")
        self.create_widgets()

    def create_widgets(self) -> None:
        main = ttk.Frame(self)
        main.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        url_frame = ttk.LabelFrame(main, text="URL do vídeo")
        url_frame.pack(fill=tk.X, pady=5)
        self.url_var = tk.StringVar()
        ttk.Entry(url_frame, textvariable=self.url_var).pack(fill=tk.X, padx=5, pady=5)

        track_frame = ttk.LabelFrame(main, text="Lista de Faixas (ex: 00:00 Intro)")
        track_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.track_text = tk.Text(track_frame, height=10)
        self.track_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        opts = ttk.Frame(main)
        opts.pack(fill=tk.X)
        self.format_var = tk.StringVar(value="mp3")
        ttk.Radiobutton(opts, text="MP3", variable=self.format_var, value="mp3").pack(side=tk.LEFT)
        ttk.Radiobutton(opts, text="MP4", variable=self.format_var, value="mp4").pack(side=tk.LEFT)
        ttk.Button(opts, text="Escolher pasta", command=self.choose_folder).pack(side=tk.RIGHT)
        self.output_dir = os.getcwd()

        ttk.Button(main, text="Baixar", command=self.start_download).pack(pady=10)
        log_frame = ttk.LabelFrame(main, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, height=8, state="disabled")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def log(self, msg: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def choose_folder(self) -> None:
        d = filedialog.askdirectory(initialdir=self.output_dir)
        if d:
            self.output_dir = d

    def start_download(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Erro", "Informe uma URL")
            return
        tracks = TrackParser.parse(self.track_text.get("1.0", tk.END))
        if not tracks:
            messagebox.showerror("Erro", "Lista de faixas invalida")
            return
        fmt = self.format_var.get()
        self.download_and_split(url, tracks, fmt)

    def download_and_split(self, url: str, tracks: list[Track], fmt: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_path = os.path.join(tmp, "audio.%(ext)s")
            cmd = [os.path.join("PATH", "yt-dlp.exe"), "-f", "bestaudio", "--no-progress", "-o", temp_path, url]
            self.log("Executando yt-dlp...")
            if subprocess.call(cmd) != 0:
                self.log("Falha no yt-dlp")
                return
            downloaded = next(p for p in os.listdir(tmp) if p.startswith("audio"))
            input_file = os.path.join(tmp, downloaded)
            for idx, t in enumerate(tracks, 1):
                out_name = f"{idx:02d} - {t.name}.{fmt}"
                out_path = os.path.join(self.output_dir, out_name)
                ff_cmd = [
                    os.path.join("PATH", "ffmpeg.exe"),
                    "-y",
                    "-i",
                    input_file,
                    "-ss",
                    str(t.start),
                ]
                if t.end is not None:
                    ff_cmd += ["-to", str(t.end)]
                ff_cmd += ["-vn", "-c:a", "libmp3lame" if fmt == "mp3" else "copy", out_path]
                self.log(f"Cortando {out_name}")
                subprocess.call(ff_cmd)
            self.log("Concluido!")


def main() -> None:
    app = DownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
