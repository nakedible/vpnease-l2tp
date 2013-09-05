""" 
Form datatype validators contains additional validators, which could be used
with form datatypes. These validators are optional.
"""

import formal
from formal import iformal
import formdatatypes as dt
import datatypestext
from zope.interface import implements


# IP address validators
class PrivateIP(object):
    implements(iformal.IValidator)
    """
    Checks that the ip address is from the private IP address.
    XXX: Only an example, implementation missing.
    """
    
    def validate(self, field, value):
        txt = datatypestext.IPAddressTexts()
        name = 'PrivateIP()'
        
        if not(isinstance(field, dt.IPAddress)):
            raise formal.FieldValidationError(name + txt.VALIDATOR_ONLY_FOR_IPADDRESS)
                
        if value is None:
            return
             
        pass
