from network import LTE
import utime
import binascii
import ure
import uos

# Values acquired from pycom firmware
# pycom-micropython-sigfox/lib/lwip/src/include/lwip/sockets.h
AF_INET = 2
AF_INET6 = 10

SOCK_STREAM = 1  #not supported
SOCK_DGRAM  = 2
SOCK_RAW    = 3  #not supported

DNS_SERVER_IP   = "8.8.8.8"
DNS_SERVER_IPV6 = "2001:4860:4860::8888"

LOCAL_PORT_DEFAULT = 8080

# MAX 6 sockets. limitation imposed by Sequans +1 for indexing convenience
#[<dummy>, <sock1>, <sock2>, <sock3>, <sock4>, <sock5>]
# <sock6> reserved for DNS
sockets_in_use = [0, 0, 0, 0, 0, 0, 0]

def has_available_sockets():
    for sock in sockets_in_use:
        if(sock == 0):
            return True
    return False

def get_first_available_socket():
    for idx, val in enumerate(sockets_in_use):
        if(idx == 0):
            continue
        if(val == 0):
            sockets_in_use[idx] = 1
            return idx
    return None

def release_socket(idx):
    if(idx < 1 or idx > len(sockets_in_use)):
        return False

    sockets_in_use[idx] = 0
    return True


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
        if(family != AF_INET and family != AF_INET6 ):
            raise Exception("address family not supported")

        if(type != SOCK_DGRAM):
            raise Exception("socket type not supported")

        self.ip = None
        self.port = None
        self.localport = LOCAL_PORT_DEFAULT
        self.hasExplicitLocalPort = False
        self.family = family
        self.type = type
        #self.recvRegex = "\+SQNSRING: (\\d+),(\\d+)"
        self.recvRegex = "\+SQNSRING: (\\d+)"
        self.contentFormat = socket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE
        self.dns_server = DNS_SERVER_IP
        if(family == AF_INET6):
            self.dns_server = DNS_SERVER_IPV6
        self.socketid = get_first_available_socket()
        self.isconnected = False

    def getaddrinfo(self, host, port):
        import dns_query

        ipv6_only = (self.family == AF_INET6)

        sock = socket(self.family, SOCK_DGRAM)
        sock.setModemInstance(self.modem)
        resolvedIPs = dns_query.dns_resolve(sock, host, self.dns_server, ipv6_only, True)
        sock.close()

        responseList = []
        for res in resolvedIPs:
            family = None
            if res[1] == 'A':
                family = AF_INET
            elif res[1] == 'AAAA':
                family = AF_INET6
            responseList.append((family, SOCK_STREAM, 0, '', (res[0], port)))
        return responseList

    def close(self, do_release_socket=False):
        if self.socketid != None:
            response = self.sendAtCommand('AT+SQNSH=' + str(self.socketid))
            if(response.find("OK") != -1):
                self.isconnected = False
            utime.sleep_ms(2000)
            if do_release_socket:
                release_socket(self.socketid)
                self.reset()

    def bind(self, address):
        self.localport = address[1]
        self.hasExplicitLocalPort = True

    def sendto(self, bytes, address):
        ip = address[0]
        port = address[1]

        if(not self.open(ip, port)):
            print("Failed to open socket, aborting.")
            return -1

        arrayHexBytes = bytes

        # if format is BYTE, convert the byte array to hex string
        if(self.contentFormat == socket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE):
          arrayHexBytes = binascii.hexlify(bytearray(bytes))

        byteLength = len(bytes)

        response = self.sendAtCommand('AT+SQNSSENDEXT=' + str(self.socketid) + ',' + str(byteLength))

        #deactivating the timeout argument for now as it is not compatible
        #with the stock Pycom firmware.
        #response = self.sendAtCommand(arrayHexBytes, 15000)

        response = self.sendAtCommand(arrayHexBytes)

        return len(bytes)

    def recvfrom(self, bufsize=1024):
        # send empty space to wait for an incoming notification from SQNSRING
        badResult = (None, None)

        if(not self.open(self.ip, self.port)):
            print("Failed to open socket, aborting.")
            return badResult

        resp = self.sendAtCommand("Pycom_Dummy")

        # search for the URC
        match = ure.search(self.recvRegex, resp)
        if match == None:
            return badResult

        # if the data comes from an other active socket
        if(match.group(1) != str(self.socketid)):
            return badResult

        # +SQNSRING -> get notified of incoming data
        # +SQNSRECV -> read data
        command = "AT+SQNSRECV=" + match.group(1) + "," + str(bufsize)
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

    def open(self, ip, port):
        if(self.ip == ip or self.port == port and self.isconnected):
            return True

        if(not has_available_sockets()):
            raise Exception("max number of sockets reached")

        #if(self.isconnected):
        self.close()

        if(self.ip == None and self.port == None):
            self.ip = ip
            self.port = port
            if(self.socketid == None):
                self.socketid = get_first_available_socket()

        if not self.hasExplicitLocalPort:
            self.localport = LOCAL_PORT_DEFAULT + (int.from_bytes(uos.urandom(2),"big") % 2000)

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
        configuration = str(self.socketid) + ',1,' + contentFormatID + ',0,0,' + contentFormatID + ',0,0'
        resp = self.sendAtCommand('AT+SQNSCFGEXT?')

        if(resp.find(configuration) == -1):
            self.sendAtCommand('AT+SQNSCFGEXT='+configuration)

        self.sendAtCommand('AT+SQNSI='+ str(self.socketid))
        self.sendAtCommand('AT+CEREG?')
        self.sendAtCommand('AT+CFUN?')
        self.sendAtCommand('AT+CGATT?')

        # <socket ID>, <UDP>, <remote port>, <remote IP>,0,<local port>, <online mode>
        command = 'AT+SQNSD=' + str(self.socketid) + ',1,' + str(port) + ',"' + ip + '",0,' + str(self.localport) + ',1,0'
        response = self.sendAtCommand(command, 4)
        self.isconnected = (response.find("OK") != -1)

        return self.isconnected

    ######################################################################
    # Private functions

    def reset(self):
        self.localport = LOCAL_PORT_DEFAULT
        self.hasExplicitLocalPort = False
        self.socketid = None

    # If stock firmware is used, this function needs to be used
    def sendAtCommand(self, command, max_tries=1):
        if self.modem == None:
            raise Exception("No modem instance assigned")

        response = ""
        cnt = 0
        while True:
            cnt += 1
            response = self.modem.send_at_cmd(command)

            if(response.find("OK") != -1 or cnt == max_tries):
                break
            else:
                utime.sleep_ms(5000)

        return response

    # This function is not supported yet by the stop Pycom firmware
    def sendAtCommandWithTimeout(self, command, timeout, max_tries=1):
        if self.modem is None:
            raise Exception("No modem instance assigned")

        response = ""
        cnt = 0
        while True:
            cnt += 1
            # print("[AT] => " + str(command))
            response = self.modem.send_at_cmd(command, timeout)
            # print("[AT] <= " + response)

            if(response.find("OK") != -1 or cnt == max_tries):
                break

        return response
