import urequests as requests
import os
import machine

REPO_URL = "https://raw.githubusercontent.com/ojaump/Solverge-microcontroller/main"

FILES = [
    "boot.py",
    "main.py",
    "lib/websocket/ws.py",
    "lib/modbus_tcp_client.py",
    "web/index.html",
    "web/wifi.html",
    "web/devices.html",
    "web/styles.css",
    "web/scripts.js",
    "ota_updater.py",
]

def ensure_dir(path):
    parts = path.split("/")
    for i in range(1, len(parts)):
        dir_path = "/".join(parts[:i])
        try:
            if dir_path not in os.listdir("/".join(parts[:i-1]) or "/"):
                os.mkdir(dir_path)
        except Exception:
            pass

def download_file(remote_path, local_path):
    url = f"{REPO_URL}/{remote_path}"
    print("[OTA] Baixando:", url)
    try:
        res = requests.get(url)
        if res.status_code == 200:
            with open(local_path, "w") as f:
                f.write(res.text)
            print("[OTA] Atualizado:", local_path)
        else:
            print(f"[OTA] Erro {res.status_code} ao baixar {remote_path}")
    except Exception as e:
        print(f"[OTA] Erro ao baixar {remote_path}:", e)

def update_all():
    print("[OTA] Iniciando atualização OTA")
    for file in FILES:
        if file == "config.json":
            continue  # não sobrescreve config.json nunca
        ensure_dir(file)
        download_file(file, file)

    print("[OTA] Atualização concluída. Reiniciando dispositivo...")
    machine.reset()
