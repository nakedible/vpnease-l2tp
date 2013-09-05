from twisted.trial import unittest
import formal


class TestForm(unittest.TestCase):

    def test_fieldName(self):
        form = formal.Form()
        form.addField('foo', formal.String())
        self.assertRaises(ValueError, form.addField, 'spaceAtTheEnd ', formal.String())
        self.assertRaises(ValueError, form.addField, 'got a space in it', formal.String())
