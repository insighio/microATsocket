from network import LTE
import utime
import binascii
import ure

################################################################################
## Custom socket implementation
##
## Implementation based on the assumption that LTE.send_at_cmd can send arbitrary
## number of bytes (https://github.com/pycom/pycom-micropython-sigfox/pull/429)
##

class MicroATSocket:
    def enum(**enums):
        return type('Enum', (), enums)

    SOCKET_MESSAGE_FORMAT = enum(
        SOCKET_MESSAGE_ASCII = 0,
        SOCKET_MESSAGE_BYTE = 1
    )

    def __init__(self, modem):
        print("CustomSocket: init")
        self.ip = None
        self.port = None
        self.socketid = None
        self.recvRegex = "\+SQNSRING: (\\d+),(\\d+)"
        self.modem = modem
        self.contentFormat = MicroATSocket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE

    def sendAtCommand(self, command, timeout = 11000):
        print("[AT] => " + str(command))
        response = self.modem.send_at_cmd(command, timeout)
        print("[AT] <= " + response)
        return response

    def setMessageFormat(self, format):
        if(format == MicroATSocket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE):
            self.contentFormat = MicroATSocket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE
        else:
            self.contentFormat = MicroATSocket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_ASCII

    def open(self, ip, port):
        self.socketid = None

        if(self.ip == ip or self.port == port and self.socketid != None):
            return True

        if(self.ip == None and self.port == None):
            self.ip = ip
            self.port = port
            self.socketid = None

        if(self.socketid != None):
            self.close()

        contentFormatID = '0'
        if(self.contentFormat == MicroATSocket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE):
            contentFormatID = '1'

        # after opening socket, set sent data format to heximal
        # AT+SQNSCFGEXT=<connId>,
        #               <incoming message notification to include byte length>,
        #               <recv data as string>,
        #               <unused>,
        #               <unused for UDP>,
        #               <sendDataMode as HEX>
        #               <unused>,
        #               <unused>
        self.sendAtCommand('AT+SQNSCFGEXT=1,1,' + contentFormatID + ',0,0,' + contentFormatID + ',0,0')

        # <socket ID>, <UDP>, <remote port>, <remote IP>,0,<local port>, <online mode>
        command = 'AT+SQNSD=1,1,' + str(port) + ',"' + ip + '",0,8888,1'
        response = self.sendAtCommand(command)
        if(response.find("OK") == -1):
            utime.sleep_ms(5000)
            # retry
            response = self.sendAtCommand(command)

            if(response.find("OK") != -1):
                self.socketid = 1
        else:
            self.socketid = 1

        status = (self.socketid != None)

        return status

    def close(self):
        if self.socketid != None:
            response = self.sendAtCommand('AT+SQNSH=1')
            self.socketid == None

    def sendto(self, bytes, address):
        ip = address[0]
        port = address[1]

        if(not self.open(ip, port)):
            print("Failed to open socket, aborting.")
            return -1

        #if respones is OK continue

        arrayHexBytes = bytes

        # if format is BYTE, convert the byte array to hex string
        if(self.contentFormat == MicroATSocket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE):
          arrayHexBytes = binascii.hexlify(bytearray(bytes))

        byteLength = len(bytes)

        response = self.sendAtCommand('AT+SQNSSENDEXT=1,' + str(byteLength))

        response = self.sendAtCommand(arrayHexBytes, 15000)

        return len(bytes)

    def recvfrom(self, bufsize=-1):
        # send empty space to wait for an incoming notification from SQNSRING
        badResult = (None, None)

        if(not self.open(self.ip, self.port)):
            print("Failed to open socket, aborting.")
            return badResult

        resp = self.sendAtCommand(" ")

        # search for the URC
        match = ure.search(self.recvRegex, resp)
        if match == None:
            return badResult

        # +SQNSRING -> get notified of incoming data
        # +SQNSRECV -> read data
        command = "AT+SQNSRECV=" + match.group(1) + "," + match.group(2)
        resp2 = self.sendAtCommand(command)

        if(resp2.find("OK") == -1):
            return badResult

        responseLines = resp2.split()
        data = None
        for i in range(len(responseLines)):
            if(responseLines[i].find("SQNSRECV") > -1):
                data = responseLines[i+2]
                break

        if(data != None):
            if(self.contentFormat == MicroATSocket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE):
                return (binascii.unhexlify(data), [self.ip, self.port])
            else:
                return (data, [self.ip, self.port])
        else:
            return badResult

    def setblocking(self, flag):
        print(".", end="")
################################################################################
