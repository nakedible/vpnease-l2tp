from datetime import date, time
try:
    import decimal
    haveDecimal = True
except ImportError:
    haveDecimal = False
from twisted.trial import unittest
import formal
from formal import validation


class TestValidators(unittest.TestCase):

    def testHasValidator(self):
        t = formal.String(validators=[validation.LengthValidator(max=10)])
        self.assertEquals(t.hasValidator(validation.LengthValidator), True)

    def testRequired(self):
        t = formal.String(required=True)
        self.assertEquals(t.hasValidator(validation.RequiredValidator), True)
        self.assertEquals(t.required, True)


class TestCreation(unittest.TestCase):

    def test_immutablility(self):
        self.assertEquals(formal.String().immutable, False)
        self.assertEquals(formal.String(immutable=False).immutable, False)
        self.assertEquals(formal.String(immutable=True).immutable, True)

    def test_immutablilityOverride(self):
        class String(formal.String):
            immutable = True
        self.assertEquals(String().immutable, True)
        self.assertEquals(String(immutable=False).immutable, False)
        self.assertEquals(String(immutable=True).immutable, True)


class TestValidate(unittest.TestCase):

    def testString(self):
        self.assertEquals(formal.String().validate(None), None)
        self.assertEquals(formal.String().validate(''), None)
        self.assertEquals(formal.String().validate(' '), ' ')
        self.assertEquals(formal.String().validate('foo'), 'foo')
        self.assertEquals(formal.String().validate(u'foo'), u'foo')
        self.assertEquals(formal.String(strip=True).validate(' '), None)
        self.assertEquals(formal.String(strip=True).validate(' foo '), 'foo')
        self.assertEquals(formal.String(missing='bar').validate('foo'), 'foo')
        self.assertEquals(formal.String(missing='bar').validate(''), 'bar')
        self.assertEquals(formal.String(strip=True, missing='').validate(' '), '')
        self.assertEquals(formal.String(missing='foo').validate('bar'), 'bar')
        self.assertRaises(formal.FieldValidationError, formal.String(required=True).validate, '')
        self.assertRaises(formal.FieldValidationError, formal.String(required=True).validate, None)

    def testInteger(self):
        self.assertEquals(formal.Integer().validate(None), None)
        self.assertEquals(formal.Integer().validate(0), 0)
        self.assertEquals(formal.Integer().validate(1), 1)
        self.assertEquals(formal.Integer().validate(-1), -1)
        self.assertEquals(formal.Integer(missing=1).validate(None), 1)
        self.assertEquals(formal.Integer(missing=1).validate(2), 2)
        self.assertRaises(formal.FieldValidationError, formal.Integer(required=True).validate, None)

    def testFloat(self):
        self.assertEquals(formal.Float().validate(None), None)
        self.assertEquals(formal.Float().validate(0), 0.0)
        self.assertEquals(formal.Float().validate(0.0), 0.0)
        self.assertEquals(formal.Float().validate(.1), 0.1)
        self.assertEquals(formal.Float().validate(1), 1.0)
        self.assertEquals(formal.Float().validate(-1), -1.0)
        self.assertEquals(formal.Float().validate(-1.86), -1.86)
        self.assertEquals(formal.Float(missing=1.0).validate(None), 1.0)
        self.assertEquals(formal.Float(missing=1.0).validate(2.0), 2.0)
        self.assertRaises(formal.FieldValidationError, formal.Float(required=True).validate, None)

    if haveDecimal:
        def testDecimal(self):
            from decimal import Decimal
            self.assertEquals(formal.Decimal().validate(None), None)
            self.assertEquals(formal.Decimal().validate(Decimal('0')), Decimal('0'))
            self.assertEquals(formal.Decimal().validate(Decimal('0.0')), Decimal('0.0'))
            self.assertEquals(formal.Decimal().validate(Decimal('.1')), Decimal('0.1'))
            self.assertEquals(formal.Decimal().validate(Decimal('1')), Decimal('1'))
            self.assertEquals(formal.Decimal().validate(Decimal('-1')), Decimal('-1'))
            self.assertEquals(formal.Decimal().validate(Decimal('-1.86')),
                    Decimal('-1.86'))
            self.assertEquals(formal.Decimal(missing=Decimal("1.0")).validate(None),
                    Decimal("1.0"))
            self.assertEquals(formal.Decimal(missing=Decimal("1.0")).validate(Decimal("2.0")),
                    Decimal("2.0"))
            self.assertRaises(formal.FieldValidationError, formal.Decimal(required=True).validate, None)

    def testBoolean(self):
        self.assertEquals(formal.Boolean().validate(None), None)
        self.assertEquals(formal.Boolean().validate(True), True)
        self.assertEquals(formal.Boolean().validate(False), False)
        self.assertEquals(formal.Boolean(missing=True).validate(None), True)
        self.assertEquals(formal.Boolean(missing=True).validate(False), False)

    def testDate(self):
        self.assertEquals(formal.Date().validate(None), None)
        self.assertEquals(formal.Date().validate(date(2005,1,1)), date(2005,1,1))
        self.assertEquals(formal.Date(missing=date(2005,1,2)).validate(None), date(2005,1,2))
        self.assertEquals(formal.Date(missing=date(2005,1,2)).validate(date(2005,1,1)), date(2005,1,1))
        self.assertRaises(formal.FieldValidationError, formal.Date(required=True).validate, None)

    def testTime(self):
        self.assertEquals(formal.Time().validate(None), None)
        self.assertEquals(formal.Time().validate(time(12,30,30)), time(12,30,30))
        self.assertEquals(formal.Time(missing=time(12,30,30)).validate(None), time(12,30,30))
        self.assertEquals(formal.Time(missing=time(12,30,30)).validate(time(12,30,31)), time(12,30,31))
        self.assertRaises(formal.FieldValidationError, formal.Time(required=True).validate, None)

    def test_sequence(self):
        self.assertEquals(formal.Sequence(formal.String()).validate(None), None)
        self.assertEquals(formal.Sequence(formal.String()).validate(['foo']), ['foo'])
        self.assertEquals(formal.Sequence(formal.String(), missing=['foo']).validate(None), ['foo'])
        self.assertEquals(formal.Sequence(formal.String(), missing=['foo']).validate(['bar']), ['bar'])
        self.assertRaises(formal.FieldValidationError, formal.Sequence(formal.String(), required=True).validate, None)
        self.assertRaises(formal.FieldValidationError, formal.Sequence(formal.String(), required=True).validate, [])

    def test_file(self):
        pass
    test_file.skip = "write tests"

