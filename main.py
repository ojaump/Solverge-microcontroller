# main.py
import network
import ubinascii
import uasyncio as asyncio
import json
import time
import socket
import _thread
from machine import reset
from lib.modbus_tcp_client import ModbusTCPClient
from websocket.ws import AsyncWebsocketClient

CONFIG_FILE = "config.json"

def get_mac():
    wlan = network.WLAN(network.STA_IF)
    mac = ubinascii.hexlify(wlan.config('mac'), ':').decode()
    return mac, mac.replace(":", "")

def load_config():
    cfg = {}
    try:
        with open(CONFIG_FILE) as f:
            cfg.update(json.load(f))
    except:
        print("[CONFIG] Aviso: config.json não encontrado.")
    return cfg

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f)

def serve_file(client, path, content_type="text/html"):
    try:
        with open(path, "r") as f:
            client.send("HTTP/1.0 200 OK\r\nContent-Type: {}\r\n\r\n".format(content_type))
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
        import sys
        sys.print_exception(e)
        client.send("HTTP/1.0 500 Internal Server Error\r\n\r\nErro interno.")
        print("[WEB] Erro ao salvar Wi-Fi:", e)

def start_web_server():
    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    s = socket.socket()
    s.bind(addr)
    s.listen(1)
    print("[WEB] Servidor ouvindo em porta 80")
    while True:
        cl, addr = s.accept()
        req = cl.recv(1024).decode()
        if "GET /wifi"   in req: serve_file(cl, "web/wifi.html")
        elif "GET / "    in req: serve_file(cl, "web/index.html")
        elif "GET /scripts.js" in req:
            serve_file(cl, "web/scripts.js", content_type="application/javascript")
        elif "GET /scan" in req:
            try:
                sta = network.WLAN(network.STA_IF)
                sta.active(True)
                nets = sta.scan()
                out = [{"ssid":n[0].decode(),"rssi":n[3]} for n in nets]
                cl.send("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
                cl.send(json.dumps(out))
            except Exception as e:
                print("[WIFI] Erro scan:", e)
                cl.send("HTTP/1.0 500 Internal Server Error\r\n\r\n")
        elif "GET /status" in req:
            sta = network.WLAN(network.STA_IF)
            data = {
                "connected": sta.isconnected(),
                "ssid":      sta.config("essid") if sta.isconnected() else None,
                "ip":        sta.ifconfig()[0] if sta.isconnected() else None,
                "rssi":      sta.status("rssi") if sta.isconnected() else None,
            }
            cl.send("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
            cl.send(json.dumps(data))
        elif "POST /save-wifi" in req:
            handle_wifi_save(cl, req)
        cl.close()

def select_mode(client, command):
    mapping = {
        "stop":   35700,
        "auto":   35701,
        "manual": 35702,
        "start":  35705,
        "run":    35708
    }
    if command not in mapping:
        print(f"[CMD] inválido: {command}")
        return
    addr  = 16*256 + 8
    value = mapping[command]
    try:
        client.write_registers(addr,      [value, 0xFFFF - value])
        print(f"[CMD] '{command}' gravado em regs {addr} e {addr+1}")
    except Exception as e:
        print("[CMD] erro ao escrever:", e)
def get_generator_mode(client):
    status_map = {0: "Stop", 1: "Auto", 2: "Manual"}
    generator_status = client.read_single_register(3*256+4)
    return status_map.get(generator_status, "Desconhecido")
def read_generator_data(ip, port):
    try:
        c = ModbusTCPClient(ip, port)
        c.connect()
        data = {
            "modo": get_generator_mode(c),
            "velocidade_motor": c.read_single_register(4*256+6),
            "pressao_oleo":    c.read_single_register(4*256+0)/10,
            "temperatura_liquido_arrefecimento": c.read_single_register(4*256+1),
            "tensao_bateria":  c.read_single_register(4*256+5)/10,
            "frequencia_gerador": c.read_single_register(4*256+7)/10,
            "tensao_gerador_L1_N": round(c.read_double_register(4*256+10)*0.1),
            "corrente_gerador":    c.read_double_register(4*256+20+2)*0.1,
            "producao_atual":      c.read_double_register(4*256+28)/1000,
            "producao_acumulada":  c.read_double_register(7*256+8),
            "horas_trabalhadas":   c.read_double_register(7*256+6)/3600,
            "pressao_turbo":       c.read_single_register(5*256+4)/10,
            "state":               "Ready!" if c.read_double_register(190*256+14)==1 else "Wait!"
        }
        c.close()
        return data
    except Exception as e:
        print("[MODBUS] erro leitura:", e)
        return None

async def handle_websocket():
    import json
    mac = get_mac()[1]
    ws = AsyncWebsocketClient()
    await ws.handshake(f"ws://solverge.ojaum.lat/ws?mac={mac}")
    print("[WS] Conectado ao servidor WebSocket")

    async def listener():
        while True:
            msg = await ws.recv()
            if not msg:
                await asyncio.sleep(1)
                continue
            try:
                cmd = json.loads(msg)
                dev = cmd.get("device") or cmd.get("id")
                mode= cmd.get("mode")
                if dev and mode:
                    cfg  = load_config()
                    info = cfg.get("devices",{}).get(dev)
                    if info:
                        cli = ModbusTCPClient(info["ip"], info.get("port",502))
                        cli.connect()
                        select_mode(cli, mode)
                        cli.close()
                    else:
                        print(f"[WS] dispositivo não encontrado: {dev}")
                else:
                    print("[WS] JSON incompleto:", cmd)
            except Exception as e:
                print("[WS] erro listener:", e)
            await asyncio.sleep(1)

    async def sender():
        mac = get_mac()[1]
        while True:
            cfg = load_config()
            for dev, info in cfg.get("devices",{}).items():
                if info.get("type")=="gerador":
                    data = read_generator_data(info["ip"], info.get("port",502))
                    if data:
                        await ws.send(json.dumps({mac:{dev:data}}))
                        print("[WS] dados enviados.")
            await asyncio.sleep(1)

    await asyncio.gather(listener(), sender())

async def main():
    # 1) Hotspot para configuração
    _, mac = get_mac()
    ap = network.WLAN(network.AP_IF)
    ap.config(essid="Solverge",
              password="")
    ap.active(True)
    print("=== Hotspot Configuration ===")
    print("AP SSID:   Solverge")
    print("=============================")

    # 2) Tenta conectar via STA se já tiver configurações
    cfg = load_config()
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if "wifi" in cfg:
        ss, pw = cfg["wifi"]["ssid"], cfg["wifi"]["password"]
        print(f"[BOOT] Tentando STA: {ss}")
        sta.connect(ss, pw)
        for _ in range(20):
            if sta.isconnected():
                print("[WIFI] Conectado com IP:", sta.ifconfig()[0])
                break
            await asyncio.sleep(1)
        else:
            print("[WIFI] Falha ao conectar STA")

    # 3) Sobe web server sempre (para /wifi)
    _thread.start_new_thread(start_web_server, ())

    # 4) Se conectou no STA, inicia WebSocket; senão dorme
    if sta.isconnected():
        await handle_websocket()
    else:
        while True:
            await asyncio.sleep(10)

# roda tudo
asyncio.run(main())
