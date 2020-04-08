from network import LTE
import machine
import utime
import binascii

from microATsocket import MicroATSocket

_NBIOT_MAX_CONNECTION_TIMEOUT_MSEC=30000
_NBIOT_APN="iot"

# attach to network
# IMPORTANT: note that we do not connect. we need to attach instead.
def attachNBIoT(timeout):
    print("Connecting LTE...")
    if lte.isattached():
        return True

    lte.send_at_cmd('AT+CFUN=0')
    lte.send_at_cmd('AT+CMEE=2')
    lte.send_at_cmd('AT+CGDCONT=1,"IPV6","' + _NBIOT_APN + '"')
    lte.send_at_cmd('AT+CFUN?')

    start_time_activation = utime.ticks_ms()

    lte.send_at_cmd('AT+CFUN=1')
    while not lte.isattached() and (utime.ticks_ms()-start_time_activation < timeout):
        print(".", end="")
        machine.idle()

    print("")
    return lte.isattached()


print("Initializing LTE...")
lte = LTE()
lte.init()

attached = attachNBIoT(_NBIOT_MAX_CONNECTION_TIMEOUT_MSEC)
print("LTE ok: " + str(attached))

if(attached):
    #message as bytes
    data = bytearray('{data:"testmessage"}')

    # create socket instance providing the instance of the LTE modem
    socket = MicroATSocket(lte)

    # set that the incoming/outgoing data are bytes in hex
    # the following cal can be omitted as default format for socket is SOCKET_MESSAGE_BYTE
    #socket.setMessageFormat(MicroATSocket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_BYTE)

    # send data to specific IP
    socket.sendto(data, ("2001:4860:4860::8888", 8888))

    # receive data from the previously used IP.
    # socket is still open from the 'sendto' operation
    (resp, address) = socket.recvfrom()
    if(resp != None and address != None):
        print("Response: from ip:" + address[0] + ", port: " + str(address[1]) + ", data: " + str(binascii.hexlify(bytearray(resp))))
    else:
        print("No data received")

    # close socket
    socket.close()

LTE().detach()
