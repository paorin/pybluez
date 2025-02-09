# Copyright (c) 2009 Bea Lam. All rights reserved.
#
# This file is part of LightBlue.
#
# LightBlue is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LightBlue is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with LightBlue.  If not, see <http://www.gnu.org/licenses/>.

# Mac OS X main module implementation.

import types
import warnings

import Foundation
import AppKit
import objc
from objc import super
import IOBluetooth

from . import _lightbluecommon
from . import _macutil
from . import _bluetoothsockets


# public attributes
__all__ = ("finddevices", "findservices", "finddevicename",
           "selectdevice", "selectservice",
           "socket")


def finddevices(getnames=True, length=10):
    inquiry = _SyncDeviceInquiry()
    inquiry.run(getnames, length)
    devices = inquiry.getfounddevices()
    return devices


def findservices(addr=None, name=None, uuid=None):
    if addr is None:
        try:
            founddevices = finddevices()
        except _lightbluecommon.BluetoothError as e:
            msg = "findservices() failed, " +\
                    "error while finding devices: " + str(e)
            raise _lightbluecommon.BluetoothError(msg)

        addresses = [dev[0] for dev in founddevices]
    else:
        addresses = [addr]

    services = []
    for devaddr in addresses:
        iobtdevice = IOBluetooth.IOBluetoothDevice.withAddressString_(devaddr)
        if not iobtdevice and addr is not None:
            msg = "findservices() failed, " +\
                    "failed to find " + devaddr
            raise _lightbluecommon.BluetoothError(msg)
        elif not iobtdevice:
            continue

        try:
            lastseen = iobtdevice.getLastServicesUpdate()
            if lastseen is None or lastseen.timeIntervalSinceNow() < -2:
                # perform SDP query to update known services.
                # wait at least a few seconds between service discovery cos
                # sometimes it doesn't work if doing updates too often.
                # In future should have option to not do updates.
                serviceupdater = _SDPQueryRunner.alloc().init()
                try:
                    serviceupdater.query(iobtdevice)  # blocks until updated
                except _lightbluecommon.BluetoothError as e:
                    msg = "findservices() couldn't get services for %s: %s" % \
                        (iobtdevice.getNameOrAddress(), str(e))
                    warnings.warn(msg)
                    # or should I use cached services instead of warning?
                    # but sometimes the cached ones are totally wrong.

            filtered = _searchservices(iobtdevice, name=name, uuid=uuid)

            services.extend([_getservicetuple(s) for s in filtered])
        finally:
            # close baseband connection (not sure if this is necessary, but
            # sometimes the transport connection seems to stay open?)
            iobtdevice.closeConnection()

    return services


def finddevicename(address, usecache=True):
    if not _lightbluecommon._isbtaddr(address):
        raise TypeError("%s is not a valid bluetooth address" % str(address))

    device = IOBluetooth.IOBluetoothDevice.withAddressString_(address)
    if usecache:
        name = device.name()
        if name is not None:
            return name

    # do name request with timeout of 10 seconds
    result = device.remoteNameRequest_withPageTimeout_(None, 10000)
    if result == _macutil.kIOReturnSuccess:
        return device.name()
    raise _lightbluecommon.BluetoothError(
        "Could not find device name for %s" % address)


### socket ###

def socket(proto=_lightbluecommon.RFCOMM):
    return _bluetoothsockets._getsocketobject(proto)


### GUI ###

def selectdevice():
    import IOBluetoothUI
    gui = IOBluetoothUI.IOBluetoothDeviceSelectorController.deviceSelector()

    # try to bring GUI to foreground by setting it as floating panel
    # (if this is called from pyobjc app, it would automatically be in foreground)
    try:
        gui.window().setFloatingPanel_(True)
    except:
        pass

    # show the window and wait for user's selection
    response = gui.runModal()   # problems here if transferring a lot of data??
    if response == AppKit.NSRunStoppedResponse:
        results = gui.getResults()
        if len(results) > 0:  # should always be > 0, but check anyway
            devinfo = _getdevicetuple(results[0])

            # sometimes the baseband connection stays open which causes
            # problems with connections w so close it here, see if this fixes
            # it
            dev = IOBluetooth.IOBluetoothDevice.withAddressString_(devinfo[0])
            if dev.isConnected():
                dev.closeConnection()

            return devinfo

    # user cancelled selection
    return None


def selectservice():
    import IOBluetoothUI
    gui = IOBluetoothUI.IOBluetoothServiceBrowserController.serviceBrowserController_(
            _macutil.kIOBluetoothServiceBrowserControllerOptionsNone)

    # try to bring GUI to foreground by setting it as floating panel
    # (if this is called from pyobjc app, it would automatically be in foreground)
    try:
        gui.window().setFloatingPanel_(True)
    except:
        pass

    # show the window and wait for user's selection
    response = gui.runModal()
    if response == AppKit.NSRunStoppedResponse:
        results = gui.getResults()
        if len(results) > 0:  # should always be > 0, but check anyway
            serviceinfo = _getservicetuple(results[0])

            # sometimes the baseband connection stays open which causes
            # problems with connections ... so close it here, see if this fixes
            # it
            dev = IOBluetooth.IOBluetoothDevice.deviceWithAddressString_(serviceinfo[0])
            if dev.isConnected():
                dev.closeConnection()

            return serviceinfo

    # user cancelled selection
    return None


### classes ###

class _SDPQueryRunner(Foundation.NSObject):
    """
    Convenience class for performing a synchronous or asynchronous SDP query
    on an IOBluetoothDevice.
    """

    @objc.python_method
    def query(self, device, timeout=10.0):
        # do SDP query
        err = device.performSDPQuery_(self)
        if err != _macutil.kIOReturnSuccess:
            raise _lightbluecommon.BluetoothError(err, self._errmsg(device))

        # performSDPQuery_ is async, so block-wait
        self._queryresult = None
        if not _macutil.waituntil(lambda: self._queryresult is not None,
                                          timeout):
            raise _lightbluecommon.BluetoothError(
                "Timed out getting services for %s" % \
                    device.getNameOrAddress())
        # query is now complete
        if self._queryresult != _macutil.kIOReturnSuccess:
            raise _lightbluecommon.BluetoothError(
                self._queryresult, self._errmsg(device))

    def sdpQueryComplete_status_(self, device, status):
        # can't raise exception during a callback, so just keep the err value
        self._queryresult = status
        _macutil.interruptwait()
    sdpQueryComplete_status_ = objc.selector(
        sdpQueryComplete_status_, signature=b"v@:@i")    # accept object, int

    @objc.python_method
    def _errmsg(self, device):
        return "Error getting services for %s" % device.getNameOrAddress()


class _SyncDeviceInquiry:

    def __init__(self):
        super().__init__()

        self._inquiry = _AsyncDeviceInquiry.alloc().init()
        self._inquiry.cb_completed = self._inquirycomplete

        self._inquiring = False

    def run(self, getnames, duration):
        if self._inquiring:
            raise _lightbluecommon.BluetoothError(
                "Another inquiry in progress")

        # set inquiry attributes
        self._inquiry.updatenames = getnames
        self._inquiry.length = duration

        # start the inquiry
        err = self._inquiry.start()
        if err != _macutil.kIOReturnSuccess:
            raise _lightbluecommon.BluetoothError(
                err, "Error starting device inquiry")

        # if error occurs during inquiry, set _inquiryerr to the error code
        self._inquiryerr = _macutil.kIOReturnSuccess

        # wait until the inquiry is complete
        self._inquiring = True
        _macutil.waituntil(lambda: not self._inquiring)

        # if error occured during inquiry, raise exception
        if self._inquiryerr != _macutil.kIOReturnSuccess:
            raise _lightbluecommon.BluetoothError(self._inquiryerr,
                "Error during device inquiry")

    def getfounddevices(self):
        # return as list of device-info tuples
        return [_getdevicetuple(device) for device in \
                    self._inquiry.getfounddevices()]

    def _inquirycomplete(self, err, aborted):
        if err != 188:      # no devices found
            self._inquiryerr = err
        self._inquiring = False
        _macutil.interruptwait()

    def __del__(self):
        self._inquiry.__del__()
        super().__del__()



# Wrapper around IOBluetoothDeviceInquiry, with python callbacks that you can
# set to receive callbacks when the inquiry is started or stopped, or when it
# finds a device.
#
# This discovery doesn't block, so it could be used in a PyObjC application
# that is running an event loop.
#
# Properties:
#   - 'length': the inquiry length (seconds)
#   - 'updatenames': whether to update device names during the inquiry
#     (i.e. perform remote name requests, which will take a little longer)
#
class _AsyncDeviceInquiry(Foundation.NSObject):

    # NSObject init, not python __init__
    def init(self):
        try:
            attr = IOBluetooth.IOBluetoothDeviceInquiry
        except AttributeError:
            raise ImportError("Cannot find IOBluetoothDeviceInquiry class " +\
                "to perform device discovery. This class was introduced in " +\
                "Mac OS X 10.4, are you running an earlier version?")

        self = super().init()
        self._inquiry = \
            IOBluetooth.IOBluetoothDeviceInquiry.inquiryWithDelegate_(self)

        # callbacks
        self.cb_started = None
        self.cb_completed = None
        self.cb_founddevice = None

        return self

    # length property
    @objc.python_method
    def _setlength(self, length):
        self._inquiry.setInquiryLength_(length)
    length = property(
            lambda self: self._inquiry.inquiryLength(),
            _setlength)

    # updatenames property
    @objc.python_method
    def _setupdatenames(self, update):
        self._inquiry.setUpdateNewDeviceNames_(update)
    updatenames = property(
            lambda self: self._inquiry.updateNewDeviceNames(),
            _setupdatenames)

    # returns error code
    def start(self):
        return self._inquiry.start()

    # returns error code
    def stop(self):
        return self._inquiry.stop()

    # returns list of IOBluetoothDevice objects
    def getfounddevices(self):
        return self._inquiry.foundDevices()

    def __del__(self):
        super().dealloc()


    #
    # delegate methods follow (these are called by the internal
    # IOBluetoothDeviceInquiry object when inquiry events occur)
    #

    # - (void)deviceInquiryDeviceFound:(IOBluetoothDeviceInquiry*)sender
    #                           device:(IOBluetoothDevice*)device;
    def deviceInquiryDeviceFound_device_(self, inquiry, device):
        if self.cb_founddevice:
            self.cb_founddevice(device)
    deviceInquiryDeviceFound_device_ = objc.selector(
        deviceInquiryDeviceFound_device_, signature=b"v@:@@")

    # - (void)deviceInquiryComplete:error:aborted;
    def deviceInquiryComplete_error_aborted_(self, inquiry, err, aborted):
        if self.cb_completed:
            self.cb_completed(err, aborted)
    deviceInquiryComplete_error_aborted_ = objc.selector(
        deviceInquiryComplete_error_aborted_, signature=b"v@:@iZ")

    # - (void)deviceInquiryStarted:(IOBluetoothDeviceInquiry*)sender;
    def deviceInquiryStarted_(self, inquiry):
        if self.cb_started:
            self.cb_started()

    # - (void)deviceInquiryDeviceNameUpdated:device:devicesRemaining:
    def deviceInquiryDeviceNameUpdated_device_devicesRemaining_(self, sender,
                                                              device,
                                                              devicesRemaining):
        pass

    # - (void)deviceInquiryUpdatingDeviceNamesStarted:devicesRemaining:
    def deviceInquiryUpdatingDeviceNamesStarted_devicesRemaining_(self, sender,
                                                                devicesRemaining):
        pass


### utility methods ###

def _searchservices(device, name=None, uuid=None):
    """
    Searches the given IOBluetoothDevice using the specified parameters.
    Returns an empty list if the device has no services.

    uuid should be a 16-bit UUID.
    """
    if not isinstance(device, IOBluetooth.IOBluetoothDevice):
        raise ValueError("device must be IOBluetoothDevice, was %s" % \
            type(device))

    services = []
    for s in device.services():
        if uuid and not s.hasServiceFromArray_([IOBluetooth.IOBluetoothSDPUUID.uuid16_(uuid)]):
            continue
        if name is None or s.getServiceName() == name:
            services.append(s)
    return services

def _getdevicetuple(iobtdevice):
    """
    Returns an (addr, name, COD) device tuple from a IOBluetoothDevice object.
    """
    addr = _macutil.formatdevaddr(iobtdevice.getAddressString())
    name = iobtdevice.getName()
    cod = iobtdevice.getClassOfDevice()
    return (addr, name, cod)


def _getservicetuple(servicerecord):
    """
    Returns a (device-addr, service-channel, service-name, attributes) tuple
    from the given IOBluetoothSDPServiceRecord.
    """
    # TODO: get service attributes with servicerecord.getAttributes
    addr = _macutil.formatdevaddr(servicerecord.getDevice().getAddressString())
    name = servicerecord.getServiceName()
    try:
        result, channel = servicerecord.getRFCOMMChannelID_(None) # pyobjc 2.0
    except TypeError:
        result, channel = servicerecord.getRFCOMMChannelID_()
    if result != _macutil.kIOReturnSuccess:
        try:
            result, channel = servicerecord.getL2CAPPSM_(None) # pyobjc 2.0
        except:
            result, channel = servicerecord.getL2CAPPSM_()
        if result != _macutil.kIOReturnSuccess:
            channel = None
    return (addr, channel, name, servicerecord.attributes())

