import network
import _thread
import ubinascii
import json
import socket
import os
import time
from machine import reset
from websocket import WebSocketClient

CONFIG_FILE = "config.json"

def load_config():
    config = {}
    try:
        with open("config.json") as f:
            user_config = json.load(f)
            config.update(user_config)  # sobrepõe as chaves
    except:
        print("[CONFIG] Aviso: config.json não encontrado. Usando apenas config.default.json.")

    return config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)
config = load_config()

ws_client = None

def get_device_id():
    mac = ubinascii.hexlify(network.WLAN(network.STA_IF).config("mac")).decode()
    return mac

def connect_websocket():
    global ws_client
    device_mac = get_device_id()
    ws_url = f"ws://solverge.ojaum.lat/ws?mac={device_mac}"
    print("[WS] Conectando como:", device_mac)

    try:
        ws_client = WebSocketClient(ws_url)
        ws_client.on_message = on_ws_message
        ws_client.on_connect = on_ws_connect
        ws_client.on_disconnect = on_ws_disconnect
        ws_client.connect()
        print("[WS] Conectado com sucesso")
        return True
    except Exception as e:
        print("[WS] Falha ao conectar:", e)
        return False

def ws_publish(data):
    try:
        if ws_client and ws_client.connected:
            ws_client.send(json.dumps(data))
    except Exception as e:
        print("[WS] Erro ao publicar:", e)

def on_ws_message(msg):
    try:
        data = json.loads(msg)
        if "command" in data:
            handle_command(data)
    except Exception as e:
        print("[WS] Erro ao processar mensagem:", e)

def on_ws_connect():
    print("[WS] Conectado")
    ws_publish({"status": "online"})

def on_ws_disconnect():
    print("[WS] Desconectado")

def websocket_loop():
    while True:
        try:
            if ws_client and ws_client.connected:
                msg = ws_client.receive()
                if msg:
                    on_ws_message(msg)
            else:
                connect_websocket()
        except Exception as e:
            print("[WS] Erro no loop:", e)
        time.sleep(0.1)

def start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    mac, password = get_mac()
    ap.config(essid="Solverge", password=password)
    print("[HOTSPOT] AP iniciado: SSID=Solverge, Senha=", password)
    return ap

def connect_wifi(config):
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    ssid = config.get("wifi", {}).get("ssid")
    password = config.get("wifi", {}).get("password")
    if not ssid or not password:
        print("[WIFI] Nenhuma configuração Wi-Fi encontrada.")
        return False
    sta.connect(ssid, password)
    for _ in range(20):
        if sta.isconnected():
            print(f"[WIFI] Conectado a {ssid} com IP {sta.ifconfig()[0]}")
            return True
        time.sleep(1)
    print("[WIFI] Falha ao conectar.")
    return False
def start_web_server():
    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    s = socket.socket()
    s.bind(addr)
    s.listen(1)
    print("[WEB] Servidor ouvindo em porta 80")

    while True:
        cl, addr = s.accept()
        print("[WEB] Cliente conectado de", addr)
        req = cl.recv(1024).decode()

        if "GET /wifi" in req:
            serve_file(cl, "web/wifi.html")
        elif "GET / " in req:
            serve_file(cl, "web/index.html")
        elif "GET /scripts.js" in req:
            serve_file(cl, "web/scripts.js", content_type="application/javascript")
        elif "GET /scan" in req:
            try:
                sta = network.WLAN(network.STA_IF)
                sta.active(True)
                nets = sta.scan()
                result = [{"ssid": n[0].decode(), "rssi": n[3]} for n in nets]
                cl.send("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
                cl.send(json.dumps(result))
            except Exception as e:
                print("[WIFI] Erro ao escanear redes:", e)
                cl.send("HTTP/1.0 500 Internal Server Error\r\n\r\n")
        elif "GET /status" in req:
            sta = network.WLAN(network.STA_IF)
            data = {
                "connected": sta.isconnected(),
                "ssid": sta.config("essid") if sta.isconnected() else None,
                "ip": sta.ifconfig()[0] if sta.isconnected() else None,
                "rssi": sta.status("rssi") if sta.isconnected() else None,
            }
            cl.send("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
            cl.send(json.dumps(data))
        elif "GET /dispositivos" in req:
            serve_file(cl, "web/devices.html")

        elif "GET /get-devices" in req:
            cfg = load_config()
            devices = cfg.get("devices", {})
            cl.send("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
            cl.send(json.dumps(devices))
            
        elif "GET /ota" in req:
            try:
                import ota_updater
                cl.send("HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nAtualizando... Reiniciando em instantes.")
                cl.close()
                time.sleep(1)
                ota_updater.update_all()
                return
            except Exception as e:
                print("[WEB] Erro ao iniciar OTA:", e)
                cl.send("HTTP/1.0 500 Internal Server Error\r\n\r\nErro ao iniciar atualização OTA.")

        elif "POST /save-device" in req:
            try:
                body = req.split("\r\n\r\n", 1)[1]
                data = json.loads(body)
                cfg = load_config()
                if "devices" not in cfg:
                    cfg["devices"] = {}
                cfg["devices"][data["id"]] = {
                    "ip": data["ip"],
                    "port": int(data["port"]),
                    "type": data["type"]
                }
                save_config(cfg)
                cl.send("HTTP/1.0 200 OK\r\n\r\nSalvo com sucesso.")
            except Exception as e:
                print("[WEB] Erro ao salvar dispositivo:", e)
                cl.send("HTTP/1.0 500 Internal Server Error\r\n\r\nErro ao salvar dispositivo.")
        elif "GET /styles.css" in req:
            serve_file(cl, "web/styles.css", content_type="text/css")
        elif "GET /scripts.js" in req:
            serve_file(cl, "web/scripts.js", content_type="application/javascript")
        elif "POST /save-wifi" in req:
            handle_wifi_save(cl, req)
        cl.close()

def serve_file(client, path, content_type="text/html"):
    try:
        with open(path, "r") as f:
            client.send("HTTP/1.0 200 OK\r\nContent-type: {}\r\n\r\n".format(content_type))
            client.send(f.read())
    except:
        client.send("HTTP/1.0 404 Not Found\r\n\r\nFile not found.")

def handle_wifi_save(client, req):
    try:
        body = req.split("\r\n\r\n", 1)[1]
        params = dict(x.split("=") for x in body.split("&"))
        ssid = params.get("ssid")
        password = params.get("password")
        if ssid and password:
            cfg = load_config()
            cfg["wifi"] = {"ssid": ssid, "password": password}
            save_config(cfg)
            client.send("HTTP/1.0 200 OK\r\n\r\nSalvo com sucesso. Reiniciando...")
            time.sleep(2)
            reset()
        else:
            client.send("HTTP/1.0 400 Bad Request\r\n\r\nParâmetros inválidos.")
    except Exception as e:
        client.send("HTTP/1.0 500 Internal Server Error\r\n\r\nErro interno.")
        print("[WEB] Erro ao salvar Wi-Fi:", e)
        
def main_loop():
    print("[MAIN] Sistema iniciado com sucesso")
    sta = network.WLAN(network.STA_IF)
    ap = network.WLAN(network.AP_IF)

    print("[DEBUG] IP Station:", sta.ifconfig()[0])
    print("[DEBUG] IP AP:", ap.ifconfig()[0])

    while True:
        cfg = load_config()
        devices = cfg.get("devices", {})

        for device_id, info in devices.items():
            if info.get("type") == "gerador":
                data = read_generator_data(info.get("ip"), info.get("port", 502))
                if data:
                    ws_publish({
                        "device": device_id,
                        "data": data
                    })
        time.sleep(5)
def read_generator_data(ip, port):
    try:
        c = ModbusTCPClient(ip, port)
        c.connect()

        data = {
            "modo": get_generator_mode(c),
            "velocidade_motor": c.read_single_register(4 * 256 + 6),
            "pressao_oleo": c.read_single_register(4 * 256 + 0) / 10,
            "temperatura_liquido_arrefecimento": c.read_single_register(4 * 256 + 1),
            "tensao_bateria": c.read_single_register(4 * 256 + 5) / 10,
            "frequencia_gerador": c.read_single_register(4 * 256 + 7) / 10,
            "tensao_gerador_L1_N": round(c.read_double_register(4 * 256 + 10) * 0.1),
            "corrente_gerador": get_generator_current(c),
            "producao_atual": get_generator_power(c),
            "producao_acumulada": c.read_double_register(7 * 256 + 8),
            "horas_trabalhadas": c.read_double_register(7 * 256 + 6) / 3600,
            "pressao_turbo": c.read_single_register(5 * 256 + 4) / 10,
            "state": get_bus_state(c)
        }

        c.close()
        return data

    except Exception as e:
        print("[MODBUS] Erro ao ler dados do dispositivo:", e)
        return None

def get_generator_mode(client):
    status_map = {0: "Stop", 1: "Auto", 2: "Manual"}
    generator_status = client.read_single_register(3 * 256 + 4)
    return status_map.get(generator_status, "Desconhecido")

def get_generator_current(client):
    currents = [
        client.read_double_register(4 * 256 + 20),
        client.read_double_register(4 * 256 + 22),
        client.read_double_register(4 * 256 + 24)
    ]
    return sum(currents) * 0.1

def get_generator_power(client):
    powers = [
        client.read_double_register(4 * 256 + 28),
        client.read_double_register(4 * 256 + 30),
        client.read_double_register(4 * 256 + 32)
    ]
    return sum(powers) / 1000

def get_bus_state(client):
    bus_state = client.read_double_register(190 * 256 + 14)
    return "Ready!" if bus_state == 1 else "Wait!"

def write_registers(self, address, values):
    # MBAP: Transaction ID, Protocol ID, Length, Unit ID
    self.transaction_id = (self.transaction_id + 1) % 65536
    length = 7 + 1 + 2 + len(values) * 2
    mbap = struct.pack('>HHHB', self.transaction_id, 0, length - 6, self.unit_id)

    # PDU: Function code 0x10 (write multiple registers)
    count = len(values)
    header = struct.pack('>BHHB', 0x10, address, count, count * 2)
    data = b''.join(struct.pack('>H', v) for v in values)

    request = mbap + header + data
    self.sock.send(request)
    resp = self.sock.recv(12)  # confirm response (address + count)

    return True
def on_mqtt_command(topic, msg):
    try:
        print(f"[MQTT] Comando recebido em {topic}: {msg}")
        data = json.loads(msg)

        device_id = data.get("id")
        command = data.get("command")

        cfg = load_config()
        devices = cfg.get("devices", {})
        if device_id not in devices:
            print(f"[CMD] Dispositivo {device_id} não encontrado.")
            return

        device = devices[device_id]
        if device["type"] != "gerador":
            print(f"[CMD] Dispositivo {device_id} não é gerador.")
            return

        c = ModbusTCPClient(device["ip"], device["port"])
        c.connect()
        select_mode(c, command)
        c.close()
        print(f"[CMD] Comando '{command}' enviado para {device_id}.")
    except Exception as e:
        print("[CMD] Erro ao processar comando:", e)
def select_mode(client, command):
    commands = {
        "stop": 35700,
        "auto": 35701,
        "manual": 35702,
        "start": 35705,
        "run": 35708
    }
    if command in commands:
        value = commands[command]
        client.write_registers(16 * 256 + 8, [value, 65535 - value])
    else:
        print(f"[CMD] Comando inválido: {command}")

config = load_config()
start_ap()

if connect_wifi(config):
    print("[BOOT] Wi-Fi conectado. Iniciando sistema...")
    _thread.start_new_thread(start_web_server,())
    _thread.start_new_thread(websocket_loop,())
    main_loop()
else:
    print("[BOOT] Sem Wi-Fi. Modo AP ativo.")
    start_web_server()
