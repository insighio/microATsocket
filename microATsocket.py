from network import LTE
import utime
import binascii
import ure

# Values acquired from pycom firmware
# pycom-micropython-sigfox/lib/lwip/src/include/lwip/sockets.h
AF_INET = 2
AF_INET6 = 10

SOCK_STREAM = 1  #not supported
SOCK_DGRAM  = 2
SOCK_RAW    = 3  #not supported

DNS_SERVER_IP   = "8.8.8.8"
DNS_SERVER_IPV6 = "2001:4860:4860::8888"

################################################################################
## Custom socket implementation
##
## Implementation based on the assumption that LTE.send_at_cmd can send arbitrary
## number of bytes (https://github.com/pycom/pycom-micropython-sigfox/pull/429)
##
class socket:
    def enum(**enums):
        return type('Enum', (), enums)

    SOCKET_MESSAGE_FORMAT = enum(
        SOCKET_MESSAGE_ASCII = 0,
        SOCKET_MESSAGE_BYTE = 1
    )

    ######################################################################
    # usocket compatible functions

    def __init__(self, family, type):
        print("CustomSocket: init")

        if(family != AF_INET and family != AF_INET6 ):
            raise Exception("address family not supported")

        if(type != SOCK_DGRAM):
            raise Exception("socket type not supported")

        self.ip = None
        self.port = None
        self.localport = 8888
        self.socketid = None
        self.family = family
        self.type = type
        self.recvRegex = "\+SQNSRING: (\\d+),(\\d+)"
        self.contentFormat = socket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE
        self.dns_server = DNS_SERVER_IP
        if(family == AF_INET6):
            self.dns_server = DNS_SERVER_IPV6

    def getaddrinfo(self, host, port):
        import dns_query

        ipv6_only = (self.family == AF_INET6)

        resolvedIPs = dns_query.dns_resolve(self, host, self.dns_server, ipv6_only)

        responseList = []
        for res in resolvedIPs:
            family = None
            if res[1] == 'A':
                family = AF_INET
            elif res[1] == 'AAAA':
                family = AF_INET6
            responseList.append((family, SOCK_STREAM, 0, '', (res[0], port)))
        return responseList

    def close(self):
        #if self.socketid != None:
        self.sendAtCommand('AT+SQNSH=1')
        self.socketid = None

    def bind(self, address):
        self.socketid = address[1]

    def sendto(self, bytes, address):
        ip = address[0]
        port = address[1]

        if(not self.open(ip, port)):
            print("Failed to open socket, aborting.")
            return -1

        #if respones is OK continue

        arrayHexBytes = bytes

        # if format is BYTE, convert the byte array to hex string
        if(self.contentFormat == socket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE):
          arrayHexBytes = binascii.hexlify(bytearray(bytes))

        byteLength = len(bytes)

        response = self.sendAtCommand('AT+SQNSSENDEXT=1,' + str(byteLength))

        #deactivating the timeout argument for now as it is not compatible
        #with the stock Pycom firmware.
        #response = self.sendAtCommand(arrayHexBytes, 15000)

        response = self.sendAtCommand(arrayHexBytes)

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
            if(self.contentFormat == socket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE):
                return (binascii.unhexlify(data), [self.ip, self.port])
            else:
                return (data, [self.ip, self.port])
        else:
            return badResult

    def setblocking(self, flag):
        print(".", end="")

    def dnsserver(self, dnsIndex=None, ip_addr=None):
        if(dnsIndex == None or ip_addr == None):
            return ((self.dns_server, "0.0.0.0"))

        if(dnsIndex != 0):
            raise Exception("Only primary DNS server can be configured")

        if(self.family == AF_INET):
            DNS_SERVER_IP = ip_addr
        elif(self.family == AF_INET6):
            DNS_SERVER_IPV6 = ip_addr

        self.dns_server = ip_addr

    ######################################################################
    # custom functions to setup socket

    def setModemInstance(self, modem):
        self.modem = modem

    def setMessageFormat(self, format):
        if(format == socket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE):
            self.contentFormat = socket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE
        else:
            self.contentFormat = socket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_ASCII

    ######################################################################
    # Private functions

    # If stock firmware is used, this function needs to be used
    def sendAtCommand(self, command):
        if self.modem == None:
            raise Exception("No modem instance assigned")
        print("[AT] => " + str(command))
        response = self.modem.send_at_cmd(command)
        print("[AT] <= " + response)
        return response

    # This function is not supported yet by the stop Pycom firmware
    def sendAtCommandWithTimeout(self, command, timeout):
        if self.modem == None:
            raise Exception("No modem instance assigned")
        print("[AT] => " + str(command))
        response = self.modem.send_at_cmd(command, timeout)
        print("[AT] <= " + response)
        return response

    def open(self, ip, port):
        if(self.ip == ip or self.port == port and self.socketid != None):
            return True

        if(self.ip == None and self.port == None) or (self.socketid != None):
            self.ip = ip
            self.port = port
            self.socketid = None
            self.close()

        contentFormatID = '0'
        if(self.contentFormat == socket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE):
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
        command = 'AT+SQNSD=1,1,' + str(port) + ',"' + ip + '",0,' + str(self.localport) + ',1'
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
