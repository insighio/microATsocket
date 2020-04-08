# microATsocket
A UDP socket implementation for Pycom devices based on Sequans AT commands that supports IPv6

Pycom devices (GPy, FiPy) that contain LTE CAT M1/NB1 modem of Sequans have a perfectly good support of usockets over LTE networks. They are based on the lwIP (lightweight IP) sockets included in the esp-idf (Espressif IoT Development Framework) and through PPP connection to the modem, they communicate to the outside world. They only major drawback is that in the current implementation of micropython / esp-idf / usocket there is no support to IPv6 sockets.

Meanwhile, many LTE CAT M1/NB1 networks operate with IPv6 only, thus making the Pycom device unusable.

A solution to this is to bypass the build-in network interface controllers and communicate directly with the included Sequans modem which has proper support to UDP sockets and IPv6.

# How To Use

The API is quite simple. It is based on the usocket API implementing the minimum set of functionality to be usable. So it is a drop-in replacement of the typical socket.

```python
from microATsocket import MicroATSocket
from network import LTE

lte = LTE()

# attach to network
# ...

#message as bytes
data = bytearray('{data:"testmessage"}')

# create socket instance providing the instance of the LTE modem
socket = MicroATSocket(lte)

# send data to specific IP (dummy IP and port used as example)
socket.sendto(data, ("2001:4860:4860::8888", 8888))

# receive data from the previously used IP.
# socket is still open from the 'sendto' operation
(resp, address) = socket.recvfrom()
print("Response: from ip:" + address[0] + ", port: " + address[1] + ", data: " + resp)

# close socket
socket.close()

```

For more detailed examples, take a look at the examples folder of the repository.

# Notes

* The modem needs to be attached and not connected. If the modem gets in "connected" mode, the system will establish a PPP connection to the modem. Thus when the send_at_cmd is called, it will need to suspend PPP and then send the AT command which is waste of time.

## Pycom limitation of AT command length

Pycom firmwares have a limitation at the length of the AT commands that they can send (still applies to the latest firmware which is 1.20.rc6).
That is:
* Max TX characters: 124
* Max Rx characters: 2048

Since in this socket implementation, all data are transferred through AT commands, this limitation directly affects the socket implementation as we can not send the maximum amount of data the modem can handle which is 1500 bytes per transfer.

Moreover, in case we require to send byte data instead of ascii messages, the bytes need to be expressed into a HEX string. In this case each byte is represented by 2 HEX characters thus limiting our maximum data per transmission from 124 character to 62 bytes.

To bypass this limitation and unlock the full capabilities of the modem, you will need to build a custom version of Pycom firmware using the [Pull Request 429](https://github.com/pycom/pycom-micropython-sigfox/pull/429) (at least till the time that this README has been written 08 Apr 2020). Should this fix is applied to the modem, it will increase the AT command length from 124 bytes to 1500 bytes which is the limit of the modem.
