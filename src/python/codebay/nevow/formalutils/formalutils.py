"""Formal helpers."""
__docformat__ = 'epytext en'

#
#  XXX: document clearly when:
#    a) a dictionary key does not exit
#    b) a dictionary key exists but value is None
#
#  It seems that erroneus values (whose local validation fails) do not currently
#  exist as keys in form.data.
#

from UserDict import UserDict, DictMixin
from nevow import appserver, context, loaders, inevow, rend, tags as T, url, stan
from twisted.internet import defer
from twisted.python.components import registerAdapter
from formal import form, validation, iformal, util, widget
import formal

# XXX: this is VPNease specific now.
_default_summary_clicktoexpand = T.span['Click ', T.img(src='/static/arrow.gif', alt='>', width='8', height='10'), ' to expand.']

class GlobalError(validation.FormsError):
    """Global, non-field specific error."""
    pass

class FormsWarning(validation.FormsError):
    """Root class of all warning messages."""
    pass

class GlobalWarning(FormsWarning):
    """Global, non-field specific warning."""
    pass

class FieldWarning(FormsWarning):
    """Field warnings.

    FieldWarning is a 'sibling' of validation.FieldError,
    and is essentially only relevant to our own code.
    """
    def __init__(self, message, fieldName=None):
        FormsWarning.__init__(self, message)
        self.fieldName = fieldName

class FieldGlobalError(validation.FieldError):
    pass
    
# --------------------------------------------------------------------------

def clear_errors_and_warnings(ctx, key):    
    """Clears field errors and warnings for a given key."""
    errorlist = iformal.IFormErrors(ctx, None).getFormErrors()
    for e in errorlist:
        if (isinstance(e, validation.FieldError)) or (isinstance(e, FieldWarning)):
            if e.fieldName == key:
                errorlist.remove(e)    

class FormDataAccessor(DictMixin):
    """Dictionary-like object for accessing the data of a Formal form.

    Supports normal dictionary operations.  All operations are simply
    wrappers and actual data always resides in form.data of the Form.

    The accessor maintains a known list of prefixes which are
    concatenated with dots to form a 'Formal path'.  The descend()
    operation allows one to enter a group and access group elements
    without repeating the prefix on every access.
    """
    def __init__(self, form, prefixlist, ctx):
        self.form = form
        self.prefixlist = prefixlist
        self.ctx = ctx
        
    def _combine(self, key):
        return '.'.join(self.prefixlist + [key])
    
    def _filter_errors(self, filterlist, errorlist=None):
        def _check_filters(e):
            for f in filterlist:
                if not f(e):
                    return False
            return True
        if errorlist is None:
            errorlist = iformal.IFormErrors(self.ctx, None).getFormErrors()
        res = [e for e in errorlist if _check_filters(e)]
        return res
    
    # public functions
    def combine(self, key):
        return '.'.join(self.prefixlist + [key])

    def descend(self, key):
        return FormDataAccessor(self.form, self.prefixlist + [key], self.ctx)

    def add_global_error(self, msg):
        errors = iformal.IFormErrors(self.ctx, None)
        errors.add(GlobalError(msg))
        
    def add_error(self, key, msg):
        errors = iformal.IFormErrors(self.ctx, None)
        errors.add(FieldGlobalError(msg, self._combine(key)))

    def has_error(self, key):
        """Check whether a specific field has a field error of any type.

        Note: this check will not consider FieldWarnings as errors, so
        this works as expected.
        """
        ourname = self._combine(key)
        errs = self._filter_errors([lambda e: isinstance(e, validation.FieldError),
                                    lambda e: not isinstance(e, FormsWarning),
                                    lambda e: e.fieldName == ourname])
        return len(errs) > 0
    
    def add_warning(self, key, msg):
        errors = iformal.IFormErrors(self.ctx, None)
        errors.add(FieldWarning(msg, self._combine(key)))

    def has_warning(self, key):
        ourname = self._combine(key)
        errs = self._filter_errors([lambda e: isinstance(e, FieldWarning),
                                    lambda e: e.fieldName == ourname])
        return len(errs) > 0

    def clear_local_errors_and_warnings(self, key):
        ourname = self._combine(key)
        clear_errors_and_warnings(self.ctx, ourname)
        
    def clear_key_value(self, key):
        self[key] = None
    
    def finalize_validation(self):
        """Finalize validation.

        Check whether form has errors, and if so, raise a validation.FormError
        to make Formal take notice.  The text for this FormError is unfortunately
        fixed.

        May be called multiple times to "bail out early".
        """

        # If the form has errors, errordata is remembered as form data in 
        # renderForm (form.py). 
        # Errordata is created in form process function (form.py) and is an 
        # independent dictionary containing errors and current data. 
        # Errordata is always created even though there are no errors. Thus 
        # there is no need to check whether the errordata is available or not.
        
        errors = iformal.IFormErrors(self.ctx, None)
        errorData = errors.data
        formData = self.form.data
        
        # XXX: TBD - form data does not contain erranuous keys and data.
        # Canonicalization inserts the keys and therefore they exists in form data.
        # This, however is similar to formal "common" behaviour.
        
        #for key in errorData.keys():
        #    errorData[key] = [formData.get(key)]
        
        # Check if there are any errors in the form. Raise exception if an error is found.
        if errors is not None:
            errwarnlist = errors.getFormErrors()

            realerrs = self._filter_errors([lambda e: isinstance(e, validation.FormsError),
                                            lambda e: not isinstance(e, FormsWarning)],
                                           errorlist=errwarnlist)
            
            if len(realerrs) > 0:
                # Remove duplicate errors for the same fields to avoid issue #842
                self._filter_dups(errwarnlist)
                raise validation.FormError('Validation of entered data failed')
        else:
            pass
        
    def _filter_dups(self, errwarnlist):
        visited = {}
        to_delete = []
        for i in errwarnlist:
            if isinstance(i, validation.FieldError):
                fld = i.fieldName
                if visited.has_key(fld):
                    print 'suppressing duplicate error for field %s: %s' % (fld, i.message)
                    to_delete.append(i)
                else:
                    visited[fld] = 1

        print 'deleting duplicate errors: %s' % to_delete

        for i in to_delete:
            errwarnlist.remove(i)

    # dict operations

    def __getitem__(self, key):
        return self.form.data[self._combine(key)]

    def __setitem__(self, key, item):
        self.form.data[self._combine(key)] = item

    def __delitem__(self, key):
        del self.form.data[self._combine(key)]

    def keys(self):
        prefix = self._combine('')   # ['foo', 'bar'] => 'foo.bar.'
        prefix_len = len(prefix)

        def _filter_prefix(p):
            return (len(p) > prefix_len) and (p[:prefix_len] == prefix)

        def _strip_prefix(p):
            return p[prefix_len:]
        
        return map(_strip_prefix, filter(_filter_prefix, self.form.data.keys()))

# --------------------------------------------------------------------------

# XXX: This is an exceptionally ugly attempt of adding tabindexes to
# stan markup returned by Formal renderers.  The ugliness comes from
# two separate issues: (1) the stan tree is 'half cooked', e.g. slots
# are explicitly slots and are not yet filled; (2) some rendering is
# delayed and are inside stan in the form of functions; this is the
# case in particular with radiobuttons.
#
# We really need to solve this better in the future -- probably by
# writing our own widgets, as we want to control layout better
# anyhow.

def _add_stan_tabindexes(x):
    from types import FunctionType, GeneratorType

    # This is used to handle radio buttons returned by Formal, and is executed
    # when the Stan is eventually flattened
    def _handle_function_type(f):
        def _g(ctx, data):
            res = f(ctx, data)

            # XXX: formal code returns a generator, so we only handle that here
            if isinstance(res, GeneratorType):
                tmp = []
                for x in res:
                    # individual elements may be tuples
                    if isinstance(x, stan.Tag):
                        _add_stan_tabindexes(x)          # recursion, ouch
                        tmp.append(x)
                    elif isinstance(x, tuple):
                        for elem in x:
                            _add_stan_tabindexes(elem)   # recursion, ouch
                            tmp.append(elem)
                return tmp
            else:
                return res
        return _g
            
    # Sanity
    if not isinstance(x, stan.Tag):
        return
        
    # Handling for this tag
    if hasattr(x, 'tagName') and x.tagName in ['input', 'select']:
        x(tabindex='1')

    # Iterate children
    if hasattr(x, 'children'):
        for i, c in enumerate(x.children):
            if isinstance(c, stan.Tag):
                _add_stan_tabindexes(c)
            elif isinstance(c, FunctionType):
                x.children[i] = _handle_function_type(c)

    # Iterate slot data (e.g. radiobuttons)
    if hasattr(x, 'slotData'):
        if isinstance(x.slotData, dict):
            for s in x.slotData.keys():
                t = x.slotData[s]
                if isinstance(t, stan.Tag):
                    _add_stan_tabindexes(x.slotData[s])
                elif isinstance(t, FunctionType):
                    x.slotData[s] = _handle_function_type(t)


# NB: has same (local) name as Formal's equivalent

class Field(form.Field):
    """Small Field wrapper which adds tabindexes."""

class FieldFragment(form.FieldFragment):
    """Rendered for Field."""

    def render_field(self, ctx, data):
        res = super(FieldFragment, self).render_field(ctx, data)
        _add_stan_tabindexes(res)
        return res

registerAdapter(FieldFragment, Field, inevow.IRenderer)

# --------------------------------------------------------------------------

class DynamicList(object):
    itemParent = None

    def __init__(self, name, label=None, description=None, cssClass=None, childCreationCallback=None):
        if label is None:
            label = util.titleFromName(name)
        self.name = name
        self.label = label
        self.description = description
        self.cssClass = cssClass
        if childCreationCallback is None:
            raise Exception('must give childCreationCallback')
        self.childCreationCallback = childCreationCallback
        self.items = form.FormItems(self)
        self.add = self.items.add
        self.getItemByName = self.items.getItemByName
        self.collapsible = False
        self.collapsed = False
        self.summary = None
        
    key = property(lambda self: form.itemKey(self))

    def setItemParent(self, itemParent):
        self.itemParent = itemParent

    def setCollapsible(self, collapsible=True):
        self.collapsible = collapsible

    def setCollapsed(self, collapsed=True):
        self.collapsed = collapsed

    def setSummary(self, summary):
        self.summary = summary

    def getCollapsedKey(self):
        return form.itemKey(self) + '._collapsedstate_'

    def process(self, ctx, the_form, args, errors):
        # nuke old children
        self.items = form.FormItems(self)        
        self.add = self.items.add
        self.getItemByName = self.items.getItemByName

        # filter away other arguments based on prefix
        ourpath = form.itemKey(self)
        ourpathlen = len(ourpath)
        ourargs = {}
        for k in args.keys():
            if k[:ourpathlen] == ourpath:
                ourargs[k[ourpathlen:]] = args[k]  # foo.bar.list.0.foo -> .0.foo
                                                   # foo.bar.list._collapsedstate_ -> ._collapsedstate_
                                                   
        # Delete existing keys from the form data. Otherwise data from objects deleted by javascripts
        # still exists in form data.
        for k in the_form.data.keys():
            if k[:ourpathlen] == ourpath:
                del(the_form.data[k])

        # Get collapsed state
        collapsed_key = '%s._collapsedstate_' % ourpath
        if args.has_key(collapsed_key):
            val = args[collapsed_key][0]
            if val == '1':
                self.collapsed = True
            else:
                self.collapsed = False
            the_form.data[collapsed_key] = val

        # catch all numbers
        nums = {}
        for k in ourargs.keys():
            t = k.split('.')   # .0.foo -> ['', '0', 'foo']; or ._collapsedstate_ -> ['', '_collapsedstate_']
            try:
                index = int(t[1])
                nums[str(index)] = ourargs[k]
            except ValueError:
                if t[1] == '_collapsedstate_':
                    pass
                else:
                    raise

        # XXX: if there are dups in the entry, we get a list of >1 values here; what to do?

        # iterate over numbers, creating groups
        for i in xrange(1024):  # max elements
            childpath = form.itemKey(self) + '.' + str(i)

            if nums.has_key(str(i)):
                self.add(self.childCreationCallback(i))
            else:
                break

        # process children
        for item in self.items:
            item.process(ctx, the_form, args, errors)

class DynamicListFragment(rend.Fragment):
    docFactory = loaders.stan(
        T.fieldset(id=T.slot('id'), _class=T.slot('cssClass'), render=T.directive('dynamiclist'))[
            T.input(_class='collapsible-group-hidden-state', type='hidden', render=T.directive('collapsedstate')),
            T.legend[T.span(_class='collapse-controls'), T.slot('label')],
            T.div(_class='description')[T.slot('description')],
            T.div(_class='collapsible-group-summary')[T.div(render=T.directive('display_summary'))[T.slot('summary')]],
            T.div(_class='collapsible-group-contents')[T.div(render=T.directive('display_contents'))[T.div(_class='dynamic-list-header'),
                                                                                                     T.div(_class='dynamic-list-contents')[T.slot('items')],
                                                                                                     T.div(_class='dynamic-list-footer')]]
        ])


    def __init__(self, dynamiclist):
        super(DynamicListFragment, self).__init__()
        self.dynamiclist = dynamiclist

    def render_collapsedstate(self, ctx, data):
        ctx.tag(name=self.dynamiclist.getCollapsedKey())
        if self.dynamiclist.collapsible and self.dynamiclist.collapsed:
            value = '1'
        else:
            value = '0'
        ctx.tag(value=value)
        return ctx.tag

    def render_display_summary(self, ctx, data):
        if self.dynamiclist.collapsible and self.dynamiclist.collapsed:
            return ctx.tag(_class='collapsible-show')
        else:
            return ctx.tag(_class='collapsible-hide')

    def render_display_contents(self, ctx, data):
        if self.dynamiclist.collapsible and self.dynamiclist.collapsed:
            return ctx.tag(_class='collapsible-hide')
        else:
            return ctx.tag(_class='collapsible-show')

    def render_dynamiclist(self, ctx, data):
        dynamiclist = self.dynamiclist

        # Build the CSS class string
        cssClass = ['group']
        if self.dynamiclist.collapsible:
            cssClass.append('collapsible-group')
        if dynamiclist.cssClass is not None:
            cssClass.append(dynamiclist.cssClass)
        cssClass = ' '.join(cssClass)

        # Fill the slots
        ctx.tag.fillSlots('id', util.render_cssid(dynamiclist.key))
        ctx.tag.fillSlots('cssClass', cssClass)
        ctx.tag.fillSlots('label', dynamiclist.label)
        ctx.tag.fillSlots('description', dynamiclist.description or '')
        if self.dynamiclist.summary is not None:
            ctx.tag.fillSlots('summary', self.dynamiclist.summary)
        else:
            ctx.tag.fillSlots('summary', _default_summary_clicktoexpand)
        ctx.tag.fillSlots('items', [inevow.IRenderer(item) for item in
                dynamiclist.items])
        
        return ctx.tag

registerAdapter(DynamicListFragment, DynamicList, inevow.IRenderer)

#registerAdapter(form.GroupFragment, DynamicList, inevow.IRenderer)

# --------------------------------------------------------------------------

class CollapsibleGroup(form.Group):
    """Collapsible group.

    Has client Javascript support for collapsing and expanding group.
    Relies on client-side Javascript to add collapse controls, etc.
    """

    def __init__(self, *a, **kw):
        super(CollapsibleGroup, self).__init__(*a, **kw)
        self.collapsible = True
        self.collapsed = False
        self.summary = None
        
    def setCollapsible(self, collapsible=True):
        self.collapsible = collapsible

    def setCollapsed(self, collapsed=True):
        self.collapsed = collapsed

    def setSummary(self, summary):
        self.summary = summary

    def getCollapsedKey(self):
        return form.itemKey(self) + '._collapsedstate_'

    def process(self, ctx, the_form, args, errors):
        # Get collapsed state
        collapsed_key = '%s._collapsedstate_' % form.itemKey(self)
        if args.has_key(collapsed_key):
            val = args[collapsed_key][0]
            if val == '1':
                self.collapsed = True
            else:
                self.collapsed = False
            the_form.data[collapsed_key] = val

        return super(CollapsibleGroup, self).process(ctx, the_form, args, errors)

class CollapsibleGroupFragment(rend.Fragment):
    docFactory = loaders.stan(
        T.fieldset(id=T.slot('id'), _class=T.slot('cssClass'), render=T.directive('group'))[
            T.input(_class='collapsible-group-hidden-state', type='hidden', render=T.directive('collapsedstate')),
            T.legend[T.span(_class='collapse-controls'), T.slot('label')],
            T.div(_class='description')[T.slot('description')],
            T.div(_class='collapsible-group-summary')[T.div(render=T.directive('display_summary'))[T.slot('summary')]],
            T.div(_class='collapsible-group-contents')[T.div(render=T.directive('display_contents'))[T.slot('items')]],
        ])

    def __init__(self, group):
        super(CollapsibleGroupFragment, self).__init__()
        self.group = group

    def render_collapsedstate(self, ctx, data):
        ctx.tag(name=self.group.getCollapsedKey())
        if self.group.collapsible and self.group.collapsed:
            value = '1'
        else:
            value = '0'
        ctx.tag(value=value)
        return ctx.tag
    
    def render_display_summary(self, ctx, data):
        if self.group.collapsible and self.group.collapsed:
            return ctx.tag(_class='collapsible-show')
        else:
            return ctx.tag(_class='collapsible-hide')

    def render_display_contents(self, ctx, data):
        if self.group.collapsible and self.group.collapsed:
            return ctx.tag(_class='collapsible-hide')
        else:
            return ctx.tag(_class='collapsible-show')

    def render_group(self, ctx, data):
        group = self.group

        # Build the CSS class string
        cssClass = ['group']
        if self.group.collapsible:
            cssClass.append('collapsible-group')
        if group.cssClass is not None:
            cssClass.append(group.cssClass)
        cssClass = ' '.join(cssClass)

        # Fill the slots
        ctx.tag.fillSlots('id', util.render_cssid(group.key))
        ctx.tag.fillSlots('cssClass', cssClass)
        ctx.tag.fillSlots('label', group.label)
        ctx.tag.fillSlots('description', group.description or '')
        if self.group.summary is not None:
            ctx.tag.fillSlots('summary', self.group.summary)
        else:
            ctx.tag.fillSlots('summary', _default_summary_clicktoexpand)
        ctx.tag.fillSlots('items', [inevow.IRenderer(item) for item in
                group.items])
        return ctx.tag

registerAdapter(CollapsibleGroupFragment, CollapsibleGroup, inevow.IRenderer)

#registerAdapter(form.GroupFragment, CollapsibleGroup, inevow.IRenderer)

# --------------------------------------------------------------------------

class SemiHiddenPassword(widget.TextInput):
    def _add_handlers(self, tag):
        tag(onfocus='formal_semi_hidden_password_show(this.id)')
        tag(onblur='formal_semi_hidden_password_hide(this.id)')
        tag(type='password')  # defaults to hidden
        css_class = ''
        if tag.attributes.has_key('class'):
            css_class = tag.attributes['class']  # XXX: direct access to old value, not nice
        if css_class != '':
            css_class += ' semihidden'
        else:
            css_class = 'semihidden'
        tag(_class=css_class)
        tag(tabindex='1')
        return tag
    
    def render(self, ctx, key, args, errors):
        tag = super(SemiHiddenPassword, self).render(ctx, key, args, errors)
        return self._add_handlers(tag)
    
    def renderImmutable(self, ctx, key, args, errors):
        tag = super(SemiHiddenPassword, self).renderImmutable(ctx, key, args, errors)
        return self._add_handlers(tag)
    
# --------------------------------------------------------------------------

class HiddenPassword(widget.TextInput):
    def _add_handlers(self, tag):
        tag(onkeypress='formal_hidden_password_capslock_test(this.id, event)')
        tag(onblur='formal_hidden_password_capslock_hide(this.id)')
        tag(type='password')  # defaults to hidden
        tag(tabindex='1')
        return tag
    
    def render(self, ctx, key, args, errors):
        tag = super(HiddenPassword, self).render(ctx, key, args, errors)
        tag = self._add_handlers(tag)
        return T.span[tag, T.span(_class='capslock-warning', style='visibility: hidden')[u' Caps Lock is on']]
    
    def renderImmutable(self, ctx, key, args, errors):
        tag = super(HiddenPassword, self).renderImmutable(ctx, key, args, errors)
        tag = self._add_handlers(tag)
        return T.span[tag, T.span(_class='capslock-warning', style='visibility: hidden')[u' Caps Lock is on']]
    
# --------------------------------------------------------------------------

class FormItemAccessor:
    """Gives an access to form items and functionality for manipulating them."""

    def __init__(self, form, ctx):
        self.form = form
        self.ctx = ctx

    def form_walk_trough(self, field_function = None, group_in_function = None, group_out_function = None, walk_items = None):
        def iterate_items(items):
            for item in items:
                if isinstance(item, formal.Group):
                    handle_group(item)
                elif isinstance(item, formal.Field):
                    handle_field(item)
                else:
                    # print 'Unknown item: ' + item.name
                    pass
    
        def handle_field(field_item):
            # Call callback function for the field
            if (field_function is not None):
                field_function(self.form, self.ctx, field_item)
    
        def handle_group(group_item):
            # Call groupIn function for group
            if (group_in_function is not None):
                group_in_function(self.form, self.ctx, group_item)
            # Iterate trough group items
            iterate_items(group_item.items)
            # Call groupOut callback
            if (group_out_function is not None):
                group_out_function(self.form, self.ctx, group_item)

        if walk_items is None:
            iterate_items(self.form.items)
        else:
            iterate_items(walk_items)

# --------------------------------------------------------------------------

class SubmitField(form.Field):
    pass

class SubmitFieldFragment(form.FieldFragment):
    docFactory = loaders.stan(
        T.div(id=T.slot('fieldId'),
              _class=T.slot('fieldClass'),
              render=T.directive('field'))[
          T.input(id=T.slot('inputId'),
                  _class=T.slot('inputClass'),
                  tabindex='1',   # XXX: tabindex is handled a bit differently here
                  type='submit',
                  name=T.slot('inputName'),
                  value=T.slot('inputValue'),
                  render=T.directive('input'))
        ])
              

    def render_field(self, ctx, data):
        # No fancy widget-stuff here

        ourform = iformal.IForm(ctx)
        classes = ['field', 'submit-field']
        ctx.tag.fillSlots('fieldId', '%s-%s-field' % (ourform.name, self.field.name))  # XXX: unused...
        ctx.tag.fillSlots('fieldClass', ' '.join(classes))

        return ctx.tag

    def render_input(self, ctx, data):
        # No fancy widget-stuff here

        ourform = iformal.IForm(ctx)
        classes = ['submit-input']
        ctx.tag.fillSlots('inputId', '%s-action-%s' % (ourform.name, self.field.name))
        ctx.tag.fillSlots('inputClass', ' '.join(classes))
        ctx.tag.fillSlots('inputName', self.field.name)  # just terminal name component for actions
        ctx.tag.fillSlots('inputValue', self.field.label)
        
        return ctx.tag

registerAdapter(SubmitFieldFragment, SubmitField, inevow.IRenderer)

class SubmitFieldGroup(form.Group):
    pass

class SubmitFieldGroupFragment(form.GroupFragment):
    docFactory = loaders.stan(
        T.div(id=T.slot('id'), _class=T.slot('cssClass'),
              render=T.directive('group'))[ T.slot('items') ]
            )

    def __init__(self, group):
        super(SubmitFieldGroupFragment, self).__init__(group)

    def render_group(self, ctx, data):
        group = self.group

        # Build the CSS class string
        cssClass = ['group', 'submit-group']
        if group.cssClass is not None:
            cssClass.append(group.cssClass)
        cssClass = ' '.join(cssClass)

        # Fill the slots
        ctx.tag.fillSlots('id', util.render_cssid(group.key))
        ctx.tag.fillSlots('cssClass', cssClass)
        items = [inevow.IRenderer(item) for item in group.items]
        items.append(T.span(_class='submit-group-clear'))
        ctx.tag.fillSlots('items', items)

        return ctx.tag

registerAdapter(SubmitFieldGroupFragment, SubmitFieldGroup, inevow.IRenderer)

# --------------------------------------------------------------------------
#
#  SubheadingField, a dummy item which renders as a subheading.  This is an
#  alternative to grouping.  Better approach would be to render subheadings
#  without resorting to a dummy item, but Formal's not made that way.
#

class SubheadingField(form.Field):
    pass

class SubheadingFieldFragment(form.FieldFragment):
    docFactory = loaders.stan(
        T.div(id=T.slot('fieldId'),
              _class=T.slot('fieldClass'),
              render=T.directive('field'))[
          T.div(_class='formal-subheading-field')[ T.slot('fieldContents') ]
          ])
          
    def render_field(self, ctx, data):
        # No fancy widget-stuff here

        ourform = iformal.IForm(ctx)
        classes = ['field', 'subheading-field']
        ctx.tag.fillSlots('fieldId', '%s-%s-field' % (ourform.name, self.field.name))  # XXX: unused...
        ctx.tag.fillSlots('fieldClass', ' '.join(classes))
        ctx.tag.fillSlots('fieldContents', self.field.label)
        return ctx.tag

registerAdapter(SubheadingFieldFragment, SubheadingField, inevow.IRenderer)
