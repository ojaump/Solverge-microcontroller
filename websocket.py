import socket
import struct
import random
import hashlib
import base64
import time

class WebSocketClient:
    def __init__(self, url):
        self.url = url
        self.socket = None
        self.connected = False
        self.on_message = None
        self.on_connect = None
        self.on_disconnect = None
        self.last_ping = 0
        self.ping_interval = 30

    def connect(self):
        try:
            proto, _, host, path = self.url.split('/', 3)
            addr = socket.getaddrinfo(host, 80)[0][-1]
            
            self.socket = socket.socket()
            self.socket.connect(addr)
            
            key = base64.b64encode(bytes([random.randint(0, 255) for _ in range(16)]))
            
            handshake = (
                f"GET /{path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key.decode()}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "\r\n"
            )
            self.socket.send(handshake.encode())
            
            resp = self.socket.recv(1024).decode()
            if "101 Switching Protocols" in resp:
                self.connected = True
                self.last_ping = time.time()
                if self.on_connect:
                    self.on_connect()
                return True
            return False
            
        except Exception as e:
            print("[WS] Error in connect:", e)
            self.connected = False
            raise

    def send(self, data):
        if not isinstance(data, str):
            data = str(data)
        payload = data.encode()
        
        header = bytearray()
        header.append(0x81)  # Text frame
        
        if len(payload) < 126:
            header.append(len(payload))
        elif len(payload) < 65536:
            header.append(126)
            header.extend(struct.pack(">H", len(payload)))
        else:
            header.append(127)
            header.extend(struct.pack(">Q", len(payload)))
            
        self.socket.send(header + payload)

    def receive(self):
        try:
            header = self.socket.recv(2)
            if not header:
                return None
                
            opcode = header[0] & 0x0F
            if opcode == 0x8:  # Close frame
                self.connected = False
                if self.on_disconnect:
                    self.on_disconnect()
                return None
            
            length = header[1] & 0x7F
            if length == 126:
                length = struct.unpack(">H", self.socket.recv(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self.socket.recv(8))[0]
                
            data = self.socket.recv(length)
            return data.decode('utf-8')
            
        except Exception as e:
            print("[WS] Error in receive:", e)
            self.connected = False
            if self.on_disconnect:
                self.on_disconnect()
            return None

    def send_ping(self):
        if time.time() - self.last_ping > self.ping_interval:
            header = bytearray([0x89, 0x00])
            self.socket.send(header)
            self.last_ping = time.time()

    def send_pong(self):
        header = bytearray([0x8A, 0x00])
        self.socket.send(header)
