"""
Widgets are small components that render form fields for inputing data in a
certain format.
"""

import itertools
from nevow import inevow, loaders, tags as T, util, url, static, rend
from nevow.i18n import _
from formal import converters, iformal, validation
from formal.util import render_cssid
from formal.form import widgetResourceURL, widgetResourceURLFromContext
from zope.interface import implements
from twisted.internet import defer


# Marker object for args that are not supplied
_UNSET = object()


class TextInput(object):
    """
    A text input field.

    <input type="text" ... />
    """
    implements( iformal.IWidget )

    inputType = 'text'
    showValueOnFailure = True

    def __init__(self, original):
        self.original = original

    def _renderTag(self, ctx, key, value, readonly):
        tag=T.input(type=self.inputType, name=key, id=render_cssid(key), value=value)
        if readonly:
            tag(class_='readonly', readonly='readonly')
        return tag

    def render(self, ctx, key, args, errors):
        if errors:
            value = args.get(key, [''])[0]
        else:
            value = iformal.IStringConvertible(self.original).fromType(args.get(key))
        if not self.showValueOnFailure:
            value = None
        return self._renderTag(ctx, key, value, False)

    def renderImmutable(self, ctx, key, args, errors):
        value = iformal.IStringConvertible(self.original).fromType(args.get(key))
        return self._renderTag(ctx, key, value, True)

    def processInput(self, ctx, key, args):
        value = args.get(key, [''])[0].decode(util.getPOSTCharset(ctx))
        value = iformal.IStringConvertible(self.original).toType(value)
        return self.original.validate(value)


class Checkbox(object):
    """
    A checkbox input field.

    <input type="checkbox" ... />
    """
    implements( iformal.IWidget )

    def __init__(self, original):
        self.original = original

    def _renderTag(self, ctx, key, value, disabled):
        tag = T.input(type='checkbox', name=key, id=render_cssid(key), value='True')
        if value == 'True':
            tag(checked='checked')
        if disabled:
            tag(class_='disabled', disabled='disabled')
        return tag

    def render(self, ctx, key, args, errors):
        if errors:
            value = args.get(key, [''])[0]
        else:
            value = iformal.IBooleanConvertible(self.original).fromType(args.get(key))
        return self._renderTag(ctx, key, value, False)

    def renderImmutable(self, ctx, key, args, errors):
        value = iformal.IBooleanConvertible(self.original).fromType(args.get(key))
        return self._renderTag(ctx, key, value, True)

    def processInput(self, ctx, key, args):
        value = args.get(key, [None])[0]
        if not value:
            value = 'False'
        value = iformal.IBooleanConvertible(self.original).toType(value)
        return self.original.validate(value)


class Password(TextInput):
    """
    A text input field that hides the text.

    <input type="password" ... />
    """
    inputType = 'password'
    showValueOnFailure = False


class TextArea(object):
    """
    A large text entry area that accepts newline characters.

    <textarea>...</textarea>
    """
    implements( iformal.IWidget )

    cols = 48
    rows = 6

    def __init__(self, original, cols=None, rows=None):
        self.original = original
        if cols is not None:
            self.cols = cols
        if rows is not None:
            self.rows = rows

    def _renderTag(self, ctx, key, value, readonly):
        tag=T.textarea(name=key, id=render_cssid(key), cols=self.cols, rows=self.rows)[value or '']
        if readonly:
            tag(class_='readonly', readonly='readonly')
        return tag

    def render(self, ctx, key, args, errors):
        if errors:
            value = args.get(key, [''])[0]
        else:
            value = iformal.IStringConvertible(self.original).fromType(args.get(key))
        return self._renderTag(ctx, key, value, False)

    def renderImmutable(self, ctx, key, args, errors):
        value = iformal.IStringConvertible(self.original).fromType(args.get(key))
        return self._renderTag(ctx, key, value, True)

    def processInput(self, ctx, key, args):
        value = args.get(key, [''])[0].decode(util.getPOSTCharset(ctx))
        value = iformal.IStringConvertible(self.original).fromType(value)
        return self.original.validate(value)


class CheckedPassword(object):
    """
    Two password entry fields that must contain the same value to validate.
    """
    implements( iformal.IWidget )

    def __init__(self, original):
        self.original = original

    def render(self, ctx, key, args, errors):
        if errors and not errors.getFieldError(key):
            values = args.get(key)
        else:
            values = ('', '')
        return [
            T.input(type='password', name=key, id=render_cssid(key), value=values[0]),
            T.br,
            T.label(for_=render_cssid(key, 'confirm'))[' Confirm '],
            T.input(type='password', name=key, id=render_cssid(key, 'confirm'), value=values[1]),
            ]

    def renderImmutable(self, ctx, key, args, errors):
        values = ('', '')
        return [
            T.input(type='password', name=key, id=render_cssid(key), value=values[0], class_='readonly', readonly='readonly'),
            T.br,
            T.label(for_=render_cssid(key, 'confirm'))[' Confirm '],
            T.input(type='password', name=key, id=render_cssid(key, 'confirm'),
                    value=values[1], class_='readonly', readonly='readonly')
        ]

    def processInput(self, ctx, key, args):
        pwds = [pwd for pwd in args.get(key, [])]
        if len(pwds) == 0:
            pwd = ''
        elif len(pwds) == 1:
            raise validation.FieldValidationError('Please enter the password twice for confirmation.')
        else:
            if pwds[0] != pwds[1]:
                raise validation.FieldValidationError('Passwords do not match.')
        return self.original.validate(pwds[0])


class ChoiceBase(object):
    """
    A base class for widgets that provide the UI to select one or more items
    from a list.

    options:
        A sequence of objects adaptable to IKey and ILabel. IKey is used as the
        <option>'s value attribute; ILabel is used as the <option>'s child.
        IKey and ILabel adapters for tuple are provided.
    noneOption:
        An object adaptable to IKey and ILabel that is used to identify when
        nothing has been selected. Defaults to ('', '')
    """

    options = None
    noneOption = None

    def __init__(self, original, options=None, noneOption=_UNSET):
        self.original = original
        if options is not None:
            self.options = options
        if noneOption is not _UNSET:
            self.noneOption = noneOption

    def processInput(self, ctx, key, args):
        value = args.get(key, [''])[0]
        value = iformal.IStringConvertible(self.original).toType(value)
        if self.noneOption is not None and value == self.noneOption[0]:
            value = None
        return self.original.validate(value)


class SelectChoice(ChoiceBase):
    """
    A drop-down list of options.

    <select>
      <option value="...">...</option>
    </select>

    """
    implements( iformal.IWidget )

    noneOption = ('', '')

    def _renderTag(self, ctx, key, value, converter, disabled):

        def renderOptions(ctx, data):
            if self.noneOption is not None:
                yield T.option(value=iformal.IKey(self.noneOption).key())[iformal.ILabel(self.noneOption).label()]
            if data is None:
                return
            for item in data:
                optValue = iformal.IKey(item).key()
                optLabel = iformal.ILabel(item).label()
                optValue = converter.fromType(optValue)
                option = T.option(value=optValue)[optLabel]
                if optValue == value:
                    option = option(selected='selected')
                yield option

        tag=T.select(name=key, id=render_cssid(key), data=self.options)[renderOptions]
        if disabled:
            tag(class_='disabled', disabled='disabled')
        return tag

    def render(self, ctx, key, args, errors):
        converter = iformal.IStringConvertible(self.original)
        if errors:
            value = args.get(key, [''])[0]
        else:
            value = converter.fromType(args.get(key))
        return self._renderTag(ctx, key, value, converter, False)

    def renderImmutable(self, ctx, key, args, errors):
        converter = iformal.IStringConvertible(self.original)
        value = converter.fromType(args.get(key))
        return self._renderTag(ctx, key, value, converter, True)


class SelectOtherChoice(object):
    """
    A <select> widget that includes an "Other ..." option. When the other
    option is selected an <input> field is enabled to allow free text entry.

    Unlike SelectChoice, the options items are not a (value,label) tuple
    because that makes no sense with the free text entry facility.

    TODO:
      * Make the Other option configurable in the JS
      * Refactor, refactor, refactor
    """
    implements(iformal.IWidget)

    options = None
    noneOption = ('', '')
    otherOption = ('...', 'Other ...')

    template = None

    def __init__(self, original, options=None, otherOption=None):
        self.original = original
        if options is not None:
            self.options = options
        if otherOption is not None:
            self.otherOption = otherOption
        if self.template is None:
            self.template = loaders.xmlfile(util.resource_filename('formal',
                'html/SelectOtherChoice.html'))


    def _valueFromRequestArgs(self, key, args):
        value = args.get(key, [''])[0]
        if value == self.otherOption[0]:
            value = args.get(key+'-other', [''])[0]
        return value

    def render(self, ctx, key, args, errors):

        converter = iformal.IStringConvertible(self.original)
        if errors:
            value = self._valueFromRequestArgs(key, args)
        else:
            value = converter.fromType(args.get(key))

        if value is None:
            value = iformal.IKey(self.noneOption).key()

        optionGen = inevow.IQ(self.template).patternGenerator('option')
        selectedOptionGen = inevow.IQ(self.template).patternGenerator('selectedOption')
        optionTags = []
        selectOther = True

        if self.noneOption is not None:
            noneValue = iformal.IKey(self.noneOption).key()
            if value == noneValue:
                tag = selectedOptionGen()
                selectOther = False
            else:
                tag = optionGen()
            tag.fillSlots('value', noneValue)
            tag.fillSlots('label', iformal.ILabel(self.noneOption).label())
            optionTags.append(tag)

        if self.options is not None:
            for item in self.options:
                if value == item:
                    tag = selectedOptionGen()
                    selectOther = False
                else:
                    tag = optionGen()
                tag.fillSlots('value', item)
                tag.fillSlots('label', item)
                optionTags.append(tag)

        if selectOther:
            tag = selectedOptionGen()
            otherValue = value
        else:
            tag = optionGen()
            otherValue = ''
        tag.fillSlots('value', self.otherOption[0])
        tag.fillSlots('label', self.otherOption[1])
        optionTags.append(tag)

        tag = T.invisible[self.template.load(ctx)]
        tag.fillSlots('key', key)
        tag.fillSlots('id', render_cssid(key))
        tag.fillSlots('options', optionTags)
        tag.fillSlots('otherValue', otherValue)
        return tag

    def renderImmutable(self, ctx, key, args, errors):
        raise NotImplemented

    def processInput(self, ctx, key, args):
        value = self._valueFromRequestArgs(key, args)
        value = iformal.IStringConvertible(self.original).toType(value)
        if self.noneOption is not None and value == self.noneOption[0]:
            value = None
        return self.original.validate(value)


class RadioChoice(ChoiceBase):
    """
    A list of options in the form of radio buttons.

    <input type="radio" ... value="..."/><label>...</label><br />
    <input type="radio" ... value="..."/><label>...</label><br />
    """
    implements( iformal.IWidget )

    def _renderTag(self, ctx, key, value, converter, disabled):

        def renderOption(ctx, itemKey, itemLabel, num, selected):
            cssid = render_cssid(key, num)
            tag = T.input(name=key, type='radio', id=cssid, value=itemKey)
            if selected:
                tag = tag(checked='checked')
            if disabled:
                tag = tag(disabled='disabled')
            return tag, ' ', T.label(for_=cssid)[itemLabel], T.br

        def renderOptions(ctx, data):
            # A counter to assign unique ids to each input
            idCounter = itertools.count()
            if self.noneOption is not None:
                itemKey = iformal.IKey(self.noneOption).key()
                itemLabel = iformal.ILabel(self.noneOption).label()
                yield renderOption(ctx, itemKey, itemLabel, idCounter.next(), itemKey==value)
            if not data:
                return
            for item in data:
                itemKey = iformal.IKey(item).key()
                itemLabel = iformal.ILabel(item).label()
                itemKey = converter.fromType(itemKey)
                yield renderOption(ctx, itemKey, itemLabel, idCounter.next(), itemKey==value)

        return T.invisible(data=self.options)[renderOptions]

    def render(self, ctx, key, args, errors):
        converter = iformal.IStringConvertible(self.original)
        if errors:
            value = args.get(key, [''])[0]
        else:
            value = converter.fromType(args.get(key))
        return self._renderTag(ctx, key, value, converter, False)

    def renderImmutable(self, ctx, key, args, errors):
        converter = iformal.IStringConvertible(self.original)
        value = converter.fromType(args.get(key))
        return self._renderTag(ctx, key, value, converter, True)


class DatePartsInput(object):
    """
    A date entry widget that uses three <input> elements for the day, month and
    year parts.

    The default entry format is the US (month, day, year) but can be switched to
    the more common (day, month, year) by setting the dayFirst attribute to
    True.
    
    By default the widget is designed to only accept unambiguous years, i.e.
    the user must enter 4 character dates.
    
    Many people find it convenient or even necessary to allow a 2 character
    year. This can be allowed by setting the twoCharCutoffYear attribute to an
    integer value between 0 and 99. Anything greater than or equal to the cutoff
    year will be considered part of the 20th century (1900 + year); anything
    less the cutoff year is a 21st century (2000 + year) date.
    
    A typical twoCharCutoffYear value is 70 (i.e. 1970). However, that value is
    somewhat arbitrary. It's the year that time began according to the PC, but
    it doesn't mean much to your non-techie user.

    dayFirst:
        Make the day the first input field, i.e. day, month, year
    twoCharCutoffYear:
        Allow 2 char years and set the year where the century flips between
        20th and 21st century.
    """
    implements( iformal.IWidget )

    dayFirst = False
    twoCharCutoffYear = None

    def __init__(self, original, dayFirst=None, twoCharCutoffYear=None):
        self.original = original
        if dayFirst is not None:
            self.dayFirst = dayFirst
        if twoCharCutoffYear is not None:
            self.twoCharCutoffYear = twoCharCutoffYear

    def _namer(self, prefix):
        def _(part):
            return '%s__%s' % (prefix,part)
        return _

    def _renderTag(self, ctx, year, month, day, namer, readonly):
        yearTag = T.input(type="text", name=namer('year'), value=year, size=4)
        monthTag = T.input(type="text", name=namer('month'), value=month, size=2)
        dayTag = T.input(type="text", name=namer('day'), value=day, size=2)
        if readonly:
            tags = (yearTag, monthTag, dayTag)
            for tag in tags:
                tag(class_='readonly', readonly='readonly')

        if self.dayFirst:
            return dayTag, ' / ', monthTag, ' / ', yearTag, ' ', _('(day/month/year)')
        else:
            return monthTag, ' / ', dayTag, ' / ', yearTag, ' ', _('(month/day/year)')

    def render(self, ctx, key, args, errors):
        converter = iformal.IDateTupleConvertible(self.original)
        namer = self._namer(key)
        if errors:
            year = args.get(namer('year'), [''])[0]
            month = args.get(namer('month'), [''])[0]
            day = args.get(namer('day'), [''])[0]
        else:
            year, month, day = converter.fromType(args.get(key))

        return self._renderTag(ctx, year, month, day, namer, False)

    def renderImmutable(self, ctx, key, args, errors):
        converter = iformal.IDateTupleConvertible(self.original)
        namer = self._namer(key)
        year, month, day = converter.fromType(args.get(key))
        return self._renderTag(ctx, year, month, day, namer, True)

    def processInput(self, ctx, key, args):
        namer = self._namer(key)
        # Get the form field values as a (y,m,d) tuple
        ymd = [args.get(namer(part), [''])[0].strip() for part in ('year', 'month', 'day')]
        # Remove parts that were not entered.
        ymd = [p for p in ymd if p]
        # Nothing entered means None otherwise we need all three.
        if not ymd:
            ymd = None
        elif len(ymd) != 3:
            raise validation.FieldValidationError("Invalid date")
        # So, we have what looks like a good attempt to enter a date.
        if ymd is not None:
            # If a 2-char year is allowed then prepend the century.
            if self.twoCharCutoffYear is not None and len(ymd[0]) == 2:
                try:
                    if int(ymd[0]) >= self.twoCharCutoffYear:
                        century = '19'
                    else:
                        century = '20'
                    ymd[0] = century + ymd[0]
                except ValueError:
                    pass
            # By now, we should have a year of at least 4 characters.
            if len(ymd[0]) < 4:
                if self.twoCharCutoffYear is not None:
                    msg = "Please enter a 2 or 4 digit year"
                else:
                    msg = "Please enter a 4 digit year"
                raise validation.FieldValidationError(msg)
            # Map to integers
            try:
                ymd = [int(p) for p in ymd]
            except ValueError, e:
                raise validation.FieldValidationError("Invalid date")
        ymd = iformal.IDateTupleConvertible(self.original).toType(ymd)
        return self.original.validate(ymd)


class MMYYDatePartsInput(object):
    """
    Two input fields for entering the month and year.
    """
    implements( iformal.IWidget )

    cutoffYear = 70

    def __init__(self, original, cutoffYear=None):
        self.original = original
        if cutoffYear is not None:
            self.cutoffYear = cutoffYear

    def _namer(self, prefix):
        def _(part):
            return '%s__%s' % (prefix,part)
        return _

    def _renderTag(self, ctx, year, month, namer, readonly):
        yearTag = T.input(type="text", name=namer('year'), value=year, size=2)
        monthTag = T.input(type="text", name=namer('month'), value=month, size=2)
        if readonly:
            tags=(yearTag, monthTag)
            for tag in tags:
                tag(class_='readonly', readonly='readonly')
        return monthTag, ' / ', yearTag, ' (mm/yy)'

    def render(self, ctx, key, args, errors):
        converter = iformal.IDateTupleConvertible(self.original)
        namer = self._namer(key)
        if errors:
            year = args.get(namer('year'), [''])[0]
            month = args.get(namer('month'), [''])[0]
            # return a blank for the day
            day = ''
        else:
            year, month, day = converter.fromType(args.get(key))
            # if we have a year as default data, stringify it and only use last two digits
            if year is not None:
                year = str(year)[2:]

        return self._renderTag(ctx, year, month, namer, False)

    def renderImmutable(self, ctx, key, args, errors):
        converter = iformal.IDateTupleConvertible(self.original)
        year, month, day = converter.fromType(args.get(key))
        namer = self._namer(key)
        # if we have a year as default data, stringify it and only use last two digits
        if year is not None:
            year = str(year)[2:]
        return self._renderTag(ctx, year, month, namer, True)

    def processInput(self, ctx, key, args):
        namer = self._namer(key)
        value = [args.get(namer(part), [''])[0].strip() for part in ('year', 'month')]
        value = [p for p in value if p]
        if not value:
            value = None
        elif len(value) != 2:
            raise validation.FieldValidationError("Invalid date")
        if value is not None:
            try:
                value = [int(p) for p in value]
            except ValueError, e:
                raise validation.FieldValidationError("Invalid date")
            if value[1] < 0 or value[1] > 99:
                raise validation.FieldValidationError("Invalid year. Please enter a two-digit year.")
            if value[0] > self.cutoffYear:
                value[0] = 1900 + value[0]
            else:
                value[0] = 2000 + value[0]
            value.append(1)
        value = iformal.IDateTupleConvertible(self.original).toType( value )
        return self.original.validate(value)


class CheckboxMultiChoice(object):
    """
    Multiple choice list, rendered as a list of checkbox fields.
    """
    implements( iformal.IWidget )

    options = None

    def __init__(self, original, options=None):
        self.original = original
        if options is not None:
            self.options = options

    def _renderTag(self, ctx, key, values, converter, disabled):
        def renderer(ctx, options):
            # loops through checkbox options and renders
            for n,item in enumerate(options):
                optValue = iformal.IKey(item).key()
                optLabel = iformal.ILabel(item).label()
                optValue = converter.fromType(optValue)
                optid = render_cssid(key, n)
                checkbox = T.input(type='checkbox', name=key, value=optValue,
                        id=optid)
                if optValue in values:
                    checkbox = checkbox(checked='checked')
                if disabled:
                    checkbox = checkbox(class_='disabled', disabled='disabled')
                yield checkbox, T.label(for_=optid)[optLabel], T.br()
        # Let Nevow worry if self.options is not already a list.
        return T.invisible(data=self.options)[renderer]

    def render(self, ctx, key, args, errors):

        converter = iformal.IStringConvertible(self.original.type)

        if errors:
            values = args.get(key, [])
        else:
            values = args.get(key)
            if values is not None:
                values = [converter.fromType(v) for v in values]
            else:
                values = []

        return self._renderTag(ctx, key, values, converter, False)

    def renderImmutable(self, ctx, key, args, errors):

        converter = iformal.IStringConvertible(self.original.type)

        values = args.get(key)
        if values is not None:
            values = [converter.fromType(v) for v in values]
        else:
            values = []

        return self._renderTag(ctx, key, values, converter, True)

    def processInput(self, ctx, key, args):
        values = args.get(key, [])
        converter = iformal.IStringConvertible(self.original.type)
        values = [converter.toType(v) for v in values]
        return self.original.validate(values)


class FileUploadRaw(object):
    implements( iformal.IWidget )

    def __init__(self, original):
        self.original = original

    def _renderTag(self, ctx, key, disabled):
        tag=T.input(name=key, id=render_cssid(key),type='file')
        if disabled:
            tag(class_='disabled', disabled='disabled')
        return tag

    def render(self, ctx, key, args, errors):
        if errors:
            value = args.get(key, [''])[0]
        else:
            value = iformal.IFileConvertible(self.original).fromType(args.get(key))
        return self._renderTag(ctx, key, False)

    def renderImmutable(self, ctx, key, args, errors):
        value = iformal.IFileConvertible(self.original).fromType(args.get(key))
        return self._renderTag(ctx, key, True)

    def processInput(self, ctx, key, args):
        fileitem = inevow.IRequest(ctx).fields[key]
        name = fileitem.filename.decode(util.getPOSTCharset(ctx))
        value = (name, fileitem.file)

        value = iformal.IFileConvertible(self.original).fromType(value)
        return self.original.validate(value)


class FileUpload(object):
    implements( iformal.IWidget )

    def __init__(self, original, fileHandler, preview=None):
        self.original = original
        self.fileHandler = fileHandler
        self.preview = preview

    def _namer(self, prefix):
        def _(part):
            return '%s__%s' % (prefix,part)
        return _

    def _renderTag(self, ctx, key, value, namer, disabled):

        name = self.fileHandler.getUrlForFile(value)
        if name:
            if self.preview == 'image':
                yield T.p[value,T.img(src=self.fileHandler.getUrlForFile(value))]
            else:
                yield T.p[value]
        else:
            yield T.p[T.strong['nothing uploaded']]

        yield T.input(name=namer('value'),value=value,type='hidden')
        tag=T.input(name=key, id=render_cssid(key),type='file')
        if disabled:
            tag(class_='disabled', disabled='disabled')
        yield tag

    def render(self, ctx, key, args, errors):
        namer = self._namer(key)
        if errors:
            fileitem = inevow.IRequest(ctx).fields[key]
            name = fileitem.filename.decode(util.getPOSTCharset(ctx))
            if name:
                value = name
            else:
               namer = self._namer(key)
               value = args.get(namer('value'))[0]
        else:
            value = iformal.IStringConvertible(self.original).fromType(args.get(key))

        return self._renderTag(ctx, key, value, namer, False)

    def renderImmutable(self, ctx, key, args, errors):
        namer = self._namer(key)
        value = iformal.IStringConvertible(self.original).fromType(args.get(key))
        return self._renderTag(ctx, key, value, namer, True)

    def processInput(self, ctx, key, args):
        fileitem = inevow.IRequest(ctx).fields[key]
        name = fileitem.filename.decode(util.getPOSTCharset(ctx))

        if name:
            value = self.fileHandler.storeFile( fileitem.file, name )
        else:
           namer = self._namer(key)
           value = args.get(namer('value'))[0]

        value = iformal.IStringConvertible(self.original).fromType(value)
        return self.original.validate(value)


class FileUploadWidget(object):
    """
    File upload widget that carries the uploaded file around until the form
    validates.

    The widget uses the resource manager to save the file to temporary storage
    until the form validates. This makes file uploads behave like most of the
    other widgets, i.e. the value is kept when a form is redisplayed due to
    validation errors.
    """
    implements( iformal.IWidget )

    FROM_RESOURCE_MANAGER = 'rm'
    FROM_CONVERTIBLE = 'cf'

    convertibleFactory = converters.NullConverter

    def _namer(self, prefix):
        def _(part):
            return '%s__%s' % (prefix,part)
        return _

    def __init__( self, original, convertibleFactory=None, originalKeyIsURL=False ):
        self.original = original
        if convertibleFactory is not None:
            self.convertibleFactory = convertibleFactory
        self.originalKeyIsURL = originalKeyIsURL

    def _blankField( self, field ):
        """
            Convert empty strings into None.
        """
        if field and field == '':
            return None
        return field

    def _getFromArgs( self, args, name ):
        """
            Get the first value of 'name' from 'args', or None.
        """
        rv = args.get( name )
        if rv:
            rv = rv[0]
        return rv

    def render(self, ctx, key, args, errors):
        """
            Render the data.

            This either renders a link to the original file, if specified, and
            no new file has been uploaded. Or a link to the uploaded file.

            The request to get the data should be routed to the getResouce
            method.
        """
        form = iformal.IForm( ctx )

        namer = self._namer( key )
        resourceIdName = namer( 'resource_id' )
        originalIdName = namer( 'original_id' )

        # get the resource id first from the resource manager
        # then try the request
        resourceId = form.resourceManager.getResourceId( key )
        if resourceId is None:
            resourceId = self._getFromArgs( args, resourceIdName )
        resourceId = self._blankField( resourceId )

        # Get the original key from a hidden field in the request,
        # then try the request file.data initial data.
        originalKey = self._getFromArgs( args, originalIdName )
        if not errors and not originalKey:
            originalKey = args.get( key )
        originalKey = self._blankField( originalKey )

        if resourceId:
            # Have an uploaded file, so render a URL to the uploaded file
            tmpURL = widgetResourceURL(form.name).child(key).child( self.FROM_RESOURCE_MANAGER ).child(resourceId)
            yield T.p[T.img(src=tmpURL)]
        elif originalKey:
            # The is no uploaded file, but there is an original, so render a
            # URL to it
            if self.originalKeyIsURL:
                tmpURL = originalKey
            else:
                tmpURL = widgetResourceURL(form.name).child(key).child( self.FROM_CONVERTIBLE ).child( originalKey )
            yield T.p[T.img(src=tmpURL)]
        else:
            # No uploaded file, no original
            yield T.p[T.strong['Nothing uploaded']]

        yield T.input(name=key, id=render_cssid(key),type='file')

        # Id of uploaded file in the resource manager
        yield T.input(name=resourceIdName,value=resourceId,type='hidden')
        if originalKey:
            # key of the original that can be used to get a file later
            yield T.input(name=originalIdName,value=originalKey,type='hidden')

    def renderImmutable(self, ctx, key, args, errors):
        form = iformal.IForm(ctx)

        namer = self._namer(key)
        originalIdName = namer('original_id')

        # Get the original key from a hidden field in the request,
        # then try the request form.data initial data.
        originalKey = self._getFromArgs( args, originalIdName )
        if not errors and not originalKey:
            originalKey = args.get( key )
        originalKey = self._blankField( originalKey )

        if originalKey:
            # The is no uploaded file, but there is an original, so render a
            # URL to it
            if self.originalKeyIsURL:
                tmpURL = originalKey
            else:
                tmpURL = widgetResourceURL(form.name).child(key).child(self.FROM_CONVERTIBLE).child(originalKey)
            yield T.p[T.img(src=tmpURL)]
        else:
            # No uploaded file, no original
            yield T.p[T.strong['Nothing uploaded']]

        if originalKey:
            # key of the original that can be used to get a file later
            yield T.input(name=originalIdName,value=originalKey,type='hidden')

    def processInput(self, ctx, key, args):
        """
            Process the request, storing any uploaded file in the
            resource manager.
        """

        resourceManager = iformal.IForm( ctx ).resourceManager

        # Ping the resource manager with any resource ids that I know
        self._registerWithResourceManager( key, args, resourceManager )

        fileitem = inevow.IRequest(ctx).fields[key]
        name = fileitem.filename.decode(util.getPOSTCharset(ctx))
        if name:
            # Store the uploaded file in the resource manager
            resourceManager.setResource( key, fileitem.file, name )

        # Validating against an uploaded file. Should the fact that there is
        # original file meet a required field validation?
        value = resourceManager.getResourceForWidget( key )
        value = self.convertibleFactory(self.original).toType( value )
        return self.original.validate( value )

    def _registerWithResourceManager( self, key, args, resourceManager ):
        """
            If there is a resource id in the request, then let the
            resource manager know about it.
        """
        namer = self._namer( key )
        resourceIdName = namer( 'resource_id' )

        resourceId = self._getFromArgs( args, resourceIdName )
        resourceId = self._blankField( resourceId )
        if resourceId:
            resourceManager.register( key, resourceId )

    def getResource( self, ctx, key, segments ):
        """
            Return an Resource that contains the image, either a file
            from the resource manager, or a data object from the convertible.
        """

        if segments[0] == self.FROM_RESOURCE_MANAGER:
            # Resource manager can provide a path so return a static.File
            # instance that points to the file
            rm = iformal.IForm( ctx ).resourceManager
            (mimetype, path, fileName) = rm.getResourcePath( segments[1] )
            return static.File( path, mimetype ), []
        elif segments[0] == self.FROM_CONVERTIBLE:
            # The convertible can provide a file like object so create a
            # static.Data instance with the data from the convertible.

            def _( result ):

                mimetype, filelike, fileName = result
                data = filelike.read()
                filelike.close()
                return static.Data( data, mimetype ), []

            d = defer.maybeDeferred( self.convertibleFactory(self.original).fromType, segments[1], context=ctx )
            d.addCallback( _ )
            return d
        else:
            return None

class Hidden(object):
    """
    A hidden form field.
    """
    __implements__ = iformal.IWidget,

    inputType = 'hidden'

    def __init__(self, original):
        self.original = original

    def render(self, ctx, key, args, errors):
        if errors:
            value = args.get(key, [''])
            if isinstance(value, list):
                value = value[0]
        else:
            value = iformal.IStringConvertible(self.original).fromType(args.get(key))
        return T.input(type=self.inputType, name=key, id=render_cssid(key), value=value)

    def renderImmutable(self, ctx, key, args, errors):
        return self.render(ctx, key, args, errors)

    def processInput(self, ctx, key, args):
        value = args.get(key, [''])[0].decode(util.getPOSTCharset(ctx))
        value = iformal.IStringConvertible(self.original).toType(value)
        return self.original.validate(value)


__all__ = [
    'Checkbox', 'CheckboxMultiChoice', 'CheckedPassword', 'FileUploadRaw',
    'Password', 'SelectChoice', 'TextArea', 'TextInput', 'DatePartsInput',
    'MMYYDatePartsInput', 'Hidden', 'RadioChoice', 'SelectOtherChoice',
    'FileUpload', 'FileUploadWidget',
    ]

