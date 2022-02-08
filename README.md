# microATsocket
A UDP socket implementation for Pycom devices based on Sequans AT commands that supports IPv4/IPv6

Pycom devices (GPy, FiPy) that contain LTE CAT M1/NB1 modem of Sequans have a perfectly good support of usockets over LTE networks. They are based on the lwIP (lightweight IP) sockets included in the esp-idf (Espressif IoT Development Framework) and through a PPP connection between the system and the modem, they communicate to the outside world. They only major drawback is that in the current implementation of micropython / esp-idf / usocket there is no support to IPv6 sockets.

Meanwhile, many LTE CAT M1/NB1 networks operate with IPv6 only, thus making the Pycom device unusable.

A solution to this is to bypass the build-in network interface controllers and communicate directly with the included Sequans modem which has proper support to UDP sockets and IPv6.

# How To Use

First make sure you have the submodules needed.

```bash
git submodule update --init
```

The API is quite simple. It is based on the usocket API implementing the minimum set of functionality to be usable. So it is a drop-in replacement of the typical socket.

## Example with IP
```python
import microATsocket as socket
from network import LTE

lte = LTE()

# attach to network
# ...

#message as bytes
data = bytearray('{data:"testmessage"}')

# create socket instance providing the instance of the LTE modem
sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
sock.setModemInstance(lte)

# send data to specific IP (dummy IP and port used as example)
sock.sendto(data, ("2001:4860:4860::8888", 8080))

# receive data from the previously used IP.
# socket is still open from the 'sendto' operation
(resp, address) = sock.recvfrom()
print("Response: from ip:" + address[0] + ", port: " + str(address[1]) + ", data: " + str(binascii.hexlify(bytearray(resp))))

# close socket
sock.close()

```

## Example with URL resolve

The socket.getaddrinfo implementation has a deviation from the typical usocket.getaddrinfo.
In microAtsocket it need to be called on the instance of the socket instead of calling a function in the module.

```python
lte = LTE()

# attach to network
# ...

#message as bytes
data = bytearray('{data:"testmessage"}')

# create socket instance providing the instance of the LTE modem
sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
sock.setModemInstance(lte)

# getaddrinfo needs to be called on the instance of socket
resolvedIPs = sock.getaddrinfo("google.com", 5683)

# send data to specific IP (dummy IP and port used as example)
sock.sendto(data, resolvedIPs[0][-1])

# receive data from the previously used IP.
# socket is still open from the 'sendto' operation
(resp, address) = sock.recvfrom()
print("Response: from ip:" + address[0] + ", port: " + str(address[1]) + ", data: " + str(binascii.hexlify(bytearray(resp))))

```

## Example with custom DNS server

```python
# create socket instance providing the instance of the LTE modem
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setModemInstance(lte)

# the first argument is ignored, though it is added for API compatibility
sock.dnsserver(0, "8.8.4.4")
# getaddrinfo needs to be called on the instance of socket
resolvedIPs = sock.getaddrinfo("google.com", 5683)

print("Resolved IP: " + str(resolvedIPs[0][-1]))
```

For more detailed examples, take a look at the [examples folder](https://github.com/insighio/microATsocket/tree/master/examples) of the repository.

# Notes

* The modem needs to be attached and not connected. If the modem gets in "connected" mode, the system will establish a PPP connection to the modem. Thus when the send_at_cmd is called, it will need to suspend PPP and then send the AT command which is waste of time.

## Pycom limitation of AT command length

Pycom firmwares have a limitation at the length of the AT commands that they can send (still applies to the latest firmware which is 1.20.rc6).
That is:
* Max TX characters: 124
* Max Rx characters: 2048

Since in this socket implementation, all data are transferred through AT commands, this limitation directly affects the socket implementation as we can not send the maximum amount of data the modem can handle which is 1500 bytes per transfer.

Moreover, in case we require to send byte data instead of ASCII messages, the bytes need to be expressed into a HEX string. In this case each byte is represented by 2 HEX characters thus limiting our maximum data per transmission from 124 character to 62 bytes. This approach is the default behavior of MicroATSocket to be able to handle any data provided.

To enable the transmission of ASCII data and increase the limit for 62 bytes to 124 characters, after creating the instance of the socket, set the message format of the socket to **SOCKET_MESSAGE_ASCII** (check [examples/pycom_cellular_send_receive_text.py](https://github.com/insighio/microATsocket/blob/master/examples/pycom_cellular_send_receive_text.py))

```python
socket = MicroATSocket(lte)
socket.setMessageFormat(MicroATSocket.SOCKET_MESSAGE_FORMAT.SOCKET_MESSAGE_ASCII)
```

### How to bypass the AT command length limitation

To bypass this limitation and unlock the full capabilities of the modem, you will need to build a custom version of Pycom firmware using the [Pull Request 429](https://github.com/pycom/pycom-micropython-sigfox/pull/429) (at least for the time being, till the Pull Request is accepted).

Should this fix is applied to the Pycom device, it will increase the AT command length from 124 bytes to 3000 characters which is the limit of the modem (3000 HEX characters -> 1500 bytes).

# Future work and issues

The socket implementation can be expanded greatly so new features can be added based on suggestions.
