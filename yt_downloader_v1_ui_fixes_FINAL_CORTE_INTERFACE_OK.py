import os
import sys
import subprocess
import tkinter as tk
from tkinter import (
    ttk,
    messagebox,
    Menu,
    Text,
    Toplevel,
    IntVar,
    filedialog,
    StringVar,
)
import threading
import shutil
import re
import time
import json
import webbrowser
from datetime import datetime, timedelta
import math # Para calcular partes do vídeo

# --- Verificação de Dependências Opcionais --- #

# Tenta importar bibliotecas essenciais e opcionais
# Essenciais (o app não funciona sem elas ou funções chave falham)
REQUESTS_AVAILABLE = False
PILLOW_AVAILABLE = False
MUTAGEN_AVAILABLE = False
PYPERCLIP_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    print("[ERROR] Biblioteca 'requests' não encontrada. Downloads de miniaturas e verificação de atualizações não funcionarão.")

try:
    from PIL import Image, ImageTk
    PILLOW_AVAILABLE = True
except ImportError:
    print("[ERROR] Biblioteca 'Pillow' não encontrada. Processamento de miniaturas não funcionará.")

try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TRCK # Added TRCK
    MUTAGEN_AVAILABLE = True
except ImportError:
    print("[ERROR] Biblioteca 'mutagen' não encontrada. Adição de metadados a MP3s não funcionará.")

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    print("[WARNING] Biblioteca 'pyperclip' não encontrada. Botão 'Colar' pode não funcionar corretamente.")

# Opcional (o app funciona sem, apenas a funcionalidade específica é desabilitada)
SPLEETER_AVAILABLE = False
def check_spleeter_availability():
    """Verifica se o comando spleeter está acessível no PATH."""
    global SPLEETER_AVAILABLE
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        # Tenta executar um comando simples. Não verifica o código de retorno aqui,
        # apenas se o comando pode ser encontrado.
        subprocess.run(["spleeter", "--version"], capture_output=True, text=True, check=False, startupinfo=startupinfo)
        # Se não levantou FileNotFoundError, assumimos que o comando existe.
        # A funcionalidade real pode falhar depois se a instalação estiver incompleta,
        # mas a UI será habilitada.
        SPLEETER_AVAILABLE = True
        print("[INFO] Comando 'spleeter' encontrado. Funcionalidade de remoção de guitarra habilitada (pode falhar se a instalação estiver incompleta).")
    except FileNotFoundError:
        SPLEETER_AVAILABLE = False
        print("[WARNING] Comando 'spleeter' não encontrado no PATH. Funcionalidade de remoção de guitarra desabilitada.")
    except Exception as e:
        SPLEETER_AVAILABLE = False # Assume indisponível em caso de outro erro
        print(f"[ERROR] Erro inesperado ao verificar Spleeter: {e}. Funcionalidade desabilitada.")

# --- Configurações Globais e Paths --- #

if getattr(sys, 'frozen', False):
    # Se rodando como executável (PyInstaller)
    application_path = os.path.dirname(sys.executable)
else:
    # Se rodando como script Python
    application_path = os.path.dirname(os.path.abspath(__file__))

# Definição de diretórios base relativos ao path da aplicação
BASE_DIR = application_path # Usar application_path como base
DOWNLOADS_DIR = os.path.join(BASE_DIR, "Downloads")
MP3_DIR = os.path.join(DOWNLOADS_DIR, "MP3")
MP4_DIR = os.path.join(DOWNLOADS_DIR, "MP4") # Diretório para MP4 dividido
PROCESSED_DIR = os.path.join(DOWNLOADS_DIR, "Processed")
BACKUP_DIR = os.path.join(BASE_DIR, "Backup")
PATH_DIR = os.path.join(BASE_DIR, "PATH")
LOG_FILE = os.path.join(BASE_DIR, "activity_log.log")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
HISTORY_FILE = os.path.join(BASE_DIR, "downloads_history.json")
VERSION_FILE = os.path.join(BASE_DIR, "version.json")
THEMES_FILE = os.path.join(BASE_DIR, "themes.json")

# Cria diretórios se não existirem
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(MP3_DIR, exist_ok=True)
os.makedirs(MP4_DIR, exist_ok=True) # Cria pasta MP4
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(PATH_DIR, exist_ok=True)

# Adiciona o diretório PATH ao PATH do sistema (importante para ffmpeg, yt-dlp etc.)--- #
LOG_COLORS = {
    "ERROR": "#FF0000", "SUCCESS": "#00AA00", "WARNING": "#FFA500",
    "INFO": "#0000FF", "HIGHLIGHT": "#9900CC", "TIMESTAMP": "#888888"
}
log_text = None # Será inicializado com a UI

def log(msg, level="INFO"):
    # Log para console se a UI não estiver pronta
    if not log_text or not log_text.winfo_exists():
        print(f"[{level}] {msg}")
        return
    try:
        log_text.config(state='normal')
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_text.insert(tk.END, f"[{timestamp}] ", "TIMESTAMP")
        log_text.insert(tk.END, msg + "\n", level)
        log_text.see(tk.END)
        log_text.config(state='disabled')
    except Exception as e:
        print(f"[LOG_ERROR] Failed to write to log widget: {e}")
        print(f"[{level}] {msg}") # Fallback para console

def clear_log():
    """Limpa o conteúdo do widget de log."""
    if log_text and log_text.winfo_exists():
        log_text.config(state='normal')
        log_text.delete('1.0', tk.END)
        log_text.config(state='disabled')
        log("Log limpo.", "INFO")
    else:
        print("[INFO] Log limpo (console).")

# --- Funções de Carregamento e Salvamento (Usam Log) --- #

def load_version_info():
    local_version_file = os.path.join(application_path, "version.json")
    if not os.path.exists(local_version_file):
        local_version_file = "version.json"
    try:
        if os.path.exists(local_version_file):
            with open(local_version_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            log("Arquivo version.json local não encontrado, usando valores padrão.", "WARNING")
            return {
                "major": 1, "minor": 0, "patch": 0, "build": 1,
                "release_date": datetime.now().strftime("%d de %B de %Y"),
                "release_notes": "Versão inicial", "changes": [], "download_url": ""
            }
    except Exception as e:
        log(f"Erro ao carregar informações de versão local: {e}", "ERROR")
        return {
            "major": 1, "minor": 0, "patch": 0, "build": 1,
            "release_date": datetime.now().strftime("%d de %B de %Y"),
            "release_notes": "Versão inicial", "changes": [], "download_url": ""
        }

def load_download_history():
    history_file = os.path.join(application_path, "downloads_history.json")
    if not os.path.exists(history_file):
        history_file = "downloads_history.json"
    try:
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {"downloads": [], "last_update": datetime.now().isoformat()}
    except Exception as e:
        log(f"Erro ao carregar histórico de downloads: {e}", "ERROR")
        return {"downloads": [], "last_update": datetime.now().isoformat()}

def save_download_history(history_data):
    history_file = os.path.join(application_path, "downloads_history.json")
    if not os.path.exists(os.path.dirname(history_file)):
         history_file = "downloads_history.json"
    try:
        history_data["last_update"] = datetime.now().isoformat()
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        log(f"Erro ao salvar histórico de downloads: {e}", "ERROR")
        return False

def add_download_to_history(url, title, file_path, file_type, duration=None, thumbnail_path=None):
    history_data = load_download_history()
    download_record = {
        "url": url, "title": title, "file_path": file_path, "file_type": file_type,
        "timestamp": datetime.now().isoformat(), "duration": duration, "thumbnail_path": thumbnail_path
    }
    history_data["downloads"].insert(0, download_record)
    return save_download_history(history_data)

def clear_download_history(filter_type="all", specific_id=None):
    history_data = load_download_history()
    if filter_type == "all":
        history_data["downloads"] = []
    elif filter_type == "1hour":
        one_hour_ago = datetime.now() - timedelta(hours=1)
        history_data["downloads"] = [d for d in history_data["downloads"] if datetime.fromisoformat(d["timestamp"]) < one_hour_ago]
    elif filter_type == "1day":
        one_day_ago = datetime.now() - timedelta(days=1)
        history_data["downloads"] = [d for d in history_data["downloads"] if datetime.fromisoformat(d["timestamp"]) < one_day_ago]
    elif filter_type == "specific" and specific_id is not None:
        if 0 <= specific_id < len(history_data["downloads"]):
            del history_data["downloads"][specific_id]
    return save_download_history(history_data)

def load_theme_settings():
    theme_file = os.path.join(application_path, "themes.json")
    if not os.path.exists(theme_file):
        theme_file = "themes.json"
    try:
        if os.path.exists(theme_file):
            with open(theme_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            log("Arquivo themes.json não encontrado, usando valores padrão.", "WARNING")
            # Define temas padrão se o arquivo não existir
            return {
                "themes": {
                    "light": {"background": "#f0f0f0", "foreground": "#000000", "button": "#e1e1e1", "button_fg": "#000000", "highlight": "#4CAF50", "highlight_fg": "#ffffff", "frame": "#ffffff", "frame_border": "#d0d0d0", "entry": "#ffffff", "entry_fg": "#000000", "log_bg": "#ffffff", "log_fg": "#000000", "disabled_fg": "#aaaaaa"},
                    "dark": {"background": "#2d2d2d", "foreground": "#ffffff", "button": "#3d3d3d", "button_fg": "#ffffff", "highlight": "#4CAF50", "highlight_fg": "#ffffff", "frame": "#363636", "frame_border": "#555555", "entry": "#404040", "entry_fg": "#ffffff", "log_bg": "#2a2a2a", "log_fg": "#e0e0e0", "disabled_fg": "#777777"},
                    "blue": {"background": "#1e3d59", "foreground": "#ffffff", "button": "#2e5984", "button_fg": "#ffffff", "highlight": "#ff6e40", "highlight_fg": "#ffffff", "frame": "#2a4a6d", "frame_border": "#3a6a9d", "entry": "#2c5282", "entry_fg": "#ffffff", "log_bg": "#1a3552", "log_fg": "#e0e0e0", "disabled_fg": "#8ca4be"}
                },
                "current_theme": "light",
                "font_size": "normal"
            }
    except Exception as e:
        log(f"Erro ao carregar configurações de tema: {e}", "ERROR")
        # Retorna um tema padrão mínimo em caso de erro grave
        return {
            "themes": {"light": {"background": "#f0f0f0", "foreground": "#000000", "button": "#e1e1e1", "button_fg": "#000000", "highlight": "#4CAF50", "highlight_fg": "#ffffff", "frame": "#ffffff", "frame_border": "#d0d0d0", "entry": "#ffffff", "entry_fg": "#000000", "log_bg": "#ffffff", "log_fg": "#000000", "disabled_fg": "#aaaaaa"}},
            "current_theme": "light", "font_size": "normal"
        }

def save_theme_settings(theme_data):
    theme_file = os.path.join(application_path, "themes.json")
    if not os.path.exists(os.path.dirname(theme_file)):
        theme_file = "themes.json"
    try:
        with open(theme_file, 'w', encoding='utf-8') as f:
            json.dump(theme_data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        log(f"Erro ao salvar configurações de tema: {e}", "ERROR")
        return False

# --- Continuação das Configurações Globais --- #

VERSION_INFO = load_version_info()
APP_VERSION = f"{VERSION_INFO['major']}.{VERSION_INFO['minor']}.{VERSION_INFO['patch']} (Build {VERSION_INFO['build']})"
APP_CREATION_DATE = VERSION_INFO['release_date']

THEME_SETTINGS = load_theme_settings()
CURRENT_THEME = THEME_SETTINGS["current_theme"]
THEME_COLORS = THEME_SETTINGS["themes"].get(CURRENT_THEME, THEME_SETTINGS["themes"]["light"]) # Fallback para light

PATH_DIR = os.path.join(application_path, "PATH")
FFMPEG_PATH = os.path.join(PATH_DIR, "ffmpeg.exe")
YTDLP_PATH = os.path.join(PATH_DIR, "yt-dlp.exe")

BASE_DOWNLOAD_DIR = "C:\\YouTubeDownloads\\Downloads"
MP4_DIR = os.path.join(BASE_DOWNLOAD_DIR, "MP4")
MP3_DIR = os.path.join(BASE_DOWNLOAD_DIR, "MP3")
THUMBNAIL_DIR_MP4 = os.path.join(MP4_DIR, ".thumbnails")
THUMBNAIL_DIR_MP3 = os.path.join(MP3_DIR, ".thumbnails")
PROCESSED_DIR = os.path.join(BASE_DOWNLOAD_DIR, "Processed")
SPLEETER_OUTPUT_DIR = os.path.join(PROCESSED_DIR, "spleeter_temp")
INSTA_STORIES_DIR = os.path.join(PROCESSED_DIR, "Instagram_Stories")

os.makedirs(MP4_DIR, exist_ok=True)
os.makedirs(MP3_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_DIR_MP4, exist_ok=True)
os.makedirs(THUMBNAIL_DIR_MP3, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(INSTA_STORIES_DIR, exist_ok=True)

FFMPEG_EXISTS = os.path.exists(FFMPEG_PATH)
YTDLP_EXISTS = os.path.exists(YTDLP_PATH)

# Verifica Spleeter na inicialização
check_spleeter_availability()

last_download_path = ""

# --- Funções Utilitárias ---

def time_str_to_seconds(time_str):
    """Converte uma string de tempo (HH:MM:SS ou MM:SS) para segundos."""
    parts_str = str(time_str).split(':') # Corrigido: usar ':' como string
    parts = [int(p) for p in parts_str] # Converte para inteiros
    seconds = 0
    if len(parts) == 3: # HH:MM:SS
        seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2: # MM:SS
        seconds = parts[0] * 60 + parts[1]
    elif len(parts) == 1: # SS (Considera como segundos apenas)
        seconds = parts[0]
    else:
        raise ValueError(f"Formato de tempo inválido: {time_str}")
    return seconds

def parse_tracklist(tracklist_text_content):
    """Analisa o texto da lista de faixas e extrai nome e tempo inicial em segundos.
       Aceita formatos: [Num.] Nome Faixa HH:MM:SS, [Num.] Nome Faixa MM:SS,
                       [Num.] HH:MM:SS - Nome Faixa, [Num.] MM:SS - Nome Faixa"""
    tracks = []
    lines = tracklist_text_content.strip().split("\n")
    
    # Padrão 1: Nome no final, Tempo no início (com separador opcional)
    # Ex: 00:00 - This Is Why  ou  04:13 Brick by Boring Brick (sem separador explícito, mas espaço)
    # Captura: Tempo (grupo 1), Nome (grupo 3)
    pattern_time_first = re.compile(r"^(?:\d+\s*[.-]?\s*)?(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–—]?\s*(.*?)$", re.IGNORECASE)
    
    # Padrão 2: Nome no início, Tempo no final
    # Ex: Can't Stop 2:38
    # Captura: Nome (grupo 1), Tempo (grupo 2)
    pattern_name_first = re.compile(r"^(?:\d+\s*[.-]?\s*)?(.*?)\s+(\d{1,2}:\d{2}(?::\d{2})?)$", re.IGNORECASE)

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        name = None
        time_str = None
        
        # Tenta Padrão 1 (Tempo - Nome)
        match1 = pattern_time_first.match(line)
        if match1:
            time_str = match1.group(1)
            name = match1.group(2)
            log(f"Linha {i+1}: Detectado formato Tempo - Nome.", "INFO")
        else:
            # Tenta Padrão 2 (Nome Tempo)
            match2 = pattern_name_first.match(line)
            if match2:
                name = match2.group(1)
                time_str = match2.group(2)
                log(f"Linha {i+1}: Detectado formato Nome - Tempo.", "INFO")

        if name is not None and time_str is not None:
            name = name.strip()
            time_str = time_str.strip()
            try:
                start_seconds = time_str_to_seconds(time_str)
                sanitized_name = sanitize_filename(name if name else f"Faixa_{i+1}")
                tracks.append({"name": sanitized_name, "time_str": time_str, "start_seconds": start_seconds})
                log(f"  -> Faixa encontrada: 	{sanitized_name} 	({time_str} -> {start_seconds}s)", "INFO")
            except ValueError as e:
                log(f"Erro ao converter tempo na linha {i+1}: 	'{line}'. 	Erro: {e}", "ERROR")
        else:
            log(f"Formato inválido ou não reconhecido na linha {i+1}: 	'{line}'.", "WARNING")

    # Ordena as faixas pelo tempo inicial para evitar cortes incorretos caso a
    # lista seja fornecida fora de ordem. Mantemos o nome e outros dados.
    tracks.sort(key=lambda x: x["start_seconds"])

    # Calcula o tempo final (início da próxima faixa)
    for i in range(len(tracks)):
        if i + 1 < len(tracks):
            # Garante que o tempo final seja maior que o inicial
            if tracks[i+1]["start_seconds"] > tracks[i]["start_seconds"]:
                 tracks[i]["end_seconds"] = tracks[i+1]["start_seconds"]
            else:
                 # Se a próxima faixa começa no mesmo tempo ou antes (erro na lista?), define fim como None
                 log(f"Tempo da faixa {i+2} ({tracks[i+1]['time_str']}) não é maior que o da faixa {i+1} ({tracks[i]['time_str']}). Verifique a lista.", "WARNING")
                 tracks[i]["end_seconds"] = None 
        else:
            tracks[i]["end_seconds"] = None # Última faixa vai até o fim do vídeo

    log(f"Lista de faixas processada. {len(tracks)} faixas válidas encontradas.", "SUCCESS" if tracks else "WARNING")
    return tracks

def sanitize_filename(filename):
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    # Evita nomes reservados do Windows
    if sanitized.upper() in [f"COM{i}" for i in range(1, 10)] + [f"LPT{i}" for i in range(1, 10)] + ["CON", "PRN", "AUX", "NUL"]:
        sanitized = "_" + sanitized
    # Remove pontos finais que podem causar problemas em alguns sistemas
    sanitized = sanitized.rstrip('.') 
    return sanitized[:200] # Limita tamanho
def format_time_input(time_str):
    if not time_str:
        return ""
    digits = re.sub(r'[^0-9]', '', time_str)
    while len(digits) < 6:
        digits = "0" + digits
    if len(digits) > 6:
        digits = digits[-6:]
    return f"{digits[0:2]}:{digits[2:4]}:{digits[4:6]}"

def get_time_description(time_str):
    if not time_str:
        return ""
    try:
        parts = time_str.split(":")
        if len(parts) != 3:
            return ""
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        desc = []
        if h > 0:
            desc.append(f"{h} hora{'s' if h > 1 else ''}")
        if m > 0:
            desc.append(f"{m} minuto{'s' if m > 1 else ''}")
        if s > 0 or (h == 0 and m == 0):
            desc.append(f"{s} segundo{'s' if s > 1 else ''}")
        return " e ".join(desc)
    except Exception:
        return ""

def format_datetime(iso_date_str):
    try:
        dt = datetime.fromisoformat(iso_date_str)
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return iso_date_str

def update_time_labels(*args):
    start_value = start_entry.get().strip()
    if start_value:
        formatted_start = format_time_input(start_value)
        start_entry.delete(0, tk.END)
        start_entry.insert(0, formatted_start)
        start_label_desc.config(text=get_time_description(formatted_start))
    else:
        start_label_desc.config(text="")

    end_value = end_entry.get().strip()
    if end_value:
        formatted_end = format_time_input(end_value)
        end_entry.delete(0, tk.END)
        end_entry.insert(0, formatted_end)
        end_label_desc.config(text=get_time_description(formatted_end))
    else:
        end_label_desc.config(text="")

def open_download_folder():
    global last_download_path
    folder_to_open = BASE_DOWNLOAD_DIR
    if last_download_path and os.path.exists(os.path.dirname(last_download_path)):
        folder_to_open = os.path.dirname(last_download_path)
    elif os.path.exists(BASE_DOWNLOAD_DIR):
        folder_to_open = BASE_DOWNLOAD_DIR
    try:
        if os.name == 'nt': # Windows
            os.startfile(folder_to_open)
        elif os.name == 'posix': # macOS, Linux
            subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', folder_to_open], check=True)
        log(f"Abrindo pasta: {folder_to_open}", "INFO")
    except Exception as e:
        log(f"Erro ao abrir pasta {folder_to_open}: {e}", "ERROR")
        messagebox.showerror("Erro", f"Não foi possível abrir a pasta: {folder_to_open}\nErro: {e}")

def run_in_thread(target_func, args=()):
    thread = threading.Thread(target=target_func, args=args, daemon=True)
    thread.start()
    return thread

def check_ffmpeg_dependency(): # Renomeada para clareza
    if not FFMPEG_EXISTS:
        log("ffmpeg.exe não encontrado na pasta PATH. Funcionalidades de corte, conversão e manipulação podem não funcionar.", "ERROR")
        messagebox.showerror("Erro de Dependência", "ffmpeg.exe não encontrado na pasta PATH.\n\nVerifique se o arquivo está presente. Funcionalidades de corte, conversão e manipulação podem falhar.")
        return False
    return True

def check_ytdlp_dependency(): # Renomeada para clareza
    if not YTDLP_EXISTS:
        log("yt-dlp.exe não encontrado na pasta PATH. Downloads não funcionarão.", "ERROR")
        messagebox.showerror("Erro de Dependência", "yt-dlp.exe não encontrado na pasta PATH.\n\nVerifique se o arquivo está presente. O download de vídeos não funcionará.")
        return False
    return True

# --- Funções Principais de Download e Processamento --- #

def get_video_title(url):
    if not check_ytdlp_dependency():
        return None
    try:
        command = [YTDLP_PATH, '--get-title', '--no-warnings', url]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace', startupinfo=startupinfo)
        title = result.stdout.strip()
        log(f"Título obtido para {url}: {title}", "INFO")
        return title
    except subprocess.CalledProcessError as e:
        log(f"Erro ao obter título (yt-dlp): {e.stderr}", "ERROR")
        return None
    except Exception as e:
        log(f"Erro inesperado ao obter título: {e}", "ERROR")
        return None

def get_video_duration(file_path):
    if not check_ffmpeg_dependency():
        return None
    try:
        command = [
            FFMPEG_PATH, '-i', file_path,
            '-f', 'null', '-'
        ]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(command, capture_output=True, text=True, check=False, stderr=subprocess.PIPE, startupinfo=startupinfo)
        output = result.stderr
        duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2})\.(\d{2})", output)
        if duration_match:
            hours, minutes, seconds, _ = map(int, duration_match.groups())
            total_seconds = hours * 3600 + minutes * 60 + seconds
            log(f"Duração obtida para {os.path.basename(file_path)}: {total_seconds}s", "INFO")
            return total_seconds
        else:
            log(f"Não foi possível encontrar a duração no output do FFmpeg para {os.path.basename(file_path)}", "WARNING")
            return None
    except Exception as e:
        log(f"Erro ao obter duração com FFmpeg: {e}", "ERROR")
        return None

def download_thumbnail(url, save_path):
    if not check_ytdlp_dependency():
        return None
    if not REQUESTS_AVAILABLE:
        log("Biblioteca 'requests' não disponível para baixar miniatura.", "ERROR")
        return None
    try:
        # Obter URL da miniatura
        command_thumb = [YTDLP_PATH, '--get-thumbnail', '--no-warnings', url]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        result_thumb = subprocess.run(command_thumb, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace', startupinfo=startupinfo)
        thumbnail_url = result_thumb.stdout.strip()

        if thumbnail_url:
            # Baixar a imagem
            response = requests.get(thumbnail_url, stream=True, timeout=15)
            response.raise_for_status() # Verifica se houve erro no request

            # Salvar a imagem
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            log(f"Miniatura baixada e salva em: {save_path}", "SUCCESS")
            return save_path
        else:
            log(f"Não foi possível obter URL da miniatura para {url}", "WARNING")
            return None
    except subprocess.CalledProcessError as e:
        log(f"Erro ao obter URL da miniatura (yt-dlp): {e.stderr}", "ERROR")
        return None
    except requests.exceptions.RequestException as e:
        log(f"Erro ao baixar miniatura (requests): {e}", "ERROR")
        return None
    except Exception as e:
        log(f"Erro inesperado ao baixar miniatura: {e}", "ERROR")
        return None

def add_metadata_to_mp3(mp3_path, title, thumbnail_path):
    if not MUTAGEN_AVAILABLE:
        log("Biblioteca 'mutagen' não disponível para adicionar metadados.", "ERROR")
        return
    if not os.path.exists(mp3_path):
        log(f"Arquivo MP3 não encontrado para adicionar metadados: {mp3_path}", "ERROR")
        return

    try:
        audio = MP3(mp3_path, ID3=ID3)

        # Adiciona tags ID3 se não existirem
        if audio.tags is None:
            audio.add_tags()

        # Título
        audio.tags.add(TIT2(encoding=3, text=title))
        # Artista (pode ser melhorado se a informação estiver disponível)
        audio.tags.add(TPE1(encoding=3, text="YouTube"))
        # Álbum (pode ser melhorado)
        audio.tags.add(TALB(encoding=3, text="YouTube Downloads"))

        # Capa do Álbum (Miniatura)
        if PILLOW_AVAILABLE and thumbnail_path and os.path.exists(thumbnail_path):
            try:
                with open(thumbnail_path, 'rb') as albumart:
                    # Determina o mime type (geralmente image/jpeg ou image/png)
                    img = Image.open(thumbnail_path)
                    mime_type = Image.MIME.get(img.format)
                    if not mime_type:
                        # Fallback se o formato não for reconhecido diretamente
                        ext = os.path.splitext(thumbnail_path)[1].lower()
                        if ext == '.jpg' or ext == '.jpeg':
                            mime_type = 'image/jpeg'
                        elif ext == '.png':
                            mime_type = 'image/png'
                        else:
                             mime_type = 'image/' # Genérico

                    audio.tags.add(
                        APIC(
                            encoding=3, # 3 is for utf-8
                            mime=mime_type,
                            type=3, # 3 is for the cover image (front)
                            desc='Cover',
                            data=albumart.read()
                        )
                    )
                log(f"Metadados de capa adicionados ao MP3: {os.path.basename(mp3_path)}", "SUCCESS")
            except Exception as img_e:
                log(f"Erro ao processar ou adicionar imagem de capa (Pillow/Mutagen): {img_e}", "ERROR")
        elif not PILLOW_AVAILABLE:
             log("Biblioteca 'Pillow' não disponível para adicionar capa ao MP3.", "WARNING")
        elif not thumbnail_path or not os.path.exists(thumbnail_path):
            log(f"Arquivo de miniatura não encontrado para adicionar como capa: {thumbnail_path}", "WARNING")

        audio.save()
        log(f"Metadados (título, artista, álbum) adicionados ao MP3: {os.path.basename(mp3_path)}", "SUCCESS")

    except Exception as e:
        log(f"Erro ao adicionar metadados ao MP3 {os.path.basename(mp3_path)} (Mutagen): {e}", "ERROR")

def download_video_thread(url, format_choice, quality_choice, start_time, end_time):
    global last_download_path
    if not check_ytdlp_dependency():
        return
    if (start_time or end_time) and not check_ffmpeg_dependency():
        return

    log(f"Iniciando download: {url} (Formato: {format_choice}, Qualidade: {quality_choice})", "INFO")
    # Desabilita botões na UI principal
    if download_button.winfo_exists():
        download_button.config(state=tk.DISABLED)
    if playlist_button.winfo_exists():
        playlist_button.config(state=tk.DISABLED)
    if open_folder_button.winfo_exists():
        open_folder_button.config(state=tk.DISABLED)
    if progress_bar.winfo_exists():
        progress_bar.start(10)

    try:
        # 1. Obter título
        title = get_video_title(url)
        if not title:
            title = f"video_{int(time.time())}" # Nome padrão se falhar
            log(f"Não foi possível obter o título, usando nome padrão: {title}", "WARNING")
        sanitized_title = sanitize_filename(title)

        # 2. Definir pasta de destino e nome do arquivo temporário/final
        is_mp3 = (format_choice == "MP3")
        download_dir = MP3_DIR if is_mp3 else MP4_DIR
        thumbnail_dir = THUMBNAIL_DIR_MP3 if is_mp3 else THUMBNAIL_DIR_MP4
        file_ext = "mp3" if is_mp3 else "mp4"

        # Nome base para arquivos temporários e finais
        base_filename = sanitized_title
        temp_filename = f"{base_filename}_temp.{file_ext}"
        temp_filepath = os.path.join(download_dir, temp_filename)
        final_filename = f"{base_filename}.{file_ext}"
        final_filepath = os.path.join(download_dir, final_filename)

        # Adiciona sufixo se for cortar
        cut_suffix = "_cortado"
        if start_time or end_time:
            final_filename = f"{base_filename}{cut_suffix}.{file_ext}"
            final_filepath = os.path.join(download_dir, final_filename)

        # 3. Baixar Miniatura (se requests estiver disponível)
        downloaded_thumbnail_path = None
        if REQUESTS_AVAILABLE:
            thumbnail_filename = f"{sanitized_title}_thumb.jpg" # Salvar como jpg por padrão
            thumbnail_save_path = os.path.join(thumbnail_dir, thumbnail_filename)
            downloaded_thumbnail_path = download_thumbnail(url, thumbnail_save_path)
        else:
            log("Download de miniatura pulado: biblioteca 'requests' não encontrada.", "WARNING")

        # 4. Construir comando yt-dlp
        command = [
            YTDLP_PATH,
            '--no-warnings',
            '--progress',
            '--output', temp_filepath # Sempre baixa para um arquivo temporário
        ]

        if is_mp3:
            command.extend(['-x', '--audio-format', 'mp3'])
            if quality_choice.lower() != 'best': # Assume 'best' para áudio se não especificado
                 command.extend(['--audio-quality', quality_choice]) # Ex: 128K, 192K, etc.
            else:
                 command.extend(['--audio-quality', '0']) # 0 geralmente é a melhor qualidade no yt-dlp para áudio
        else: # MP4
            # Formato: bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best
            # Ou usar códigos de formato específicos se quality_choice for um número (ex: '1080')
            if quality_choice.isdigit(): # Se for um número como '1080', '720'
                format_code = f'bestvideo[height<={quality_choice}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality_choice}][ext=mp4]/best[height<={quality_choice}]'
            elif quality_choice.lower() == 'best':
                format_code = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            else: # Fallback para 'best' se a qualidade não for reconhecida
                format_code = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                log(f"Qualidade '{quality_choice}' não reconhecida para MP4, usando 'best'.", "WARNING")
            command.extend(['-f', format_code])
            command.extend(['--merge-output-format', 'mp4']) # Garante MP4 na saída da mesclagem

        command.append(url)

        # 5. Executar Download (yt-dlp)
        log(f"Executando comando yt-dlp: {' '.join(command)}", "INFO")
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1, universal_newlines=True, startupinfo=startupinfo)

        # Ler output do processo para log e progresso (simplificado)
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                log(line.strip(), "INFO") # Logar output do yt-dlp
                # Extrair progresso se possível (requer parsing mais complexo)
            process.stdout.close()
        return_code = process.wait()

        if return_code != 0:
            log(f"Erro durante o download (yt-dlp retornou código {return_code}). Verifique o log acima.", "ERROR")
            raise Exception(f"yt-dlp falhou com código {return_code}")
        else:
            log("Download inicial (arquivo temporário) concluído com sucesso.", "SUCCESS")

        # 6. Processamento Pós-Download (Corte com FFmpeg)
        if start_time or end_time:
            log("Iniciando corte com FFmpeg...", "INFO")
            if not check_ffmpeg_dependency():
                raise Exception("FFmpeg não encontrado para corte.")

            ffmpeg_command = [FFMPEG_PATH, '-y'] # -y para sobrescrever sem perguntar

            # Adiciona -ss ANTES de -i para busca rápida
            if start_time:
                ffmpeg_command.extend(['-ss', start_time])

            ffmpeg_command.extend(['-i', temp_filepath])

            # Adiciona -to DEPOIS de -i
            if end_time:
                 ffmpeg_command.extend(['-to', end_time])

            # Copia codecs para evitar re-encode desnecessário se possível
            ffmpeg_command.extend(['-c', 'copy'])

            ffmpeg_command.append(final_filepath)

            log(f"Executando comando FFmpeg: {' '.join(ffmpeg_command)}", "INFO")
            startupinfo_ffmpeg = None
            if os.name == 'nt':
                startupinfo_ffmpeg = subprocess.STARTUPINFO()
                startupinfo_ffmpeg.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo_ffmpeg.wShowWindow = subprocess.SW_HIDE
            result_ffmpeg = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False, encoding='utf-8', errors='replace', startupinfo=startupinfo_ffmpeg)

            if result_ffmpeg.returncode != 0:
                log(f"Erro durante o corte com FFmpeg (código {result_ffmpeg.returncode}): {result_ffmpeg.stderr}", "ERROR")
                # Tentar sem '-c copy' se falhar (pode ser problema de codec)
                log("Tentando cortar novamente sem '-c copy' (pode re-encodar)...", "WARNING")
                ffmpeg_command_recode = [cmd for cmd in ffmpeg_command if cmd != '-c' and cmd != 'copy']
                log(f"Executando comando FFmpeg (re-encode): {' '.join(ffmpeg_command_recode)}", "INFO")
                result_ffmpeg_recode = subprocess.run(ffmpeg_command_recode, capture_output=True, text=True, check=False, encoding='utf-8', errors='replace', startupinfo=startupinfo_ffmpeg)
                if result_ffmpeg_recode.returncode != 0:
                     log(f"Erro durante o corte com FFmpeg (mesmo re-encodando): {result_ffmpeg_recode.stderr}", "ERROR")
                     raise Exception(f"FFmpeg falhou ao cortar o arquivo (código {result_ffmpeg_recode.returncode})")
                else:
                    log("Corte com FFmpeg (re-encode) concluído com sucesso.", "SUCCESS")
            else:
                log("Corte com FFmpeg concluído com sucesso.", "SUCCESS")

            # Remove o arquivo temporário após o corte bem-sucedido
            try:
                os.remove(temp_filepath)
                log(f"Arquivo temporário removido: {temp_filepath}", "INFO")
            except OSError as e:
                log(f"Erro ao remover arquivo temporário {temp_filepath}: {e}", "WARNING")

        else:
            # Se não houve corte, apenas renomeia o temporário para o final
            try:
                shutil.move(temp_filepath, final_filepath)
                log(f"Arquivo renomeado para: {final_filepath}", "SUCCESS")
            except OSError as e:
                 log(f"Erro ao renomear arquivo temporário {temp_filepath} para {final_filepath}: {e}", "ERROR")
                 # Tenta copiar e remover como fallback
                 try:
                     shutil.copy2(temp_filepath, final_filepath)
                     os.remove(temp_filepath)
                     log(f"Arquivo copiado para: {final_filepath} e temporário removido.", "SUCCESS")
                 except Exception as copy_e:
                     log(f"Falha ao copiar/remover arquivo temporário: {copy_e}", "ERROR")
                     final_filepath = temp_filepath # Mantém o temporário como final nesse caso extremo

        # 7. Adicionar Metadados (se MP3 e mutagen disponível)
        if is_mp3 and MUTAGEN_AVAILABLE:
            add_metadata_to_mp3(final_filepath, title, downloaded_thumbnail_path)
        elif is_mp3 and not MUTAGEN_AVAILABLE:
            log("Metadados não adicionados ao MP3: biblioteca 'mutagen' não encontrada.", "WARNING")

        # 8. Atualizar último download e histórico
        last_download_path = final_filepath
        duration_seconds = get_video_duration(final_filepath)
        add_download_to_history(url, title, final_filepath, format_choice, duration_seconds, downloaded_thumbnail_path)
        log(f"Download e processamento concluídos! Arquivo salvo em: {final_filepath}", "SUCCESS")
        messagebox.showinfo("Sucesso", f"Download concluído!\n\nArquivo salvo em:\n{final_filepath}")

    except Exception as e:
        log(f"Erro geral no processo de download: {e}", "ERROR")
        messagebox.showerror("Erro", f"Ocorreu um erro durante o download:\n{e}")
        # Tenta limpar arquivo temporário em caso de erro
        if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
                log(f"Arquivo temporário {temp_filepath} removido devido a erro.", "INFO")
            except OSError as rm_e:
                log(f"Erro ao remover arquivo temporário {temp_filepath} após falha: {rm_e}", "WARNING")

    finally:
        # Reabilita botões e para barra de progresso
        if download_button.winfo_exists():
            download_button.config(state=tk.NORMAL)
        if playlist_button.winfo_exists():
            playlist_button.config(state=tk.NORMAL)
        if open_folder_button.winfo_exists():
            open_folder_button.config(state=tk.NORMAL)
        if progress_bar.winfo_exists():
            progress_bar.stop()

def start_download():
    url = url_entry.get().strip()
    if not url:
        messagebox.showwarning("Entrada Inválida", "Por favor, insira uma URL do YouTube.")
        return

    format_choice = format_var.get()
    quality_choice = quality_var.get()
    start_time = start_entry.get().strip()
    end_time = end_entry.get().strip()

    # Valida formato HH:MM:SS se preenchido
    if start_time and not re.match(r'^\d{2}:\d{2}:\d{2}$', start_time):
        messagebox.showwarning("Tempo Inválido", "Formato inválido para Tempo Inicial. Use HH:MM:SS.")
        return
    if end_time and not re.match(r'^\d{2}:\d{2}:\d{2}$', end_time):
        messagebox.showwarning("Tempo Inválido", "Formato inválido para Tempo Final. Use HH:MM:SS.")
        return

    # Verifica se o tempo final é maior que o inicial
    if start_time and end_time:
        try:
            t_start = sum(int(x) * 60 ** i for i, x in enumerate(reversed(start_time.split(':'))))
            t_end = sum(int(x) * 60 ** i for i, x in enumerate(reversed(end_time.split(':'))))
            if t_end <= t_start:
                 messagebox.showwarning("Tempo Inválido", "O Tempo Final deve ser maior que o Tempo Inicial.")
                 return
        except ValueError:
             messagebox.showwarning("Tempo Inválido", "Erro ao converter tempos para comparação.")
             return

    # Verifica se é uma playlist ANTES de iniciar a thread
    if "list=" in url:
        response = messagebox.askyesno("Playlist Detectada", "A URL parece ser de uma playlist. Deseja baixar a playlist inteira?")
        if response:
            open_playlist_window(url)
            return # Aborta download individual
        else:
            log("Usuário optou por baixar apenas o vídeo individual da playlist.", "INFO")
            # Continua para baixar apenas o vídeo da URL

    # Inicia o download em uma thread separada
    run_in_thread(download_video_thread, args=(url, format_choice, quality_choice, start_time, end_time))

# --- Funções da Janela de Playlist --- #

def fetch_playlist_info(url):
    if not check_ytdlp_dependency():
        return None
    log(f"Obtendo informações da playlist: {url}", "INFO")
    playlist_info_label.config(text="Buscando vídeos da playlist...")
    root.update_idletasks()

    try:
        command = [
            YTDLP_PATH,
            '--flat-playlist', # Lista vídeos sem baixar metadados completos
            '--print', '"%(id)s---%(title)s---%(duration_string)s"', # Imprime ID, Título e Duração
            '--no-warnings',
            url
        ]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace', startupinfo=startupinfo)

        videos = []
        output_lines = result.stdout.strip().split('\n')
        for line in output_lines:
            if line.strip():
                parts = line.strip().strip('"').split('---') # Remove aspas extras e divide
                if len(parts) == 3:
                    video_id, title, duration = parts
                    # Recria a URL do vídeo individual
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    videos.append({"id": video_id, "url": video_url, "title": title, "duration": duration})
                else:
                    log(f"Linha de informação da playlist mal formatada: {line}", "WARNING")

        log(f"{len(videos)} vídeos encontrados na playlist.", "SUCCESS")
        playlist_info_label.config(text=f"{len(videos)} vídeos encontrados.")
        return videos

    except subprocess.CalledProcessError as e:
        log(f"Erro ao obter informações da playlist (yt-dlp): {e.stderr}", "ERROR")
        playlist_info_label.config(text="Erro ao buscar vídeos.")
        messagebox.showerror("Erro Playlist", f"Não foi possível obter informações da playlist.\nErro: {e.stderr}")
        return None
    except Exception as e:
        log(f"Erro inesperado ao obter informações da playlist: {e}", "ERROR")
        playlist_info_label.config(text="Erro inesperado.")
        messagebox.showerror("Erro Playlist", f"Ocorreu um erro inesperado.\nErro: {e}")
        return None

def populate_playlist_listbox(videos):
    playlist_listbox.delete(0, tk.END)
    playlist_check_vars.clear()
    if videos:
        for i, video in enumerate(videos):
            var = IntVar(value=1) # Selecionado por padrão
            playlist_check_vars.append(var)
            # Usar um Frame para conter o Checkbutton e permitir melhor controle de estilo
            item_frame = ttk.Frame(playlist_listbox, style="ListboxItem.TFrame")
            cb = ttk.Checkbutton(item_frame, text=f"{i+1}. {video['title']} ({video['duration']})", variable=var, style="TCheckbutton")
            cb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
            # Aplica o tema ao Checkbutton e ao Frame
            style.configure("ListboxItem.TFrame", background=THEME_COLORS["frame"]) # Cor de fundo do item
            style.configure("TCheckbutton", background=THEME_COLORS["frame"], foreground=THEME_COLORS["foreground"])

            playlist_listbox.insert(tk.END, "") # Placeholder para o frame
            playlist_listbox.window_create(tk.END, window=item_frame)
    else:
        playlist_listbox.insert(tk.END, " Nenhum vídeo encontrado ou erro.")

def select_all_playlist(value):
    for var in playlist_check_vars:
        var.set(value)

def invert_selection_playlist():
    for var in playlist_check_vars:
        var.set(1 - var.get())

def start_playlist_download_thread(videos_to_download, format_choice, quality_choice):
    log(f"Iniciando download de {len(videos_to_download)} vídeos da playlist...", "HIGHLIGHT")
    playlist_progress_bar.start(10)
    playlist_download_button.config(state=tk.DISABLED)
    playlist_select_all_button.config(state=tk.DISABLED)
    playlist_deselect_all_button.config(state=tk.DISABLED)
    playlist_invert_button.config(state=tk.DISABLED)

    total_videos = len(videos_to_download)
    completed_videos = 0
    errors = 0

    for i, video_info in enumerate(videos_to_download):
        log(f"Baixando vídeo {i+1}/{total_videos}: {video_info['title']}", "INFO")
        playlist_status_label.config(text=f"Baixando {i+1}/{total_videos}: {video_info['title'][:40]}...")
        try:
            # Chama a função de download individual (sem tempos de corte)
            # Precisamos garantir que a função de download individual seja robusta
            # e não pare a thread inteira em caso de erro.
            # A função download_video_thread já tem try/except interno.
            download_video_thread(video_info['url'], format_choice, quality_choice, None, None)
            # A função download_video_thread já loga sucesso ou erro.
            # Precisamos verificar se houve erro de alguma forma?
            # Por enquanto, contamos como sucesso se não lançou exceção aqui.
            completed_videos += 1
        except Exception as e:
            # Este except provavelmente não será atingido se o interno funcionar
            log(f"Erro GERAL ao baixar vídeo {video_info['title']}: {e}", "ERROR")
            errors += 1

        # Atualiza progresso (simplificado)
        # progress = (i + 1) / total_videos * 100
        # playlist_progress_bar['value'] = progress
        # root.update_idletasks()

    playlist_progress_bar.stop()
    playlist_progress_bar['value'] = 0
    playlist_download_button.config(state=tk.NORMAL)
    playlist_select_all_button.config(state=tk.NORMAL)
    playlist_deselect_all_button.config(state=tk.NORMAL)
    playlist_invert_button.config(state=tk.NORMAL)

    final_message = f"Download da playlist concluído!\n{completed_videos} vídeos baixados com sucesso."
    if errors > 0:
        final_message += f"\n{errors} vídeos falharam (verifique o log)."
        log(final_message, "WARNING")
        messagebox.showwarning("Playlist Concluída com Erros", final_message)
    else:
        log(final_message, "SUCCESS")
        messagebox.showinfo("Playlist Concluída", final_message)

    playlist_status_label.config(text="Pronto.")
    # Fecha a janela de playlist automaticamente?
    # playlist_window.destroy()

def start_playlist_download():
    selected_indices = [i for i, var in enumerate(playlist_check_vars) if var.get() == 1]
    if not selected_indices:
        messagebox.showwarning("Nenhum Vídeo Selecionado", "Por favor, selecione pelo menos um vídeo para baixar.")
        return

    videos_to_download = [playlist_videos[i] for i in selected_indices]
    format_choice = playlist_format_var.get()
    quality_choice = playlist_quality_var.get()

    run_in_thread(start_playlist_download_thread, args=(videos_to_download, format_choice, quality_choice))

def open_playlist_window(url):
    global playlist_window, playlist_listbox, playlist_check_vars, playlist_videos
    global playlist_info_label, playlist_status_label, playlist_progress_bar
    global playlist_format_var, playlist_quality_var, playlist_download_button
    global playlist_select_all_button, playlist_deselect_all_button, playlist_invert_button
    # global playlist_listbox_frame # Removido, usar Listbox diretamente

    playlist_window = Toplevel(root)
    playlist_window.title("Baixar Playlist")
    playlist_window.geometry("600x500")
    playlist_window.configure(bg=THEME_COLORS["background"])
    apply_theme_to_widget(playlist_window)

    # Frame superior para informações e controles
    top_frame = ttk.Frame(playlist_window, padding="10", style="TFrame")
    top_frame.pack(fill=tk.X)

    playlist_info_label = ttk.Label(top_frame, text="Buscando informações da playlist...", style="TLabel")
    playlist_info_label.pack(side=tk.LEFT, padx=5)

    # Frame para a lista de vídeos com scrollbar
    list_frame = ttk.Frame(playlist_window, padding="5", style="TFrame")
    list_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)

    playlist_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, style="Vertical.TScrollbar")
    playlist_listbox = tk.Listbox(list_frame, yscrollcommand=playlist_scrollbar.set,
                                  bg=THEME_COLORS["frame"], fg=THEME_COLORS["foreground"],
                                  selectbackground=THEME_COLORS["highlight"],
                                  selectforeground=THEME_COLORS["highlight_fg"],
                                  borderwidth=1, relief="sunken", height=15)
    playlist_scrollbar.config(command=playlist_listbox.yview)
    playlist_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    playlist_listbox.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

    # playlist_listbox_frame = ttk.Frame(playlist_listbox, style="TFrame")
    # playlist_listbox.window_create(tk.END, window=playlist_listbox_frame)

    playlist_check_vars = []
    playlist_videos = []

    # Frame para botões de seleção
    selection_frame = ttk.Frame(playlist_window, padding="5", style="TFrame")
    selection_frame.pack(fill=tk.X, padx=10)

    playlist_select_all_button = ttk.Button(selection_frame, text="Selecionar Todos", command=lambda: select_all_playlist(1), style="TButton")
    playlist_select_all_button.pack(side=tk.LEFT, padx=5)
    playlist_deselect_all_button = ttk.Button(selection_frame, text="Desmarcar Todos", command=lambda: select_all_playlist(0), style="TButton")
    playlist_deselect_all_button.pack(side=tk.LEFT, padx=5)
    playlist_invert_button = ttk.Button(selection_frame, text="Inverter Seleção", command=invert_selection_playlist, style="TButton")
    playlist_invert_button.pack(side=tk.LEFT, padx=5)

    # Frame para opções de download
    options_frame = ttk.Frame(playlist_window, padding="5", style="TFrame")
    options_frame.pack(fill=tk.X, padx=10)

    ttk.Label(options_frame, text="Formato:", style="TLabel").pack(side=tk.LEFT, padx=5)
    playlist_format_var = StringVar(value="MP4")
    playlist_format_menu = ttk.Combobox(options_frame, textvariable=playlist_format_var, values=["MP4", "MP3"], state="readonly", width=8, style="TCombobox")
    playlist_format_menu.pack(side=tk.LEFT, padx=5)

    ttk.Label(options_frame, text="Qualidade:", style="TLabel").pack(side=tk.LEFT, padx=5)
    playlist_quality_var = StringVar(value="best")
    playlist_quality_menu = ttk.Combobox(options_frame, textvariable=playlist_quality_var, values=["best", "1080", "720", "480"], width=10, style="TCombobox") # Adicionar mais opções se necessário
    playlist_quality_menu.pack(side=tk.LEFT, padx=5)

    # Frame inferior para status e botão de download
    bottom_frame = ttk.Frame(playlist_window, padding="10", style="TFrame")
    bottom_frame.pack(fill=tk.X)

    playlist_status_label = ttk.Label(bottom_frame, text="Pronto.", style="TLabel")
    playlist_status_label.pack(side=tk.LEFT, padx=5)

    playlist_progress_bar = ttk.Progressbar(bottom_frame, orient='horizontal', mode='indeterminate', length=150)
    playlist_progress_bar.pack(side=tk.LEFT, padx=10)

    playlist_download_button = ttk.Button(bottom_frame, text="Baixar Selecionados", command=start_playlist_download, style="Highlight.TButton")
    playlist_download_button.pack(side=tk.RIGHT, padx=5)

    # Busca informações da playlist em outra thread
    def fetch_and_populate():
        global playlist_videos
        playlist_videos = fetch_playlist_info(url)
        if playlist_videos:
            populate_playlist_listbox(playlist_videos)
        else:
            playlist_info_label.config(text="Falha ao buscar vídeos.")
            playlist_listbox.insert(tk.END, " Erro ao carregar playlist.")

    run_in_thread(fetch_and_populate)

# --- Funções da Janela de Histórico --- #

def populate_history_listbox():
    history_listbox.delete(0, tk.END)
    history_data = load_download_history()
    downloads = history_data.get("downloads", [])

    if not downloads:
        history_listbox.insert(tk.END, " Histórico vazio.")
        return

    for i, item in enumerate(downloads):
        # Formata a linha do histórico
        timestamp_str = format_datetime(item.get("timestamp", ""))
        title_str = item.get("title", "N/A")[:60] # Limita tamanho do título
        type_str = item.get("file_type", "N/A")
        display_text = f" {timestamp_str} - [{type_str}] {title_str}"

        # Tenta carregar e exibir miniatura (se Pillow disponível)
        thumbnail_path = item.get("thumbnail_path")
        list_item_frame = ttk.Frame(history_listbox, style="ListboxItem.TFrame")

        thumb_label = ttk.Label(list_item_frame, style="TLabel") # Label para a miniatura
        if PILLOW_AVAILABLE and thumbnail_path and os.path.exists(thumbnail_path):
            try:
                img = Image.open(thumbnail_path)
                img.thumbnail((40, 30)) # Redimensiona para caber na linha
                photo = ImageTk.PhotoImage(img)
                thumb_label.config(image=photo)
                thumb_label.image = photo # Mantém referência
            except Exception as e:
                log(f"Erro ao carregar miniatura do histórico {thumbnail_path}: {e}", "WARNING")
                thumb_label.config(text="[X]") # Placeholder se falhar
        elif not PILLOW_AVAILABLE:
             thumb_label.config(text="[P]") # Placeholder Pillow indisponível
        else:
            thumb_label.config(text="[ ]") # Placeholder se não houver miniatura

        thumb_label.pack(side=tk.LEFT, padx=5)

        # Label para o texto
        text_label = ttk.Label(list_item_frame, text=display_text, anchor="w", style="TLabel")
        text_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Adiciona o frame ao Listbox
        history_listbox.insert(tk.END, "") # Placeholder
        history_listbox.window_create(tk.END, window=list_item_frame, padx=5, pady=3)

        # Adiciona tooltip com caminho completo
        # ToolTip(list_item_frame, text=f"Caminho: {item.get('file_path', 'N/A')}")

def show_history_context_menu(event):
    selected_index = history_listbox.nearest(event.y) # Obtém índice do item clicado
    # Precisa ajustar o índice se estivermos usando frames dentro do listbox
    # A lógica de obter o índice correto pode precisar de ajuste.
    # Vamos assumir que nearest funciona razoavelmente bem por enquanto.
    if selected_index < 0 or selected_index >= history_listbox.size():
        return # Clicou fora de um item válido

    # Seleciona o item clicado
    history_listbox.selection_clear(0, tk.END)
    history_listbox.selection_set(selected_index)
    history_listbox.activate(selected_index)

    # Obtém dados do item selecionado
    history_data = load_download_history()
    downloads = history_data.get("downloads", [])
    if selected_index >= len(downloads):
         return # Índice fora dos limites dos dados reais

    selected_item_data = downloads[selected_index]
    file_path = selected_item_data.get("file_path")
    video_url = selected_item_data.get("url")

    # Cria o menu de contexto
    context_menu = Menu(root, tearoff=0)
    apply_theme_to_widget(context_menu) # Aplica tema ao menu

    if file_path and os.path.exists(file_path):
        context_menu.add_command(label="Abrir Arquivo", command=lambda p=file_path: os.startfile(p) if os.name == 'nt' else subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', p]))
        context_menu.add_command(label="Abrir Pasta", command=lambda p=file_path: open_folder_path(os.path.dirname(p)))
    else:
        context_menu.add_command(label="Abrir Arquivo (Não encontrado)", state=tk.DISABLED)
        context_menu.add_command(label="Abrir Pasta (Não encontrado)", state=tk.DISABLED)

    if video_url:
         context_menu.add_command(label="Baixar Novamente", command=lambda u=video_url: download_again_from_history(u))

    context_menu.add_separator()
    context_menu.add_command(label="Remover do Histórico", command=lambda idx=selected_index: remove_specific_history_item(idx))

    context_menu.tk_popup(event.x_root, event.y_root)

def open_folder_path(folder_path):
    """Abre uma pasta específica no explorador."""
    try:
        if os.path.exists(folder_path):
            if os.name == "nt":
                os.startfile(folder_path)
            else:
                subprocess.run(
                    ["open" if sys.platform == "darwin" else "xdg-open", folder_path],
                    check=True,
                )
            log(f"Abrindo pasta: {folder_path}", "INFO")
        else:
            log(f"Pasta não encontrada: {folder_path}", "WARNING")
            messagebox.showwarning("Pasta Não Encontrada", f"A pasta {folder_path} não foi encontrada.")
    except Exception as e:
        log(f"Erro ao abrir pasta {folder_path}: {e}", "ERROR")
        messagebox.showerror("Erro", f"Não foi possível abrir a pasta: {folder_path}\nErro: {e}")

def download_again_from_history(url):
    """Inicia um novo download a partir de um item do histórico."""
    log(f"Iniciando download novamente para: {url}", "HIGHLIGHT")
    # Preenche a URL na aba principal e simula clique (ou chama a função diretamente)
    url_entry.delete(0, tk.END)
    url_entry.insert(0, url)
    # Talvez mudar para a aba de download se não estiver nela?
    notebook.select(download_tab)
    # Chama a função de download (sem precisar clicar no botão)
    start_download()
    # Fecha a janela de histórico?
    if history_window and history_window.winfo_exists():
        history_window.destroy()

def remove_specific_history_item(index):
    response = messagebox.askyesno("Confirmar Remoção", "Tem certeza que deseja remover este item do histórico?")
    if response:
        if clear_download_history(filter_type="specific", specific_id=index):
            log("Item removido do histórico com sucesso.", "SUCCESS")
            populate_history_listbox() # Atualiza a lista
        else:
            log("Falha ao remover item do histórico.", "ERROR")
            messagebox.showerror("Erro", "Não foi possível remover o item do histórico.")

def clear_history_action(filter_type):
    confirm_msg = "Tem certeza que deseja limpar TODO o histórico? Esta ação não pode ser desfeita."
    if filter_type == "1hour":
        confirm_msg = "Tem certeza que deseja limpar o histórico da última hora?"
    elif filter_type == "1day":
        confirm_msg = "Tem certeza que deseja limpar o histórico do último dia?"

    response = messagebox.askyesno("Confirmar Limpeza", confirm_msg)
    if response:
        if clear_download_history(filter_type=filter_type):
            log(f"Histórico limpo com sucesso (Filtro: {filter_type}).", "SUCCESS")
            populate_history_listbox() # Atualiza a lista
        else:
            log("Falha ao limpar o histórico.", "ERROR")
            messagebox.showerror("Erro", "Não foi possível limpar o histórico.")

def open_history_window():
    global history_window, history_listbox

    history_window = Toplevel(root)
    history_window.title("Histórico de Downloads")
    history_window.geometry("700x500")
    history_window.configure(bg=THEME_COLORS["background"])
    apply_theme_to_widget(history_window)

    # Frame para botões de limpeza
    clear_frame = ttk.Frame(history_window, padding="10", style="TFrame")
    clear_frame.pack(fill=tk.X)

    ttk.Button(clear_frame, text="Limpar Última Hora", command=lambda: clear_history_action("1hour"), style="TButton").pack(side=tk.LEFT, padx=5)
    ttk.Button(clear_frame, text="Limpar Último Dia", command=lambda: clear_history_action("1day"), style="TButton").pack(side=tk.LEFT, padx=5)
    ttk.Button(clear_frame, text="Limpar Tudo", command=lambda: clear_history_action("all"), style="Highlight.TButton").pack(side=tk.LEFT, padx=5)

    # Frame para a lista com scrollbar
    list_frame = ttk.Frame(history_window, padding="5", style="TFrame")
    list_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)

    history_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, style="Vertical.TScrollbar")
    history_listbox = tk.Listbox(list_frame, yscrollcommand=history_scrollbar.set,
                                 bg=THEME_COLORS["frame"], fg=THEME_COLORS["foreground"],
                                 selectbackground=THEME_COLORS["highlight"],
                                 selectforeground=THEME_COLORS["highlight_fg"],
                                 borderwidth=1, relief="sunken", height=20)
    history_scrollbar.config(command=history_listbox.yview)
    history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    history_listbox.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

    # Adiciona menu de contexto ao clicar com botão direito
    history_listbox.bind("<Button-3>", show_history_context_menu)

    populate_history_listbox()

# --- Funções da Janela de Configurações --- #

def apply_theme(theme_name):
    global CURRENT_THEME, THEME_COLORS
    if theme_name in THEME_SETTINGS["themes"]:
        CURRENT_THEME = theme_name
        THEME_COLORS = THEME_SETTINGS["themes"][CURRENT_THEME]
        THEME_SETTINGS["current_theme"] = CURRENT_THEME
        if save_theme_settings(THEME_SETTINGS):
            log(f"Tema alterado para: {theme_name}", "SUCCESS")
            apply_theme_to_all_widgets(root) # Aplica a todos os widgets abertos
            # Atualiza a janela de configurações se estiver aberta
            if 'settings_window' in globals() and settings_window.winfo_exists():
                apply_theme_to_all_widgets(settings_window)
                # Atualiza o status das dependências na janela de config
                update_dependency_status_labels(settings_window)
        else:
            log("Erro ao salvar a configuração do tema.", "ERROR")
    else:
        log(f"Tema '{theme_name}' não encontrado.", "WARNING")

def apply_theme_to_widget(widget):
    """Aplica as cores do tema atual a um widget específico e seus filhos."""
    try:
        widget_bg = THEME_COLORS["background"]
        widget_fg = THEME_COLORS["foreground"]
        disabled_fg = THEME_COLORS.get("disabled_fg", "#aaaaaa") # Cor para texto desabilitado

        # Aplica ao próprio widget
        widget.configure(bg=widget_bg)

        # Aplica a widgets específicos que têm foreground
        if isinstance(widget, (tk.Label, tk.Button, tk.Radiobutton, tk.Checkbutton, tk.Entry, tk.Text, tk.Listbox, ttk.Label, ttk.Button, ttk.Radiobutton, ttk.Checkbutton, ttk.Entry, ttk.Combobox, Menu)):
            if 'foreground' in THEME_COLORS:
                 widget.configure(foreground=widget_fg)
            # Configura cor desabilitada para tk widgets
            if isinstance(widget, (tk.Button, tk.Entry, tk.Radiobutton, tk.Checkbutton)):
                widget.configure(disabledforeground=disabled_fg)

        # Configurações específicas para ttk widgets usando estilos
        style.configure("TFrame", background=THEME_COLORS["frame"])
        style.configure("TLabel", background=widget_bg, foreground=widget_fg)
        style.configure("TButton", background=THEME_COLORS["button"], foreground=THEME_COLORS["button_fg"])
        style.map("TButton", background=[("active", THEME_COLORS["highlight"]), ("disabled", THEME_COLORS["button"])],
                  foreground=[("active", THEME_COLORS["highlight_fg"]), ("disabled", disabled_fg)])
        style.configure("Highlight.TButton", background=THEME_COLORS["highlight"], foreground=THEME_COLORS["highlight_fg"])
        style.map("Highlight.TButton", background=[("active", THEME_COLORS["button"]), ("disabled", THEME_COLORS["highlight"])],
                  foreground=[("active", THEME_COLORS["button_fg"]), ("disabled", disabled_fg)])
        style.configure("TEntry", fieldbackground=THEME_COLORS["entry"], foreground=THEME_COLORS["entry_fg"])
        style.map("TEntry", foreground=[("disabled", disabled_fg)])
        style.configure("TCombobox", fieldbackground=THEME_COLORS["entry"], foreground=THEME_COLORS["entry_fg"], selectbackground=THEME_COLORS["highlight"], selectforeground=THEME_COLORS["highlight_fg"])
        style.map("TCombobox", foreground=[("disabled", disabled_fg), ("readonly", THEME_COLORS["entry_fg"])],
                  fieldbackground=[("readonly", THEME_COLORS["entry"])])
        # Explicitly set listbox style for dropdown
        widget.tk.eval(f"option add *TCombobox*Listbox.background {THEME_COLORS['entry']}")
        widget.tk.eval(f"option add *TCombobox*Listbox.foreground {THEME_COLORS['entry_fg']}")
        widget.tk.eval(f"option add *TCombobox*Listbox.selectBackground {THEME_COLORS['highlight']}")
        widget.tk.eval(f"option add *TCombobox*Listbox.selectForeground {THEME_COLORS['highlight_fg']}")
        style.configure("TCheckbutton", background=widget_bg, foreground=widget_fg)
        style.map("TCheckbutton", foreground=[("disabled", disabled_fg)])
        style.configure("TRadiobutton", background=widget_bg, foreground=widget_fg)
        style.map("TRadiobutton", foreground=[("disabled", disabled_fg)])
        style.configure("Vertical.TScrollbar", background=THEME_COLORS["button"], troughcolor=THEME_COLORS["frame"])
        style.configure("TNotebook", background=widget_bg)
        style.configure("TNotebook.Tab", background=THEME_COLORS["button"], foreground=THEME_COLORS["button_fg"], padding=[5, 2])
        style.map("TNotebook.Tab", background=[("selected", THEME_COLORS["highlight"])], foreground=[("selected", THEME_COLORS["highlight_fg"])])
        style.configure("TLabelframe", background=widget_bg)
        style.configure("TLabelframe.Label", background=widget_bg, foreground=widget_fg)

        # Configurações específicas para widgets tk
        if isinstance(widget, tk.Listbox):
            widget.configure(
                bg=THEME_COLORS["frame"],
                fg=widget_fg,
                selectbackground=THEME_COLORS["highlight"],
                selectforeground=THEME_COLORS["highlight_fg"],
            )
        if isinstance(widget, tk.Text):
            widget.configure(bg=THEME_COLORS["log_bg"], fg=widget_fg)
        if isinstance(widget, tk.Menu):
            widget.configure(
                bg=THEME_COLORS["button"],
                fg=THEME_COLORS["button_fg"],
                activebackground=THEME_COLORS["highlight"],
                activeforeground=THEME_COLORS["highlight_fg"],
                disabledforeground=disabled_fg,
            )
        if isinstance(widget, tk.LabelFrame):
            widget.configure(bg=widget_bg, fg=widget_fg)

        # Aplica recursivamente aos filhos
        for child in widget.winfo_children():
            apply_theme_to_widget(child)

    except tk.TclError:
        # Ignora erros de widgets que não suportam certas configurações
        pass
    except Exception as e:
        log(f"Erro inesperado ao aplicar tema em {widget}: {e}", "ERROR")

def apply_theme_to_all_widgets(root_widget):
    """Aplica o tema atual a todos os widgets a partir de um widget raiz."""
    apply_theme_to_widget(root_widget)
    # Aplica ao log_text especificamente
    if 'log_text' in globals() and log_text and log_text.winfo_exists():
        log_text.config(bg=THEME_COLORS["log_bg"], fg=THEME_COLORS["log_fg"])
        # Reaplica cores das tags do log
        for level, color in LOG_COLORS.items():
            log_text.tag_config(level, foreground=color)
        log_text.tag_config("TIMESTAMP", foreground=THEME_COLORS.get("timestamp_fg", "#888888")) # Cor do timestamp

def update_dependency_status_labels(parent_window):
    """Atualiza as labels de status das dependências na janela de configurações."""
    try:
        ytdlp_status_label = parent_window.nametowidget("dep_status_frame.ytdlp_status")
        ffmpeg_status_label = parent_window.nametowidget("dep_status_frame.ffmpeg_status")
        spleeter_status_label = parent_window.nametowidget("dep_status_frame.spleeter_status")
        requests_status_label = parent_window.nametowidget("dep_status_frame.requests_status")
        pillow_status_label = parent_window.nametowidget("dep_status_frame.pillow_status")
        mutagen_status_label = parent_window.nametowidget("dep_status_frame.mutagen_status")

        ytdlp_status_label.config(text="Encontrado" if YTDLP_EXISTS else "Não Encontrado",
                                  foreground="green" if YTDLP_EXISTS else "red")
        ffmpeg_status_label.config(text="Encontrado" if FFMPEG_EXISTS else "Não Encontrado",
                                   foreground="green" if FFMPEG_EXISTS else "red")
        spleeter_status_label.config(text="Disponível" if SPLEETER_AVAILABLE else "Indisponível",
                                     foreground="green" if SPLEETER_AVAILABLE else "orange") # Laranja para opcional
        requests_status_label.config(text="Disponível" if REQUESTS_AVAILABLE else "Não Encontrado",
                                     foreground="green" if REQUESTS_AVAILABLE else "red")
        pillow_status_label.config(text="Disponível" if PILLOW_AVAILABLE else "Não Encontrado",
                                   foreground="green" if PILLOW_AVAILABLE else "red")
        mutagen_status_label.config(text="Disponível" if MUTAGEN_AVAILABLE else "Não Encontrado",
                                    foreground="green" if MUTAGEN_AVAILABLE else "red")
    except KeyError:
        log("Erro ao encontrar labels de status de dependência na janela de configurações.", "WARNING")
    except Exception as e:
        log(f"Erro ao atualizar status de dependências: {e}", "ERROR")

def open_settings_window():
    global settings_window

    settings_window = Toplevel(root)
    settings_window.title("Configurações")
    settings_window.geometry("450x400") # Aumentado para caber mais dependências
    settings_window.configure(bg=THEME_COLORS["background"])
    apply_theme_to_widget(settings_window)

    notebook_settings = ttk.Notebook(settings_window, style="TNotebook")

    # --- Aba Temas ---
    theme_tab = ttk.Frame(notebook_settings, padding="10", style="TFrame")
    notebook_settings.add(theme_tab, text='Temas e Aparência')

    theme_frame = ttk.LabelFrame(theme_tab, text="Selecionar Tema", padding="10", style="TLabelframe")
    theme_frame.pack(pady=10, padx=10, fill="x")

    theme_var = StringVar(value=CURRENT_THEME)

    # Cria Radiobuttons para cada tema disponível
    themes_available = list(THEME_SETTINGS["themes"].keys())
    for theme_name in themes_available:
        rb = ttk.Radiobutton(theme_frame, text=theme_name.capitalize(), variable=theme_var,
                             value=theme_name, command=lambda t=theme_name: apply_theme(t), style="TRadiobutton")
        rb.pack(anchor="w", pady=2)

    # --- Aba Dependências ---
    dep_tab = ttk.Frame(notebook_settings, padding="10", style="TFrame")
    notebook_settings.add(dep_tab, text='Dependências')

    dep_status_frame = ttk.LabelFrame(dep_tab, text="Status das Dependências", padding="10", style="TLabelframe", name="dep_status_frame")
    dep_status_frame.pack(pady=10, padx=10, fill="x")

    # Labels de Status
    row_idx = 0
    ttk.Label(dep_status_frame, text="yt-dlp (Download):", style="TLabel").grid(row=row_idx, column=0, sticky="w", pady=3)
    ytdlp_status_label = ttk.Label(dep_status_frame, text="Verificando...", style="TLabel", name="ytdlp_status")
    ytdlp_status_label.grid(row=row_idx, column=1, sticky="w", padx=5)
    row_idx += 1

    ttk.Label(dep_status_frame, text="FFmpeg (Corte/Conversão):", style="TLabel").grid(row=row_idx, column=0, sticky="w", pady=3)
    ffmpeg_status_label = ttk.Label(dep_status_frame, text="Verificando...", style="TLabel", name="ffmpeg_status")
    ffmpeg_status_label.grid(row=row_idx, column=1, sticky="w", padx=5)
    row_idx += 1

    ttk.Label(dep_status_frame, text="Requests (Miniaturas/Updates):", style="TLabel").grid(row=row_idx, column=0, sticky="w", pady=3)
    requests_status_label = ttk.Label(dep_status_frame, text="Verificando...", style="TLabel", name="requests_status")
    requests_status_label.grid(row=row_idx, column=1, sticky="w", padx=5)
    row_idx += 1

    ttk.Label(dep_status_frame, text="Pillow (Miniaturas):", style="TLabel").grid(row=row_idx, column=0, sticky="w", pady=3)
    pillow_status_label = ttk.Label(dep_status_frame, text="Verificando...", style="TLabel", name="pillow_status")
    pillow_status_label.grid(row=row_idx, column=1, sticky="w", padx=5)
    row_idx += 1

    ttk.Label(dep_status_frame, text="Mutagen (Metadados MP3):", style="TLabel").grid(row=row_idx, column=0, sticky="w", pady=3)
    mutagen_status_label = ttk.Label(dep_status_frame, text="Verificando...", style="TLabel", name="mutagen_status")
    mutagen_status_label.grid(row=row_idx, column=1, sticky="w", padx=5)
    row_idx += 1

    ttk.Label(dep_status_frame, text="Spleeter (Remover Guitarra - Opcional):", style="TLabel").grid(row=row_idx, column=0, sticky="w", pady=3)
    spleeter_status_label = ttk.Label(dep_status_frame, text="Verificando...", style="TLabel", name="spleeter_status")
    spleeter_status_label.grid(row=row_idx, column=1, sticky="w", padx=5)
    row_idx += 1

    # Botão para verificar novamente
    # check_dep_button = ttk.Button(dep_tab, text="Verificar Dependências Novamente", command=lambda: update_dependency_status_labels(settings_window), style="TButton")
    # check_dep_button.pack(pady=10)

    notebook_settings.pack(expand=True, fill="both", padx=5, pady=5)

    # Atualiza o status inicial
    update_dependency_status_labels(settings_window)

# --- Funções da Janela "Sobre" --- #

def open_about_window():
    about_window = Toplevel(root)
    about_window.title("Sobre YouTube Downloader")
    about_window.geometry("450x450") # Aumentado para mais dependências
    about_window.resizable(False, False)
    about_window.configure(bg=THEME_COLORS["background"])
    apply_theme_to_widget(about_window)

    about_frame = ttk.Frame(about_window, padding="15", style="TFrame")
    about_frame.pack(expand=True, fill="both")

    title_label = ttk.Label(about_frame, text="YouTube Downloader", font=("Segoe UI", 16, "bold"), style="TLabel")
    title_label.pack(pady=(0, 10))

    version_label = ttk.Label(about_frame, text=f"Versão: {APP_VERSION}", style="TLabel")
    version_label.pack(pady=2)

    date_label = ttk.Label(about_frame, text=f"Data da Versão: {APP_CREATION_DATE}", style="TLabel")
    date_label.pack(pady=2)

    separator = ttk.Separator(about_frame, orient='horizontal')
    separator.pack(fill='x', pady=10)

    info_text = Text(about_frame, wrap="word", height=14, relief="flat",
                     bg=THEME_COLORS["background"], fg=THEME_COLORS["foreground"],
                     font=("Segoe UI", 10))
    info_text.pack(fill="x", pady=5)
    info_text.insert(tk.END, "Desenvolvido por: Manus AI (assistente virtual)\n")
    info_text.insert(tk.END, "Linguagem: Python 3\n")
    info_text.insert(tk.END, "Interface Gráfica: Tkinter (ttk)\n\n")
    info_text.insert(tk.END, "Dependências Externas:\n")
    info_text.insert(tk.END, f" - yt-dlp: {'OK' if YTDLP_EXISTS else 'Não encontrado'}\n")
    info_text.insert(tk.END, f" - FFmpeg: {'OK' if FFMPEG_EXISTS else 'Não encontrado'}\n\n")
    info_text.insert(tk.END, "Bibliotecas Python Essenciais:\n")
    info_text.insert(tk.END, f" - requests: {'OK' if REQUESTS_AVAILABLE else 'Não encontrada'}\n")
    info_text.insert(tk.END, f" - Pillow: {'OK' if PILLOW_AVAILABLE else 'Não encontrada'}\n")
    info_text.insert(tk.END, f" - mutagen: {'OK' if MUTAGEN_AVAILABLE else 'Não encontrada'}\n")
    info_text.insert(tk.END, f" - pyperclip: {'OK' if PYPERCLIP_AVAILABLE else 'Não encontrada (opcional)'}\n\n")
    info_text.insert(tk.END, "Bibliotecas Python Opcionais:\n")
    info_text.insert(tk.END, f" - Spleeter: {'Disponível' if SPLEETER_AVAILABLE else 'Indisponível'}\n")

    info_text.config(state="disabled") # Torna o texto não editável

    close_button = ttk.Button(about_frame, text="Fechar", command=about_window.destroy, style="Highlight.TButton")
    close_button.pack(pady=(15, 0))

# --- Funções de Atualização Automática --- #

# URL para verificar a versão mais recente (Substitua pela URL real do seu version.json no GitHub/servidor)
# Exemplo: "https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPOSITORIO/main/version.json"
UPDATE_CHECK_URL = "" # Deixe vazio ou coloque a URL real

def check_for_updates(show_no_update_message=False):
    if not REQUESTS_AVAILABLE:
        log("Verificação de atualizações pulada: biblioteca 'requests' não encontrada.", "WARNING")
        if show_no_update_message:
            messagebox.showwarning("Verificar Atualizações", "Não é possível verificar atualizações.\nA biblioteca 'requests' não está instalada.")
        return

    if not UPDATE_CHECK_URL:
        log("URL de verificação de atualização não configurada.", "WARNING")
        if show_no_update_message:
             messagebox.showinfo("Verificar Atualizações", "A URL para verificar atualizações não está configurada.")
        return

    log("Verificando atualizações...", "INFO")
    try:
        response = requests.get(UPDATE_CHECK_URL, timeout=10)
        response.raise_for_status()
        latest_version_info = response.json()

        # Compara versão local com a mais recente
        latest_version_str = f"{latest_version_info['major']}.{latest_version_info['minor']}.{latest_version_info['patch']}"
        local_version_str = f"{VERSION_INFO['major']}.{VERSION_INFO['minor']}.{VERSION_INFO['patch']}"
        latest_build = latest_version_info.get('build', 0)
        local_build = VERSION_INFO.get('build', 0)

        # Comparação simples (pode ser melhorada com bibliotecas como packaging.version)
        update_available = False
        if latest_version_info['major'] > VERSION_INFO['major'] or \
           (latest_version_info['major'] == VERSION_INFO['major'] and latest_version_info['minor'] > VERSION_INFO['minor']) or \
           (latest_version_info['major'] == VERSION_INFO['major'] and latest_version_info['minor'] == VERSION_INFO['minor'] and latest_version_info['patch'] > VERSION_INFO['patch']) or \
           (latest_version_str == local_version_str and latest_build > local_build):
            update_available = True

        if update_available:
            log(f"Nova versão disponível: {latest_version_str} (Build {latest_build})", "SUCCESS")
            release_notes = latest_version_info.get("release_notes", "Nenhuma nota de versão disponível.")
            changes = "\n".join([f" - {change}" for change in latest_version_info.get("changes", [])])
            download_url = latest_version_info.get("download_url", "")

            msg = f"Uma nova versão ({latest_version_str} Build {latest_build}) está disponível!\n\nNotas da Versão:\n{release_notes}\n\nNovidades:\n{changes}\n\nDeseja visitar a página de download agora?"

            response = messagebox.askyesno("Atualização Disponível", msg)
            if response and download_url:
                webbrowser.open_new(download_url)
            elif response and not download_url:
                 messagebox.showinfo("Atualização Disponível", "URL de download não fornecida na informação de versão.")
        else:
            log("Você já está usando a versão mais recente.", "INFO")
            if show_no_update_message:
                messagebox.showinfo("Verificar Atualizações", "Você já está usando a versão mais recente do aplicativo.")

    except requests.exceptions.RequestException as e:
        log(f"Erro ao verificar atualizações (rede): {e}", "ERROR")
        if show_no_update_message:
             messagebox.showerror("Erro de Rede", f"Não foi possível verificar atualizações.\nErro: {e}")
    except json.JSONDecodeError as e:
         log(f"Erro ao decodificar resposta de atualização: {e}", "ERROR")
         if show_no_update_message:
             messagebox.showerror("Erro de Resposta", "A resposta do servidor de atualização não é válida.")
    except Exception as e:
        log(f"Erro inesperado ao verificar atualizações: {e}", "ERROR")
        if show_no_update_message:
             messagebox.showerror("Erro Inesperado", f"Ocorreu um erro inesperado ao verificar atualizações.\nErro: {e}")

# --- Funções da Aba de Manipulação de Mídia --- #

def select_media_file(entry_widget):
    filetypes = [("Arquivos de Mídia", "*.mp4 *.mp3 *.mkv *.avi *.wav *.flac"), ("Todos os Arquivos", "*.*")]
    filepath = filedialog.askopenfilename(title="Selecionar Arquivo de Mídia", filetypes=filetypes)
    if filepath:
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, filepath)
        log(f"Arquivo de mídia selecionado: {filepath}", "INFO")

def run_spleeter_thread(input_path):
    # Verificação dupla: se o botão estava habilitado mas Spleeter não está realmente ok
    if not SPLEETER_AVAILABLE:
        log("Tentativa de usar Spleeter, mas não está disponível.", "ERROR")
        messagebox.showerror("Spleeter Indisponível", "A funcionalidade de remoção de guitarra não está disponível.\nVerifique a instalação do Spleeter e se o comando está no PATH.")
        # Garante que o botão e status sejam atualizados
        if spleeter_button.winfo_exists():
            spleeter_button.config(state=tk.DISABLED)
        if spleeter_status_label.winfo_exists():
            spleeter_status_label.config(text="Spleeter indisponível", foreground="red")
        return
    if not check_ffmpeg_dependency():
        return  # FFmpeg também é necessário para combinar

    if not input_path or not os.path.exists(input_path):
        log("Arquivo de entrada inválido para Spleeter.", "ERROR")
        messagebox.showerror("Erro Spleeter", "Selecione um arquivo de áudio válido primeiro.")
        return

    log(f"Iniciando separação de instrumentos (Spleeter) para: {os.path.basename(input_path)}", "HIGHLIGHT")
    spleeter_button.config(state=tk.DISABLED)
    spleeter_status_label.config(text="Processando com Spleeter...")
    # Limpa pasta de saída anterior?
    if os.path.exists(SPLEETER_OUTPUT_DIR):
        try:
            shutil.rmtree(SPLEETER_OUTPUT_DIR)
        except Exception as e:
            log(f"Erro ao limpar pasta Spleeter antiga: {e}", "WARNING")
    os.makedirs(SPLEETER_OUTPUT_DIR, exist_ok=True)

    try:
        # Comando Spleeter para separar em 4 stems (vocal, baixo, bateria, outros)
        command = [
            "spleeter", "separate",
            "-p", "spleeter:4stems", # Modelo de 4 stems
            "-o", SPLEETER_OUTPUT_DIR, # Pasta de saída
            input_path
        ]
        log(f"Executando comando Spleeter: {' '.join(command)}", "INFO")
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        result = subprocess.run(command, capture_output=True, text=True, check=False, startupinfo=startupinfo)

        if result.returncode != 0:
            log(f"Erro durante a execução do Spleeter (código {result.returncode}):\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}", "ERROR")
            raise Exception(f"Spleeter falhou com código {result.returncode}. Verifique o log e a instalação do Spleeter.")
        else:
            log(f"Spleeter processou o arquivo com sucesso. Saída em: {SPLEETER_OUTPUT_DIR}", "SUCCESS")
            # Agora precisamos combinar os stems desejados (vocal, baixo, bateria) para ter o áudio sem guitarra
            output_base = os.path.splitext(os.path.basename(input_path))[0]
            spleeter_result_folder = os.path.join(SPLEETER_OUTPUT_DIR, output_base)

            vocals_path = os.path.join(spleeter_result_folder, "vocals.wav")
            bass_path = os.path.join(spleeter_result_folder, "bass.wav")
            drums_path = os.path.join(spleeter_result_folder, "drums.wav")
            # other_path = os.path.join(spleeter_result_folder, "other.wav") # Contém a guitarra

            # Verifica se os arquivos existem
            stems_to_combine = []
            if os.path.exists(vocals_path):
                stems_to_combine.append(vocals_path)
            if os.path.exists(bass_path):
                stems_to_combine.append(bass_path)
            if os.path.exists(drums_path):
                stems_to_combine.append(drums_path)

            if len(stems_to_combine) < 1:
                 log("Nenhum stem (vocal, baixo, bateria) encontrado após processamento Spleeter.", "ERROR")
                 raise Exception("Falha ao encontrar stems para combinar.")

            # Combina os stems usando FFmpeg
            output_no_guitar_filename = f"{output_base}_sem_guitarra.mp3" # Salvar como MP3
            output_no_guitar_path = os.path.join(PROCESSED_DIR, output_no_guitar_filename)

            if not check_ffmpeg_dependency():
                raise Exception("FFmpeg necessário para combinar stems.")

            ffmpeg_combine_cmd = [FFMPEG_PATH, '-y']
            for stem_path in stems_to_combine:
                ffmpeg_combine_cmd.extend(['-i', stem_path])

            # Mapeia os inputs para mixar
            ffmpeg_combine_cmd.extend([
                '-filter_complex',
                f"amix=inputs={len(stems_to_combine)}:duration=longest",
                '-c:a', 'libmp3lame', # Codec MP3
                '-q:a', '2', # Qualidade MP3 (0-9, menor é melhor)
                output_no_guitar_path
            ])

            log(f"Combinando stems com FFmpeg: {' '.join(ffmpeg_combine_cmd)}", "INFO")
            result_combine = subprocess.run(ffmpeg_combine_cmd, capture_output=True, text=True, check=False, startupinfo=startupinfo)

            if result_combine.returncode != 0:
                log(f"Erro ao combinar stems com FFmpeg: {result_combine.stderr}", "ERROR")
                raise Exception("Falha ao combinar stems com FFmpeg.")
            else:
                log(f"Arquivo sem guitarra criado com sucesso: {output_no_guitar_path}", "SUCCESS")
                messagebox.showinfo("Spleeter Concluído", f"Processamento concluído!\n\nArquivo sem guitarra salvo em:\n{output_no_guitar_path}")
                # Limpa a pasta temporária do spleeter?
                # try: shutil.rmtree(SPLEETER_OUTPUT_DIR) except Exception: pass

    except Exception as e:
        log(f"Erro no processo Spleeter: {e}", "ERROR")
        messagebox.showerror("Erro Spleeter", f"Ocorreu um erro durante o processamento:\n{e}")

    finally:
        # Reabilita o botão apenas se Spleeter estiver realmente disponível
        if SPLEETER_AVAILABLE and spleeter_button.winfo_exists():
             spleeter_button.config(state=tk.NORMAL)
        elif not SPLEETER_AVAILABLE and spleeter_button.winfo_exists():
             spleeter_button.config(state=tk.DISABLED) # Mantém desabilitado

        if spleeter_status_label.winfo_exists():
            spleeter_status_label.config(text="Pronto." if SPLEETER_AVAILABLE else "Spleeter indisponível",
                                         foreground=THEME_COLORS["foreground"] if SPLEETER_AVAILABLE else "red")

def start_spleeter_processing():
    input_path = spleeter_entry.get().strip()
    run_in_thread(run_spleeter_thread, args=(input_path,))

def split_video_for_stories_thread(input_path, segment_duration):
    if not check_ffmpeg_dependency():
        return
    if not input_path or not os.path.exists(input_path):
        log("Arquivo de entrada inválido para divisão.", "ERROR")
        messagebox.showerror("Erro Divisão", "Selecione um arquivo de vídeo válido primeiro.")
        return

    log(f"Iniciando divisão para Instagram Stories ({segment_duration}s): {os.path.basename(input_path)}", "HIGHLIGHT")
    split_button.config(state=tk.DISABLED)
    split_status_label.config(text=f"Dividindo em partes de {segment_duration}s...")

    try:
        # 1. Obter duração total do vídeo
        total_duration = get_video_duration(input_path)
        if total_duration is None:
            raise Exception("Não foi possível obter a duração do vídeo.")

        # 2. Calcular número de partes
        num_parts = math.ceil(total_duration / segment_duration)
        log(f"Duração total: {total_duration}s. Dividindo em {num_parts} partes de {segment_duration}s.", "INFO")

        # 3. Criar pasta de saída específica para este vídeo
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_folder = os.path.join(INSTA_STORIES_DIR, sanitize_filename(base_name))
        os.makedirs(output_folder, exist_ok=True)

        # 4. Loop para dividir com FFmpeg
        errors = 0
        for i in range(num_parts):
            part_num = i + 1
            start_time_part = i * segment_duration
            output_filename = f"{base_name}_Parte_{part_num:02d}.mp4" # Ex: video_Parte_01.mp4
            output_filepath = os.path.join(output_folder, output_filename)

            split_status_label.config(text=f"Processando parte {part_num}/{num_parts}...")

            command = [
                FFMPEG_PATH, '-y',
                '-ss', str(start_time_part), # Tempo inicial da parte
                '-i', input_path,
                '-t', str(segment_duration), # Duração da parte
                '-c', 'copy', # Tenta copiar codecs para rapidez
                output_filepath
            ]

            log(f"Executando FFmpeg para parte {part_num}: {' '.join(command)}", "INFO")
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            result = subprocess.run(command, capture_output=True, text=True, check=False, startupinfo=startupinfo)

            if result.returncode != 0:
                log(f"Erro ao dividir parte {part_num} (código {result.returncode}): {result.stderr}", "ERROR")
                # Tentar re-encodar se a cópia falhar
                log(f"Tentando dividir parte {part_num} novamente (re-encode)...", "WARNING")
                command_recode = [
                    FFMPEG_PATH, '-y',
                    '-ss', str(start_time_part),
                    '-i', input_path,
                    '-t', str(segment_duration),
                    # Sem '-c copy'
                    output_filepath
                ]
                result_recode = subprocess.run(command_recode, capture_output=True, text=True, check=False, startupinfo=startupinfo)
                if result_recode.returncode != 0:
                    log(f"Erro ao dividir parte {part_num} (mesmo re-encodando): {result_recode.stderr}", "ERROR")
                    errors += 1
                    # Continuar para as próximas partes?
                else:
                    log(f"Parte {part_num} dividida com sucesso (re-encode).", "SUCCESS")
            else:
                log(f"Parte {part_num} dividida com sucesso.", "SUCCESS")

        # 5. Finalização
        final_message = f"Divisão concluída! {num_parts - errors} partes salvas em:\n{output_folder}"
        if errors > 0:
            final_message += f"\n{errors} partes falharam (verifique o log)."
            log(final_message, "WARNING")
            messagebox.showwarning("Divisão Concluída com Erros", final_message)
        else:
            log(final_message, "SUCCESS")
            messagebox.showinfo("Divisão Concluída", final_message)
            # Abrir pasta automaticamente?
            open_folder_path(output_folder)

    except Exception as e:
        log(f"Erro no processo de divisão: {e}", "ERROR")
        messagebox.showerror("Erro Divisão", f"Ocorreu um erro durante a divisão:\n{e}")

    finally:
        # Reabilita botão apenas se FFmpeg estiver ok
        if FFMPEG_EXISTS and split_button.winfo_exists():
            split_button.config(state=tk.NORMAL)
        elif not FFMPEG_EXISTS and split_button.winfo_exists():
            split_button.config(state=tk.DISABLED)

        if split_status_label.winfo_exists():
            split_status_label.config(text="Pronto." if FFMPEG_EXISTS else "FFmpeg indisponível",
                                      foreground=THEME_COLORS["foreground"] if FFMPEG_EXISTS else "red")

def start_video_split():
    input_path = split_entry.get().strip()
    try:
        segment_duration = int(split_duration_var.get())
    except ValueError:
        messagebox.showerror("Erro", "Duração inválida selecionada.")
        return

    run_in_thread(split_video_for_stories_thread, args=(input_path, segment_duration))

# --- Criação da Interface Gráfica --- #

root = tk.Tk()
root.title(f"YouTube Downloader - {APP_VERSION}")
root.geometry("800x650")

# Aplica estilo ttk e configura temas
style = ttk.Style()
style.theme_use('clam') # Base theme (clam, alt, default, classic)
# Configura estilos antes de criar widgets
apply_theme_to_all_widgets(root) # Aplica tema inicial

# --- Menu Superior --- #
menubar = Menu(root)
root.config(menu=menubar)
apply_theme_to_widget(menubar)

# Menu Arquivo
file_menu = Menu(menubar, tearoff=0)
apply_theme_to_widget(file_menu)
file_menu.add_command(label="Baixar Vídeo/Playlist", command=start_download)
file_menu.add_command(label="Abrir Local do Último Download", command=open_download_folder)
file_menu.add_command(label="Ver Histórico", command=open_history_window)
file_menu.add_separator()
file_menu.add_command(label="Sair", command=root.quit)
menubar.add_cascade(label="Arquivo", menu=file_menu)

# Menu Configurações
settings_menu = Menu(menubar, tearoff=0)
apply_theme_to_widget(settings_menu)
settings_menu.add_command(label="Preferências", command=open_settings_window)
menubar.add_cascade(label="Configurações", menu=settings_menu)

# Menu Ajuda
help_menu = Menu(menubar, tearoff=0)
apply_theme_to_widget(help_menu)
help_menu.add_command(label="Verificar Atualizações", command=lambda: check_for_updates(show_no_update_message=True))
help_menu.add_separator()
help_menu.add_command(label="Sobre", command=open_about_window)
menubar.add_cascade(label="Ajuda", menu=help_menu)

# --- Frame Principal (Contém Notebook e Log) --- #
main_frame = ttk.Frame(root, style="TFrame")
main_frame.pack(expand=True, fill=tk.BOTH)

# --- Abas (Notebook) --- #
notebook = ttk.Notebook(main_frame, style="TNotebook")
notebook.pack(expand=True, fill="both", padx=5, pady=5)

# --- Aba Download --- #
download_tab = ttk.Frame(notebook, padding="10", style="TFrame")
notebook.add(download_tab, text=' Download ') # Espaços para padding

# Frame URL
url_frame = ttk.Frame(download_tab, padding="5", style="TFrame")
url_frame.pack(fill=tk.X, pady=5)
ttk.Label(url_frame, text="URL YouTube:", style="TLabel").pack(side=tk.LEFT, padx=5)
url_entry = ttk.Entry(url_frame, width=60, style="TEntry")
url_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

# Botão Colar (opcional)
def paste_from_clipboard():
    if PYPERCLIP_AVAILABLE:
        try:
            clipboard_content = pyperclip.paste()
            url_entry.delete(0, tk.END)
            url_entry.insert(0, clipboard_content)
            log("URL colada da área de transferência (pyperclip).", "INFO")
            return
        except Exception as e:
            log(f"Erro ao colar com pyperclip: {e}", "WARNING")
    # Fallback para Tkinter clipboard
    try:
        clipboard_content = root.clipboard_get()
        url_entry.delete(0, tk.END)
        url_entry.insert(0, clipboard_content)
        log("URL colada da área de transferência (Tk fallback).", "INFO")
    except tk.TclError:
        log("Não foi possível acessar a área de transferência.", "ERROR")
        messagebox.showerror("Erro Clipboard", "Não foi possível acessar a área de transferência.")

paste_button = ttk.Button(url_frame, text="Colar", command=paste_from_clipboard, style="TButton")
# Desabilita se pyperclip não estiver disponível (Tkinter fallback pode não ser ideal)
if not PYPERCLIP_AVAILABLE:
    # paste_button.config(state=tk.DISABLED) # Ou deixa habilitado e usa o fallback
    pass
paste_button.pack(side=tk.LEFT, padx=5)

# Frame Opções
options_frame = ttk.Frame(download_tab, padding="5", style="TFrame")
options_frame.pack(fill=tk.X, pady=5)

# Formato
ttk.Label(options_frame, text="Formato:", style="TLabel").pack(side=tk.LEFT, padx=(5, 2))
format_var = StringVar(value="MP4")
format_menu = ttk.Combobox(options_frame, textvariable=format_var, values=["MP4", "MP3"], state="readonly", width=8, style="TCombobox")
format_menu.pack(side=tk.LEFT, padx=(0, 10))

# Qualidade
ttk.Label(options_frame, text="Qualidade:", style="TLabel").pack(side=tk.LEFT, padx=(10, 2))
quality_var = StringVar(value="best")
quality_menu = ttk.Combobox(options_frame, textvariable=quality_var, values=["best", "1080", "720", "480", "360", "128K", "192K", "256K", "320K"], width=10, style="TCombobox")
quality_menu.pack(side=tk.LEFT, padx=(0, 10))

# Frame Corte
cut_frame = ttk.LabelFrame(download_tab, text="Cortar Vídeo/Áudio (Opcional - Requer FFmpeg)", padding="10", style="TLabelframe")
cut_frame.pack(fill=tk.X, pady=10, padx=5)

ttk.Label(cut_frame, text="Início (HH:MM:SS):", style="TLabel").grid(row=0, column=0, padx=5, pady=5, sticky="w")
start_entry = ttk.Entry(cut_frame, width=10, style="TEntry", state=tk.NORMAL if FFMPEG_EXISTS else tk.DISABLED)
start_entry.grid(row=0, column=1, padx=5, pady=5)
start_label_desc = ttk.Label(cut_frame, text="", style="TLabel")
start_label_desc.grid(row=0, column=2, padx=5, pady=5, sticky="w")

ttk.Label(cut_frame, text="Fim (HH:MM:SS):", style="TLabel").grid(row=1, column=0, padx=5, pady=5, sticky="w")
end_entry = ttk.Entry(cut_frame, width=10, style="TEntry", state=tk.NORMAL if FFMPEG_EXISTS else tk.DISABLED)
end_entry.grid(row=1, column=1, padx=5, pady=5)
end_label_desc = ttk.Label(cut_frame, text="", style="TLabel")
end_label_desc.grid(row=1, column=2, padx=5, pady=5, sticky="w")

# Atualiza descrições ao sair dos campos ou pressionar Enter
start_entry.bind("<FocusOut>", update_time_labels)
start_entry.bind("<Return>", update_time_labels)
end_entry.bind("<FocusOut>", update_time_labels)
end_entry.bind("<Return>", update_time_labels)

# Frame Botões Download
button_frame = ttk.Frame(download_tab, padding="10", style="TFrame")
button_frame.pack(fill=tk.X, pady=10)

download_button = ttk.Button(button_frame, text="Baixar Vídeo", command=start_download, style="Highlight.TButton", state=tk.NORMAL if YTDLP_EXISTS else tk.DISABLED)
download_button.pack(side=tk.LEFT, padx=10)

playlist_button = ttk.Button(button_frame, text="Baixar Playlist", command=lambda: open_playlist_window(url_entry.get().strip()) if "list=" in url_entry.get().strip() else messagebox.showinfo("URL Inválida", "Insira uma URL de playlist válida."), style="TButton", state=tk.NORMAL if YTDLP_EXISTS else tk.DISABLED)
playlist_button.pack(side=tk.LEFT, padx=10)

open_folder_button = ttk.Button(button_frame, text="Abrir Local", command=open_download_folder, style="TButton")
open_folder_button.pack(side=tk.LEFT, padx=10)

history_button = ttk.Button(button_frame, text="Histórico", command=open_history_window, style="TButton")
history_button.pack(side=tk.RIGHT, padx=10)

# Barra de Progresso
progress_bar = ttk.Progressbar(download_tab, orient='horizontal', mode='indeterminate', length=300)
progress_bar.pack(pady=10, fill=tk.X, padx=5)

# --- Aba Manipulação de Mídia --- #
media_tab = ttk.Frame(notebook, padding="10", style="TFrame")
notebook.add(media_tab, text=' Manipular Mídia ')

# --- Seção: Remover Guitarra (Spleeter) ---
spleeter_frame = ttk.LabelFrame(media_tab, text="Remover Guitarra (Experimental - Requer Spleeter e FFmpeg)", padding="10", style="TLabelframe")
spleeter_frame.pack(fill=tk.X, pady=10, padx=5)

ttk.Label(spleeter_frame, text="Arquivo de Áudio (MP3, WAV):", style="TLabel").grid(row=0, column=0, padx=5, pady=5, sticky="w")
spleeter_entry = ttk.Entry(spleeter_frame, width=50, style="TEntry")
spleeter_entry.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
spleeter_select_button = ttk.Button(spleeter_frame, text="Selecionar...", command=lambda: select_media_file(spleeter_entry), style="TButton")
spleeter_select_button.grid(row=1, column=1, padx=5, pady=5)

spleeter_button = ttk.Button(spleeter_frame, text="Remover Guitarra", command=start_spleeter_processing, style="Highlight.TButton")
spleeter_button.grid(row=2, column=0, columnspan=2, pady=10)

spleeter_status_label = ttk.Label(spleeter_frame, text="Verificando...", style="TLabel")
spleeter_status_label.grid(row=3, column=0, columnspan=2, pady=5)

# Desabilita se Spleeter ou FFmpeg não estiverem disponíveis
if not SPLEETER_AVAILABLE or not FFMPEG_EXISTS:
    spleeter_button.config(state=tk.DISABLED)
    spleeter_status_label.config(text="Spleeter ou FFmpeg indisponível", foreground="red")
    spleeter_entry.config(state=tk.DISABLED)
    spleeter_select_button.config(state=tk.DISABLED)
    ttk.Label(spleeter_frame, text="Verifique a instalação do Spleeter e FFmpeg.", foreground="red", style="TLabel").grid(row=4, column=0, columnspan=2)
else:
    spleeter_status_label.config(text="Pronto.")

# --- Seção: Dividir Vídeo para Stories --- #
split_frame = ttk.LabelFrame(media_tab, text="Dividir Vídeo para Instagram Stories (Requer FFmpeg)", padding="10", style="TLabelframe")
split_frame.pack(fill=tk.X, pady=10, padx=5)

ttk.Label(split_frame, text="Arquivo de Vídeo (MP4, MKV, etc.):", style="TLabel").grid(row=0, column=0, padx=5, pady=5, sticky="w")
split_entry = ttk.Entry(split_frame, width=50, style="TEntry")
split_entry.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
split_select_button = ttk.Button(split_frame, text="Selecionar...", command=lambda: select_media_file(split_entry), style="TButton")
split_select_button.grid(row=1, column=1, padx=5, pady=5)

# Opções de duração
duration_frame = ttk.Frame(split_frame, style="TFrame")
duration_frame.grid(row=2, column=0, columnspan=2, pady=5)
ttk.Label(duration_frame, text="Duração por parte:", style="TLabel").pack(side=tk.LEFT, padx=5)
split_duration_var = StringVar(value="15") # Padrão 15 segundos
rb_15s = ttk.Radiobutton(duration_frame, text="15 segundos (Stories)", variable=split_duration_var, value="15", style="TRadiobutton")
rb_15s.pack(side=tk.LEFT, padx=5)
rb_30s = ttk.Radiobutton(duration_frame, text="30 segundos (Música/Reels)", variable=split_duration_var, value="30", style="TRadiobutton")
rb_30s.pack(side=tk.LEFT, padx=5)

split_button = ttk.Button(split_frame, text="Dividir Vídeo", command=start_video_split, style="Highlight.TButton")
split_button.grid(row=3, column=0, columnspan=2, pady=10)

split_status_label = ttk.Label(split_frame, text="Verificando...", style="TLabel")
split_status_label.grid(row=4, column=0, columnspan=2, pady=5)

# Desabilita se FFmpeg não estiver disponível
if not FFMPEG_EXISTS:
    split_button.config(state=tk.DISABLED)
    split_status_label.config(text="FFmpeg indisponível", foreground="red")
    split_entry.config(state=tk.DISABLED)
    split_select_button.config(state=tk.DISABLED)
    rb_15s.config(state=tk.DISABLED)
    rb_30s.config(state=tk.DISABLED)
    ttk.Label(split_frame, text="Verifique a instalação do FFmpeg.", foreground="red", style="TLabel").grid(row=5, column=0, columnspan=2)
else:
    split_status_label.config(text="Pronto.")

# --- Aba Download em Parte/Lista ---
part_download_tab = ttk.Frame(notebook, padding="10", style="TFrame")
notebook.add(part_download_tab, text=' Download em Parte/Lista ')

# Frame URL (Parte/Lista)
part_url_frame = ttk.Frame(part_download_tab, padding="5", style="TFrame")
part_url_frame.pack(fill=tk.X, pady=5)
ttk.Label(part_url_frame, text="URL YouTube:", style="TLabel").pack(side=tk.LEFT, padx=5)
part_url_entry = ttk.Entry(part_url_frame, width=60, style="TEntry")
part_url_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

# Botão Colar (Parte/Lista)
def part_paste_from_clipboard():
    # Reutiliza a lógica de colar, mas no campo de entrada desta aba
    if PYPERCLIP_AVAILABLE:
        try:
            clipboard_content = pyperclip.paste()
            part_url_entry.delete(0, tk.END)
            part_url_entry.insert(0, clipboard_content)
            log("URL colada na aba Parte/Lista (pyperclip).", "INFO")
            return
        except Exception as e:
            log(f"Erro ao colar com pyperclip (Parte/Lista): {e}", "WARNING")
    try:
        clipboard_content = root.clipboard_get()
        part_url_entry.delete(0, tk.END)
        part_url_entry.insert(0, clipboard_content)
        log("URL colada na aba Parte/Lista (Tk fallback).", "INFO")
    except tk.TclError:
        log("Não foi possível acessar a área de transferência (Parte/Lista).", "ERROR")
        messagebox.showerror("Erro Clipboard", "Não foi possível acessar a área de transferência.")

part_paste_button = ttk.Button(part_url_frame, text="Colar", command=part_paste_from_clipboard, style="TButton")
part_paste_button.pack(side=tk.LEFT, padx=5)

# Frame Lista de Faixas
tracklist_frame = ttk.LabelFrame(part_download_tab, text="Lista de Faixas (Nome HH:MM:SS ou MM:SS / HH:MM:SS - Nome)", padding="10", style="TLabelframe")
tracklist_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=5)

tracklist_scrollbar = ttk.Scrollbar(tracklist_frame, orient=tk.VERTICAL, style="Vertical.TScrollbar")
tracklist_text = tk.Text(tracklist_frame, height=10, wrap="word", yscrollcommand=tracklist_scrollbar.set,
                         relief="sunken", borderwidth=1,
                         bg=THEME_COLORS["entry"], fg=THEME_COLORS["entry_fg"]) # Usa cores de entry
tracklist_scrollbar.config(command=tracklist_text.yview)

tracklist_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
tracklist_text.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

# Frame Opções de Formato (Parte/Lista)
part_format_frame = ttk.Frame(part_download_tab, padding="5", style="TFrame")
part_format_frame.pack(fill=tk.X, pady=(0, 5))

ttk.Label(part_format_frame, text="Formato Saída:", style="TLabel").pack(side=tk.LEFT, padx=(5, 10))

part_output_format = tk.StringVar(value="mp3") # Default to mp3

mp3_radio = ttk.Radiobutton(part_format_frame, text="MP3 (Áudio)", variable=part_output_format, value="mp3", style="TRadiobutton")
mp3_radio.pack(side=tk.LEFT, padx=5)

mp4_radio = ttk.Radiobutton(part_format_frame, text="MP4 (Vídeo)", variable=part_output_format, value="mp4", style="TRadiobutton")
mp4_radio.pack(side=tk.LEFT, padx=5)

# Frame Botões e Status (Parte/Lista)
part_action_frame = ttk.Frame(part_download_tab, padding="5", style="TFrame")
part_action_frame.pack(fill=tk.X, pady=5)

part_download_button = ttk.Button(part_action_frame, text="Iniciar Download por Partes", command=lambda: start_part_download(), style="Highlight.TButton") # Placeholder command
part_download_button.pack(side=tk.LEFT, padx=10)

part_status_label = ttk.Label(part_action_frame, text="Pronto.", style="TLabel")
part_status_label.pack(side=tk.LEFT, padx=10)

# Barra de Progresso (Parte/Lista)
part_progress_bar = ttk.Progressbar(part_download_tab, orient='horizontal', mode='indeterminate', length=300)
part_progress_bar.pack(pady=5, fill=tk.X, padx=5)
part_progress_bar.stop() # Inicia parada

# --- Funções da Aba Download em Parte/Lista ---

def download_and_split_thread(url, tracks, output_format):
    log(f"Iniciando download e divisão por faixas para: {url} (Formato: {output_format.upper()})", "HIGHLIGHT")
    # Desabilita botão e inicia progresso
    if part_download_button.winfo_exists():
        part_download_button.config(state=tk.DISABLED)
    if part_status_label.winfo_exists():
        part_status_label.config(text=f"Iniciando download ({output_format.upper()})...")
    if part_progress_bar.winfo_exists():
        part_progress_bar.start(10)

    global last_download_path # Para abrir a pasta depois

    temp_filepath = None # Inicializa para garantir que existe no finally

    try:
        # 1. Obter título do vídeo para nomear a pasta
        video_title = get_video_title(url)
        if not video_title:
            video_title = f"video_dividido_{int(time.time())}"
            log(f"Não foi possível obter o título do vídeo, usando nome padrão: {video_title}", "WARNING")
        sanitized_video_title = sanitize_filename(video_title)

        # 2. Definir pasta de saída baseada no formato
        if output_format == "mp3":
            output_base_dir = MP3_DIR
        elif output_format == "mp4":
            output_base_dir = MP4_DIR
        else:
            raise ValueError(f"Formato de saída inválido: {output_format}")
            
        output_folder = os.path.join(output_base_dir, sanitized_video_title)
        os.makedirs(output_folder, exist_ok=True)
        log(f"Pasta de saída para faixas ({output_format.upper()}): {output_folder}", "INFO")

        # 3. Baixar o arquivo completo (áudio ou vídeo) temporário
        temp_filename = f"{sanitized_video_title}_full_temp.{output_format}"
        temp_filepath = os.path.join(PROCESSED_DIR, temp_filename) # Salva temporário em Processed
        log(f"Baixando arquivo completo ({output_format.upper()}) para: {temp_filepath}", "INFO")
        if part_status_label.winfo_exists():
            part_status_label.config(text=f"Baixando ({output_format.upper()})...")

        if not check_ytdlp_dependency():
            raise Exception("yt-dlp não encontrado.")

        ytdlp_command = [YTDLP_PATH, '--no-warnings', '--progress']

        if output_format == "mp3":
            ytdlp_command.extend([
                	'-x', # Extrair áudio
                	'--audio-format', 'mp3',
                	'--audio-quality', '0', # Melhor qualidade de áudio
            ])
        elif output_format == "mp4":
             ytdlp_command.extend([
                 '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', # Melhor MP4 com áudio
                 '--merge-output-format', 'mp4', # Garante MP4 se precisar merge
             ])
        
        ytdlp_command.extend([ 
            '--output', temp_filepath,
            url
        ])

        log(f'Executando comando yt-dlp: {" ".join(ytdlp_command)}', "INFO")
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(ytdlp_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1, universal_newlines=True, startupinfo=startupinfo)

        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                log(line.strip(), "INFO") # Logar output do yt-dlp
            process.stdout.close()
        return_code = process.wait()

        if return_code != 0:
            log(f"Erro durante o download ({output_format.upper()}) (yt-dlp retornou código {return_code}).", "ERROR")
            raise Exception(f"yt-dlp falhou ao baixar o arquivo ({output_format.upper()}) (código {return_code})")
        else:
            log(f"Download do arquivo completo ({output_format.upper()}) concluído com sucesso.", "SUCCESS")

        # 4. Dividir o arquivo usando FFmpeg
        if not check_ffmpeg_dependency():
            raise Exception("FFmpeg não encontrado para dividir o arquivo.")

        total_tracks = len(tracks)
        errors = 0
        processed_files = []

        for i, track in enumerate(tracks):
            track_num = i + 1
            track_name = track["name"]
            start_sec = track["start_seconds"]
            end_sec = track["end_seconds"]

            log(f"  [DEBUG] Processando Faixa {track_num}: Nome=\"{track_name}\", Início={start_sec}s, Fim={end_sec if end_sec is not None else 'Fim'}", "INFO")

            output_track_filename = f"{track_num:02d} - {track_name}.{output_format}"
            output_track_filepath = os.path.join(output_folder, output_track_filename)

            # Colocar -ss DEPOIS de -i para output seeking (mais lento, potencialmente mais preciso)
            # Adicionar -copyts para tentar manter a precisão do timestamp
            ffmpeg_command = [
                FFMPEG_PATH, 	"-y", # Flag para sobrescrever sem perguntar
                	"-copyts", # Copia timestamps
                	"-i", temp_filepath, # Entrada primeiro
                	"-ss", str(start_sec),  # Tempo inicial DEPOIS da entrada
                	"-avoid_negative_ts", 	"make_zero" # Evita timestamps negativos
            ]

            # Define o tempo final usando -t (duração) em vez de -to
            if end_sec is not None:
                # Garante que end_sec é maior que start_sec
                if end_sec > start_sec:
                    duration = end_sec - start_sec
                    ffmpeg_command.extend(["-t", str(duration)]) # Usa -t (duração)
                    log(f"  [DEBUG] Definindo duração (-t): {duration}s (Fim: {end_sec}s)", "INFO") # DEBUG LOG
                else:
                    log(f"  [WARN] Tempo final ({end_sec}) não é maior que o inicial ({start_sec}) para a faixa {track_num}. Pulando definição de tempo final/duração.", "WARNING")
            else:
                 log("  [DEBUG] Tempo final não definido (end_sec is None), FFmpeg cortará até o fim.", "INFO") # DEBUG LOG
            # Se end_sec for None ou inválido, FFmpeg cortará até o final do arquivo

            # Define codecs e metadados baseados no formato
            if output_format == "mp3":
                ffmpeg_command.extend(['-c:a', 'libmp3lame', '-q:a', '2']) # Codec MP3
            elif output_format == "mp4":
                # Tenta copiar codecs para velocidade e qualidade. Adiciona mapeamento.
                ffmpeg_command.extend(['-map', '0:v?', '-map', '0:a?', '-c:v', 'copy', '-c:a', 'copy'])
                # Adiciona metadados MP4
                ffmpeg_command.extend(['-metadata', f'title={track_name}', '-metadata', f'track={track_num}/{total_tracks}']) 
            
            ffmpeg_command.append(output_track_filepath)

            log(f'Executando comando FFmpeg: {" ".join(ffmpeg_command)}', "INFO")
            result_ffmpeg = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False, encoding='utf-8', errors='replace', startupinfo=startupinfo)

            if result_ffmpeg.returncode != 0:
                log(f"Erro ao dividir faixa {track_num} ({track_name}) com FFmpeg (código {result_ffmpeg.returncode}): {result_ffmpeg.stderr}", "ERROR")
                # Se a cópia de codec falhar para MP4, tenta re-encodificar como fallback
                if output_format == "mp4" and ("Codec type mismatch" in result_ffmpeg.stderr or "copy" in result_ffmpeg.stderr):
                    log("Cópia de codec falhou para MP4. Tentando re-encodificar...", "WARNING")
                    ffmpeg_command_reencode = [
                        FFMPEG_PATH, '-y',
                        '-i', temp_filepath,
                        '-ss', str(start_sec)
                    ]
                    if end_sec is not None and end_sec > start_sec:
                        ffmpeg_command_reencode.extend(['-to', str(end_sec)])
                    
                    ffmpeg_command_reencode.extend(['-map', '0:v?', '-map', '0:a?', '-c:v', 'libx264', '-preset', 'fast', '-crf', '23', '-c:a', 'aac', '-b:a', '128k'])
                    ffmpeg_command_reencode.extend(['-metadata', f'title={track_name}', '-metadata', f'track={track_num}/{total_tracks}']) 
                    ffmpeg_command_reencode.append(output_track_filepath)
                    
                    log(f'Executando comando FFmpeg (re-encode): {" ".join(ffmpeg_command_reencode)}', "INFO")
                    result_ffmpeg = subprocess.run(ffmpeg_command_reencode, capture_output=True, text=True, check=False, encoding='utf-8', errors='replace', startupinfo=startupinfo)
                    
                    if result_ffmpeg.returncode != 0:
                        log(f"Erro ao dividir faixa {track_num} ({track_name}) com FFmpeg (re-encode) (código {result_ffmpeg.returncode}): {result_ffmpeg.stderr}", "ERROR")
                        errors += 1
                    else:
                        log(f"Faixa {track_num} ({track_name}) dividida com sucesso (re-encode): {output_track_filepath}", "SUCCESS")
                        processed_files.append(output_track_filepath)
                else:
                     errors += 1 # Erro não relacionado a codec copy ou formato não é MP4
            else:
                log(f"Faixa {track_num} ({track_name}) dividida com sucesso: {output_track_filepath}", "SUCCESS")
                processed_files.append(output_track_filepath)
                # 5. Adicionar metadados MP3 (se aplicável)
                if output_format == "mp3" and MUTAGEN_AVAILABLE:
                    try:
                        audio = MP3(output_track_filepath, ID3=ID3)
                        if audio.tags is None:
                            audio.add_tags()
                        audio.tags.add(TIT2(encoding=3, text=track_name)) # Título
                        audio.tags.add(TRCK(encoding=3, text=f"{track_num}/{total_tracks}")) # Número da Faixa
                        # Poderia adicionar Artista/Álbum do vídeo aqui se desejado
                        audio.save()
                        log(f"Metadados (título, faixa) adicionados à faixa MP3 {track_num}", "INFO")
                    except Exception as meta_e:
                        log(f"Erro ao adicionar metadados à faixa MP3 {track_num}: {meta_e}", "WARNING")
                elif output_format == "mp3":
                    log("Metadados MP3 não adicionados: biblioteca 'mutagen' não encontrada.", "WARNING")

        # 6. Limpeza do arquivo temporário
        try:
            os.remove(temp_filepath)
            log(f"Arquivo temporário removido: {temp_filepath}", "INFO")
        except OSError as e:
            log(f"Erro ao remover arquivo temporário {temp_filepath}: {e}", "WARNING")

        # 7. Finalização
        final_message = f"Divisão concluída! {total_tracks - errors} faixas ({output_format.upper()}) salvas em:\n{output_folder}"
        if errors > 0:
            final_message += f"\n{errors} faixas falharam (verifique o log)."
            log(final_message, "WARNING")
            messagebox.showwarning("Divisão Concluída com Erros", final_message)
        else:
            log(final_message, "SUCCESS")
            messagebox.showinfo("Divisão Concluída", final_message)
            last_download_path = output_folder # Define para botão "Abrir Local"
            open_folder_path(output_folder) # Abre a pasta automaticamente

    except Exception as e:
        log(f"Erro geral no processo de download/divisão por partes: {e}", "ERROR")
        messagebox.showerror("Erro", f"Ocorreu um erro durante o processo:\n{e}")
        # Tenta limpar arquivo temporário em caso de erro
        if temp_filepath and os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
                log(f"Arquivo temporário {temp_filepath} removido devido a erro.", "INFO")
            except OSError as rm_e:
                log(f"Erro ao remover arquivo temporário {temp_filepath} após falha: {rm_e}", "WARNING")

    finally:
        # Reabilita botão e para progresso
        if part_download_button.winfo_exists():
            part_download_button.config(state=tk.NORMAL)
        if part_status_label.winfo_exists():
            part_status_label.config(text="Pronto.")
        if part_progress_bar.winfo_exists():
            part_progress_bar.stop()
            part_progress_bar['value'] = 0

def start_part_download():
    url = part_url_entry.get().strip()
    tracklist_content = tracklist_text.get("1.0", tk.END).strip()
    selected_format = part_output_format.get() # Pega o formato selecionado

    if not url:
        messagebox.showwarning("Entrada Inválida", "Por favor, insira uma URL do YouTube.")
        return
    if not tracklist_content:
        messagebox.showwarning("Entrada Inválida", "Por favor, cole a lista de faixas.")
        return

    log("Analisando lista de faixas...", "INFO")
    tracks = parse_tracklist(tracklist_content)

    if not tracks:
        messagebox.showerror("Erro na Lista", "Nenhuma faixa válida encontrada na lista fornecida. Verifique o formato e o log para detalhes.")
        return

    # Verifica dependências essenciais
    if not check_ytdlp_dependency() or not check_ffmpeg_dependency():
        messagebox.showerror("Erro de Dependência", "yt-dlp e/ou FFmpeg não encontrados. Verifique a instalação e a pasta PATH.")
        return

    # Inicia o processo em uma thread separada
    run_in_thread(download_and_split_thread, args=(url, tracks, selected_format))


# --- Área de Log (Movida para baixo) --- #
log_frame = ttk.LabelFrame(main_frame, text="Log de Atividades", padding="5", style="TLabelframe")
log_frame.pack(expand=False, fill=tk.X, padx=10, pady=(0, 10), side=tk.BOTTOM) # Empacota no final

log_controls_frame = ttk.Frame(log_frame, style="TFrame")
log_controls_frame.pack(fill=tk.X)

log_scrollbar = ttk.Scrollbar(log_controls_frame, orient=tk.VERTICAL, style="Vertical.TScrollbar")
log_text = tk.Text(log_controls_frame, height=8, wrap="word", yscrollcommand=log_scrollbar.set,
                   state='disabled', relief="sunken", borderwidth=1,
                   bg=THEME_COLORS["log_bg"], fg=THEME_COLORS["log_fg"]) # Cores do tema
log_scrollbar.config(command=log_text.yview)

log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
log_text.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

# Botão Limpar Log
clear_log_button = ttk.Button(log_frame, text="Limpar Log", command=clear_log, style="TButton")
clear_log_button.pack(pady=(5,0)) # Posicionado abaixo do log

# Configura tags de cor para o log
for level, color in LOG_COLORS.items():
    log_text.tag_config(level, foreground=color)
log_text.tag_config("TIMESTAMP", foreground=THEME_COLORS.get("timestamp_fg", "#888888")) # Cor do timestamp

# --- Inicialização Final --- #
log("YouTube Downloader iniciado.", "HIGHLIGHT")
log(f"Versão: {APP_VERSION}", "INFO")
log(f"Diretório Base de Downloads: {BASE_DOWNLOAD_DIR}", "INFO")
log(f"yt-dlp: {'Encontrado' if YTDLP_EXISTS else 'NÃO ENCONTRADO!'}", "SUCCESS" if YTDLP_EXISTS else "ERROR")
log(f"FFmpeg: {'Encontrado' if FFMPEG_EXISTS else 'NÃO ENCONTRADO!'}", "SUCCESS" if FFMPEG_EXISTS else "ERROR")
log(f"Requests: {'Disponível' if REQUESTS_AVAILABLE else 'NÃO ENCONTRADO!'}", "SUCCESS" if REQUESTS_AVAILABLE else "ERROR")
log(f"Pillow: {'Disponível' if PILLOW_AVAILABLE else 'NÃO ENCONTRADO!'}", "SUCCESS" if PILLOW_AVAILABLE else "ERROR")
log(f"Mutagen: {'Disponível' if MUTAGEN_AVAILABLE else 'NÃO ENCONTRADO!'}", "SUCCESS" if MUTAGEN_AVAILABLE else "ERROR")
log(f"Spleeter: {'Disponível' if SPLEETER_AVAILABLE else 'Indisponível (Opcional)'}", "SUCCESS" if SPLEETER_AVAILABLE else "WARNING")

# Mostra popups de erro para dependências *essenciais* não encontradas
# (Comentado para não ser muito intrusivo, o log já informa)
# if not YTDLP_EXISTS: messagebox.showerror("Dependência Essencial Ausente", "yt-dlp.exe não encontrado na pasta PATH! Downloads não funcionarão.")
# if not FFMPEG_EXISTS: messagebox.showwarning("Dependência Ausente", "ffmpeg.exe não encontrado na pasta PATH! Funções de corte, conversão e manipulação podem falhar.")
# if not REQUESTS_AVAILABLE: messagebox.showwarning("Dependência Ausente", "Biblioteca 'requests' não instalada! Download de miniaturas e verificação de atualizações não funcionarão.")
# if not PILLOW_AVAILABLE: messagebox.showwarning("Dependência Ausente", "Biblioteca 'Pillow' não instalada! Processamento de miniaturas não funcionará.")
# if not MUTAGEN_AVAILABLE: messagebox.showwarning("Dependência Ausente", "Biblioteca 'mutagen' não instalada! Adição de metadados a MP3s não funcionará.")

# Verifica atualizações ao iniciar (em background, se requests estiver disponível)
if REQUESTS_AVAILABLE:
    run_in_thread(check_for_updates, args=(False,)) # False para não mostrar msg se não houver update

root.mainloop()

