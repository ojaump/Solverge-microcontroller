# modbus_tcp_client.py - Cliente Modbus TCP leve para MicroPython
import socket
import struct

class ModbusTCPClient:
    def __init__(self, ip, port=502, unit_id=1, timeout=2):
        self.ip = ip
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.transaction_id = 0
        self.sock = None

    def connect(self):
        self.sock = socket.socket()
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.ip, self.port))

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def read_holding_registers(self, address, count=1):
        self.transaction_id = (self.transaction_id + 1) % 65536

        # MBAP Header
        mbap = struct.pack('>HHHB',
                           self.transaction_id,  # Transaction ID
                           0x0000,               # Protocol ID
                           6,                    # Length
                           self.unit_id)         # Unit ID

        # PDU: Function Code (0x03) + Start Address + Quantity
        pdu = struct.pack('>BHH', 0x03, address, count)

        request = mbap + pdu
        self.sock.send(request)

        # Expected response: MBAP (7 bytes) + Function Code + Byte Count + Data
        response = self.sock.recv(512)

        if len(response) < 9:
            raise Exception("Resposta incompleta do servidor Modbus")

        byte_count = response[8]
        if byte_count != count * 2:
            raise Exception("Byte count inesperado")

        registers = []
        for i in range(count):
            reg = struct.unpack('>H', response[9 + 2*i: 11 + 2*i])[0]
            registers.append(reg)

        return registers

    def read_single_register(self, address):
        return self.read_holding_registers(address, 1)[0]

    def read_double_register(self, address):
        regs = self.read_holding_registers(address, 2)
        return struct.unpack('>I', struct.pack('>HH', *regs))[0]
