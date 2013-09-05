"""
This file contains data types used with formal.
"""

from formal.types import Type

class FormIPv4AddressSubnet(Type):
    """IP Address with optional subnet datatype. Address may or may not contain a subnet in CIDR format."""
    pass

class FormIPv4Subnet(Type):
    """IP subnet datatype."""
    pass

class FormSubnetMask(Type):
    """Subnet mask data type."""
    pass

class FormIPv4Address(Type):
    """IP address data type."""
    pass

class FormFloat(Type):
    """Float field that accepts both 2.5 and 2,5."""
    pass

class FormIPv4AddressRange(Type):
    """IP address range."""
    pass

class FormIPv4SubnetList(Type):
    """A list of IP subnets (in CIDR format). List separator can be either , or ;"""
    pass
