from twisted.python.components import registerAdapter
from formal.widget import *
from formdatatypes import *
from formal import iformal
from formal import converters
from formconverters import *

# Own converters
registerAdapter(TextInput, FormIPv4AddressSubnet, iformal.IWidget)
registerAdapter(FormIPv4AddressSubnetToStringConverter, FormIPv4AddressSubnet, iformal.IStringConvertible)
registerAdapter(TextInput, FormIPv4Subnet, iformal.IWidget)
registerAdapter(FormIPv4SubnetToStringConverter, FormIPv4Subnet, iformal.IStringConvertible)
registerAdapter(TextInput, FormSubnetMask, iformal.IWidget)
registerAdapter(FormSubnetMaskToStringConverter, FormSubnetMask, iformal.IStringConvertible)
registerAdapter(TextInput, FormIPv4Address, iformal.IWidget)
registerAdapter(FormIPv4AddressToStringConverter, FormIPv4Address, iformal.IStringConvertible)
registerAdapter(TextInput, FormFloat, iformal.IWidget)
registerAdapter(FormFloatToStringConverter, FormFloat, iformal.IStringConvertible)
registerAdapter(TextInput, FormIPv4AddressRange, iformal.IWidget)
registerAdapter(FormIPv4AddressRangeToStringConverter, FormIPv4AddressRange, iformal.IStringConvertible)
registerAdapter(TextInput, FormIPv4SubnetList, iformal.IWidget)
registerAdapter(FormIPv4SubnetListToStringConverter, FormIPv4SubnetList, iformal.IStringConvertible)
