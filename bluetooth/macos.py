import lightblue
from .btcommon import *

def discover_devices(duration=8, flush_cache=True, lookup_names=False,
        lookup_class=False, device_id=-1):
    # This is order of discovered device attributes in C-code.
    btAddresIndex = 0
    namesIndex = 1
    classIndex = 2

    # Use lightblue to discover devices on OSX.
    devices = lightblue.finddevices(getnames=lookup_names, length=duration)

    ret = list()
    for device in devices:
        item = [device[btAddresIndex], ]
        if lookup_names:
            item.append(device[namesIndex])
        if lookup_class:
            item.append(device[classIndex])

        # in case of address-only we return string not tuple
        if len(item) == 1:
            ret.append(item[0])
        else:
            ret.append(tuple(item))
    return ret


def lookup_name(address, timeout=10):
    return lightblue.finddevicename(address)


def find_service(name=None, uuid=None, address=None):
    results = []

    services = lightblue.findservices(addr=address, name=name, uuid=uuid)

    for tup in services:
        service = {}

        # LightBlue performs a service discovery and returns the found
        # services as a list of (device-address, service-port,
        # service-name, attributes) tuples.
        service["host"] = tup[0]
        service["port"] = tup[1]
        service["name"] = tup[2]

        service["description"] = None
        if SERVICE_DESCRIPTION_ATTRID in tup[3]:
            service["description"] = tup[3][SERVICE_DESCRIPTION_ATTRID]
        service["provider"] = None
        if PROVIDER_NAME_ATTRID in tup[3]:
            service["provider"] = tup[3][PROVIDER_NAME_ATTRID]
        service["protocol"] = None
        if PROTOCOL_DESCRIPTOR_LIST_ATTRID in tup[3]:
            service["protocol"] = tup[3][PROTOCOL_DESCRIPTOR_LIST_ATTRID]
        service["service-classes"] = []
        if SERVICE_CLASS_ID_LIST_ATTRID in tup[3]:
            service["service-classes"] = tup[3][SERVICE_CLASS_ID_LIST_ATTRID]
        service["profiles"] = []
        if BLUETOOTH_PROFILE_DESCRIPTOR_LIST_ATTRID in tup[3]:
            service["profiles"] = tup[3][BLUETOOTH_PROFILE_DESCRIPTOR_LIST_ATTRID]
        service["service-id"] = None
        if SERVICE_ID_ATTRID in tup[3]:
            service["service-id"] = tup[3][SERVICE_ID_ATTRID]

        results.append(service)

    return results


def advertise_service(sock, name, service_id="", service_classes=None,
        profiles=None, provider="", description="", protocols=None):
    raise NotImplementedError("Not implemented yet for MAC OS")


def stop_advertising(sock):
    raise NotImplementedError("Not implemented yet for MAC OS")


# ============================= BluetoothSocket ============================== #
class BluetoothSocket:

    def __init__(self, proto=RFCOMM, _sock=None):
        if _sock is None:
            _sock = lightblue.socket()
        self._sock = _sock

        if proto != RFCOMM:
            # name the protocol
            raise NotImplementedError("Not supported protocol")
        self._proto = lightblue.RFCOMM
        self._addrport = None

    def _getport(self):
        return self._addrport[1]

    def bind(self, addrport):
        self._addrport = addrport
        return self._sock.bind(addrport)

    def listen(self, backlog):
        return self._sock.listen(backlog)

    def accept(self):
        return self._sock.accept()

    def connect(self, addrport):
        return self._sock.connect(addrport)

    def send(self, data):
        return self._sock.send(data)

    def recv(self, numbytes):
        return self._sock.recv(numbytes)

    def close(self):
        return self._sock.close()

    def getsockname(self):
        return self._sock.getsockname()

    def setblocking(self, blocking):
        return self._sock.setblocking(blocking)

    def settimeout(self, timeout):
        return self._sock.settimeout(timeout)

    def gettimeout(self):
        return self._sock.gettimeout()

    def fileno(self):
        return self._sock.fileno()

    def dup(self):
        return BluetoothSocket(self._proto, self._sock)

    def makefile(self, mode, bufsize):
        return self.makefile(mode, bufsize)

# ============================= DeviceDiscoverer ============================= #

class DeviceDiscoverer:
    def __init__ (self):
        raise NotImplementedError("Not implemented yet for MAC OS")
