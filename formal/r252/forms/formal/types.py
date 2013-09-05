"""
Form types.
"""

try:
    import decimal
    haveDecimal = True
except ImportError:
    haveDecimal = False
from zope.interface import implements

from formal import iformal, validation


class Type(object):

    implements( iformal.IType )

    # Name of the instance
    name = None
    # Value to use if no value entered
    missing = None
    # Instance cannot be changed
    immutable = False
    # List of validators to test the value against
    validators = ()

    def __init__(self, name=None, required=None, missing=None, immutable=None, validators=None):
        if name is not None:
            self.name = name
        if missing is not None:
            self.missing = missing
        if immutable is not None:
            self.immutable = immutable
        if validators is not None:
            self.validators = list(validators)
        else:
            self.validators = list(self.validators)
        if required is None:
            required = self.required
        if required:
            self.validators.append(validation.RequiredValidator())

    def validate(self, value):
        for validator in self.validators:
            validator.validate(self, value)
        if value is None:
            value = self.missing
        return value

    def hasValidator(self, validatorType):
        """
        Check for the existance of a validator of a specific type.
        """
        for v in self.validators:
            if isinstance(v, validatorType):
                return True
        return False

    def required():
        def get(self):
            return self.hasValidator(validation.RequiredValidator)
        return get,
    required = property(*required())


class String(Type):

    # Strip the value before validation
    strip = False

    def __init__(self, **k):
        strip = k.pop('strip', None)
        if strip is not None:
            self.strip = strip
        super(String, self).__init__(**k)

    def validate(self, value):
        if value is not None and self.strip:
            value = value.strip()
        if not value:
            value = None
        return super(String, self).validate(value)


class Integer(Type):
    pass


class Float(Type):
    pass


class Boolean(Type):
    pass


class Date(Type):
    pass


class Time(Type):
    pass


if haveDecimal:
    class Decimal(Type):
        """
        Forms type for Python 2.4's decimal.Decimal type.
        """


class Sequence(Type):

    # Type of items in the sequence
    type = None

    def __init__(self, type=None, **k):
        super(Sequence, self).__init__(**k)
        if type is not None:
            self.type = type

    def validate(self, value):
        # Map empty sequence to None
        if not value:
            value = None
        return super(Sequence, self).validate(value)


class File(Type):
    pass


__all__ = [
    'Boolean', 'Date', 'File', 'Float', 'Integer', 'Sequence', 'String', 'Time',
    ]

if haveDecimal:
    __all__.append('Decimal')
