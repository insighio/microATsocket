from network import LTE
import machine
import utime
import binascii
import dns_query

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

#attached = True
attached = attachNBIoT(_NBIOT_MAX_CONNECTION_TIMEOUT_MSEC)
print("LTE ok: " + str(attached))

if(attached):
    socket = MicroATSocket(lte)

    url='google.com'
    dns_server="2001:4860:4860::8888"
    ipv6_only = True

    resolvedIPs = dns_query.dns_resolve(socket, url, dns_server, ipv6_only)

    print("Resolved IP list: " + str(resolvedIPs))

    #close socket
    socket.close()

lte.detach()
