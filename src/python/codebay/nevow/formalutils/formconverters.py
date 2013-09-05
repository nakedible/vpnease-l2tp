""" Adapters created for formdatatypes for converting a type from and to string.
"""

from formal import converters, validation, iformal
from codebay.common import datatypes
from zope.interface import implements
import sys, re

class FormIPv4AddressSubnetToStringConverter(converters._Adapter):
    implements( iformal.IStringConvertible )
    """Converts datatypes.IPv4AddressSubnet -> String -> datatypes.IPv4AddressSubnet."""

    def fromType(self, value):
        if value is None:
            return None
        return value.toString()
    
    #
    #  XXX: why does this allow IPv4Addresses here?  Why not just always use
    #  IPv4AddressSubnet, and canonicalize to without /32 if that looks better?
    #
    def toType(self, value):
        if not(value is None):
            value = value.strip()
        if not value:
            return None
        try:
            if (value.find('/') > 0):
                value = datatypes.IPv4AddressSubnet.fromString(value)
            else:
                value = datatypes.IPv4Address.fromString(value)
        except datatypes.InvalidIPAddress:
            raise validation.FieldValidationError('Invalid IP address')
        except datatypes.InvalidSubnet:
            raise validation.FieldValidationError('Invalid subnet mask (CIDR)')
        except:
            # XXX: Error logs?
            print "Unknown field error. System exception message: ", str(sys.exc_info()[0]) 
            raise validation.FieldValidationError('Invalid IP address')
            
        return value
        
class FormIPv4SubnetToStringConverter(converters._Adapter):
    implements( iformal.IStringConvertible )
    """Converts datatypes.IPv4Subnet -> String -> datatypes.IPv4Subnet."""

    def fromType(self, value):
        if value is None:
            return None
        return value.toString()
    
    def toType(self, value):
        if not(value is None):
            value = value.strip()
        if not value:
            return None
        try:
            if (value.find('/') > 0):
                value = datatypes.IPv4Subnet.fromString(value)
            else:
                value = datatypes.IPv4Subnet.fromString(value + '/32')
        except datatypes.InvalidSubnet:
            raise validation.FieldValidationError('Invalid subnet')
        except:
            # XXX: Error logs?
            print "Unknown field error. System exception message: ", str(sys.exc_info()[0]) 
            raise validation.FieldValidationError('Invalid subnet')

        return value
        
class FormSubnetMaskToStringConverter(converters._Adapter):
    implements( iformal.IStringConvertible )

    """Converts subnet mask -> string -> subnet mask. Subnet mask format is xxx.xxx.xxx.xxx."""
    def fromType(self, value):
        if value is None:
            return None
        return value.toString()
        
    def toType(self, value):
        if not(value is None):
            value = value.strip()
        if not value:
            return None
        try:
            temp_mask = datatypes.mask_to_cidr(value)
            value = datatypes.IPv4Address.fromString(value)
        except datatypes.InvalidSubnet:
            raise validation.FieldValidationError('Invalid subnet mask')
        except:
            print "Unknown field error. System exception message: ", sys.exc_info()[0] 
            raise validation.FieldValidationError('Invalid subnet mask')
        
        return value
            
class FormIPv4AddressToStringConverter(converters._Adapter):
    implements( iformal.IStringConvertible )
    """Converts datatypes.IPv4Address -> string -> datatypes.IPv4Address."""

    def fromType(self, value):
        if value is None:
            return None
        return value.toString()
    
    def toType(self, value):
        if not(value is None):
            value = value.strip()
        if not value:
            return None
        try:
            value = datatypes.IPv4Address.fromString(value)
        except datatypes.InvalidIPAddress:
            raise validation.FieldValidationError('Invalid IP address')
        except:
            print "Unknown field error. System exception message: ", sys.exc_info()[0] 
            raise validation.FieldValidationError('Invalid IP address')
        
        return value
        
class FormFloatToStringConverter(converters._Adapter):
    implements( iformal.IStringConvertible )

    """Converts FormFloat -> String -> FormFloat. FormFloat accepts both , and . as a decimal separator."""
    
    def fromType(self, value):
        if value is None:
            return None
        return str(value)
        
    def toType(self, value):
        if not(value is None):
            value = value.strip()
        if not value:
            return None
        value = value.replace(',','.')
        try:
            value = float(value)
        except:
            raise validation.FieldValidationError('Invalid number')
        
        return value

class FormIPv4AddressRangeToStringConverter(converters._Adapter):
    implements( iformal.IStringConvertible )
    """Converts IPv4 address range -> string -> address range.

    IP address range is in format xxx.xxx.xxx.xxx - yyy.yyy.yyy.yyy.
    """

    def fromType(self, value):
        if value is None:
            return None
        return value.toString()
        
    def toType(self, value):
        if not(value is None):
            value = value.strip()
        if not value:
            return None
        try:
            value = datatypes.IPv4AddressRange.fromString(value)         
        except:
            raise validation.FieldValidationError('Invalid IP address range')
        
        return value
        
class FormIPv4SubnetListToStringConverter(converters._Adapter):
    implements( iformal.IStringConvertible )
    """Converts list of IPv4 subnets -> string -> list of IPv4 subnets."""
    
    def fromType(self, value):
        if value is None:
            return None
        return ','.join(map(lambda x : x.toString(), value))
        
    def toType(self, value):
        if not(value is None):
            value = value.strip()
        if not value:
            return None
        
        result_list = []
        for x in re.split(',|;', value):
            try:                
                x = x.strip()
                    
                if x.find('/') > 0:
                    result_list.append(datatypes.IPv4Subnet.fromString(x))
                else:
                    result_list.append(datatypes.IPv4Subnet.fromString(x + '/32'))

            except datatypes.InvalidSubnet:
                raise validation.FieldValidationError('Invalid subnet in list')
            except:
                # XXX: Error logs?
                print "Unknown field error. System exception message: ", str(sys.exc_info()[0]) 
                raise validation.FieldValidationError('Invalid subnet in list')

        return result_list
