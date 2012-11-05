from textwrap import dedent
import types

from errors import DeveloperError, RequirementError
from bookkeeper import BookKeeper

class DelegateRequirementError(RequirementError):
    path_desc = "delegate_to"

def parse_app_spec(handler):
    """
        Look at an app and update it's __bookkeeper__ attribute
        To reflect the specification of the app
        Combined with specification of app's super classes
        Based on handler specified
    """
    def parser(name, bases, attrs):
        factory = handler(name, bases)
        factory.update(attrs)
        created = type(name, bases, attrs)
        factory.post_creation(created, name, bases, attrs)
        return created
    return parser

class SpecHandler(object):
    """
        Look at (name, bases, attrs) used to make a class
        and update attrs and attrs['__bookkeper__'] to reflect the semantics of the specification
    """
    def __init__(self, name, bases):
        self.name = name
        self.bases = bases

    ########################
    ###   USAGE
    ########################

    def update(self, attrs):
        """Update attrs to reflect the specifications they hold"""
        self.ensure_bookkeeper(attrs)

        # Get handlers for special declarations
        known_declarations = self.find_handlers(prefix="make_")

        # Get the delarations in the attrs
        declaration_objs = self.find_declarations(attrs)
        declarations = {key:vars(dec) for key, dec in declaration_objs.items()}
        declaration_name_map = {dec.lower():dec for dec in declarations}

        # Determine which declarations aren't known
        special_declarations = {key:declarations[key] for key, val in declaration_objs.items() if key.lower() not in known_declarations}

        # Understood declaration blocks
        for name, spec, handler in self.declarations_for_handlers(known_declarations, declarations, declaration_name_map):
            self.handle_known(name, spec, handler, attrs)

        # Unknown declaration blocks
        for name, spec in sorted(special_declarations.items()):
            self.handle_unknown(name, spec, attrs)

    def post_creation(self, created, name, bases, attrs):
        """Record any attributes this class manually replaced"""
        bookkeeper = created.__bookkeeper__
        manually_replaced = []

        for base in self.bases:
            if hasattr(base, '__bookkeeper__'):
                added = base.__bookkeeper__.added
                for attr in added:
                    if attr in attrs and attr not in self.added:
                        manually_replaced.append(attr)

        if manually_replaced:
            bookkeeper.replaced_attrs(manually_replaced, created)

        bookkeeper.normalise_attr_record()

    ########################
    ###   HANDLERS
    ########################

    def handle_known(self, name, spec, handler, attrs):
        """
            Handle declaration with a handler
            Determine if handler is nullable/extendable for when finding inherited
        """
        nullable = self.is_nullable(handler)
        extendable = self.is_extendable(handler)
        inherited = self.find_inherited(name, spec, attrs, extendable=extendable, nullable=nullable, force=True)
        attributes = handler(name, spec, inherited, attrs)
        self.handle_attributes(name, attributes, inherited, attrs)

    def handle_unknown(self, name, spec, attrs):
        """
            Handle unknown declarations
            Create one instance from the whole spec
            and add as the name of the declaration, lowered, as a new attribute
        """
        inherited = self.find_inherited(name, spec, attrs)
        attributes = self.combine_dicts(inherited, spec)
        kls = attributes.get("__main__")

        kwargs = self.attributes_from(attributes)
        attributes = {name.lower():(name, kls, kwargs)}
        self.handle_attributes(name, attributes, None, attrs, bookkeeper_method="add_custom")

    def handle_attributes(self, name, attributes, inherited, attrs, bookkeeper_method=None):
        """
            Add new attributes to attrs
            Make sure there are no conflicts
            And add any necessary sanity checkers
        """
        if attributes:
            self.complain_about_conflicts(name, attributes, attrs)
            self.add_sanity_checks(attrs, attributes, attrs[name])
            if bookkeeper_method:
                self.add_to_bookkeeper(name, attributes, inherited, attrs, bookkeeper_method=bookkeeper_method)
            else:
                attrs.update(attributes)
                self.bookkeeper(attrs).added_attributes({key:attrs[name] for key in attributes}, origin=attrs[name])

    ########################
    ###   FINDERS
    ########################

    def find_declarations(self, attrs):
        """Return all the delcarations in attrs"""
        declarations = {}
        for key, val in attrs.items():
            if self.is_declaration(val):
                declarations[key] = val
        return declarations

    def find_handlers(self, prefix):
        """Return all the handlers on this class with provided prefix"""
        known = {}
        for attr in dir(self):
            if attr.startswith(prefix):
                name = attr[len(prefix):].lower()
                handler = getattr(self, attr)
                if name in known:
                    raise DeveloperError("Declaration for {} specified twice".format(name))
                known[name] = handler
        return known

    def find_inherited(self, name, attributes, attrs, extendable=True, nullable=True, force=False):
        """
            Find any inherited values from self.bases
            Complain if using __extend__ or __nullify_inherited__ if need be
        """
        inherited = {}
        if '__extend__' in attributes and not extendable:
            message = dedent("""
                '{}' is a special declaration that puts all it's properties on the instance being created.
                This means that __extends__ doesn't make sense here.
                You need to instead overwrite inherited properties to do nothing, or something different.
                Just as you would with normal inheritance, because subclasses can't (and shouldn't) modify parent classes
                """.format(name)
                )
            raise DeveloperError(message, origin=attrs[name])
        if '__nullify_inherited__' in attributes and not nullable:
            message = dedent("""
                '{}' is a declaration that doesn't put all it's properties on the instance being created.
                This means that if you want to not use properties inherited from super declarations, use __extend__=False
                """.format(name)
                )
            raise DeveloperError(message, origin=attrs[name])

        if attributes.get('__extend__', True) or force:
            for base in self.bases:
                if hasattr(base, name):
                    inherited.update(vars(getattr(base, name)))
        return inherited

    ########################
    ###   IDENTITY
    ########################

    def is_declaration(self, obj):
        """Says yes if the obj is an old style class"""
        return isinstance(obj, types.ClassType)

    def is_nullable(self, handler):
        """Determine if a handler says this declaration allows for __nullify_inherited__"""
        return bool(getattr(handler, "__nullable__", True))

    def is_extendable(self, handler):
        """Determine if a handler says this declaration allows for __extend__"""
        return bool(getattr(handler, "__extendable__", True))

    ########################
    ###   MODIFIERS
    ########################

    def nulls_if_necessary(self, values, inherited):
        """Return keys in inherited that should be None, based of __nullify_inherited__ in values"""
        if values.get('__nullify_inherited__'):
            return {key:None for key in inherited}
        return {}

    def combine_dicts(self, *dicts):
        """Combine multiple dictionaries"""
        values = {}
        for dct in dicts:
            values.update(dct)
        return values

    def add_sanity_checks(self, attrs, added_attributes, origin):
        """Add sanity checks to attrs['__bookkeeper__']"""
        for key, val in added_attributes.items():
            if hasattr(val, '__uses__') and val.__uses__:
                self.bookkeeper(attrs).add_requirement(val.__uses__, key, origin)

    def replace_nulled_functions(self, attributes, inherited, origin):
        """Make empty functions for attributes that are defined as None"""
        result = {}
        for key, val in attributes.items():
            if val is None:
                # Value is none, make it empty
                def make_empty(key=key):
                    """Create empty function and mark it as such"""
                    def nothing_func(*args, **kwargs):
                        """Empty function that does nothing"""
                        pass
                    nothing_func.__checker__ = False
                    nothing_func.__emptiedby__ = origin
                    return nothing_func

                # Add the empty function
                result[key] = make_empty()
        return result

    def ensure_bookkeeper(self, attrs):
        """
            Make sure there is a __bookkeeper__ in attrs
            Look for bookkeeper_kls in attrs and on bases to see what type it should be
            default to core.bookkeeper.BookKeeper
        """
        if '__bookkeeper__' not in attrs:
            kls = attrs.get('bookkeeper_kls')
            if kls is None:
                for base in self.bases:
                    kls = getattr(base, 'bookkeeper_kls', None)
                    if kls is not None:
                        break

            if kls is None:
                kls = BookKeeper

            attrs['__bookkeeper__'] = BookKeeper()
        return attrs['__bookkeeper__']
    
    # Alias for getting bookkeeper from attrs
    bookkeeper = ensure_bookkeeper

    ########################
    ###   UTILITY
    ########################

    def add_to_bookkeeper(self, name, spec, inherited, attrs, bookkeeper_method):
        """Add spec to the bookkeeper"""
        method = getattr(attrs['__bookkeeper__'], bookkeeper_method)
        if inherited is None:
            method(spec, attrs[name])
        else:
            method(
                  {key.lower():val for key, val in spec.items() if not key.startswith("_")}
                , inherited
                , extend = spec.get("__extend__", True)
                , origin = attrs[name]
                )

    def copy_attributes_to_instance(self, name, spec, inherited, attrs, generate_method=None):
        """Just copy the attributes from the delaration onto the class"""
        attributes = self.nulls_if_necessary(spec, inherited)
        self.bookkeeper(attrs).removed_attributes(attributes, origin=attrs[name])

        if not generate_method:
            self.attributes_from(spec)
        else:
            for identity, thing in spec.items():
                if not identity.startswith("_"):
                    if thing is None:
                        attributes[identity] = path
                    else:
                        attributes[identity] = generate_method(identity, thing, name, attrs)

        replaced = self.replace_nulled_functions(attributes, inherited, attrs[name])
        attributes.update(replaced)
        self.bookkeeper(attrs).removed_attributes(replaced, origin=attrs[name])
        return attributes

    def declarations_for_handlers(self, handlers, declarations, name_map):
        """
            Yield declarations and respective handler
            for all the declarations and handlers specified
            name_map is a map of lower case declaration to original declaration name
        """
        for name in sorted(handlers):
            if name in name_map:
                declaration = name_map[name]
                if declaration in declarations:
                    yield declaration, declarations[declaration], handlers[name]

    def attributes_from(self, attrs):
        """
            Given a dictionary of values, return appropiate attributes
            That is those that don't start with underscore
            And lambdas are called to get a value
        """
        attributes = {}
        for key, val in attrs.items():
            if not key.startswith("_"):
                attributes[key] = val
        return attributes

    def complain_about_conflicts(self, name, adding, attrs):
        """
            Complain about conflicts between original and what's beeing added
            Essentially if it's already in original then we are defining things on the class itself
            and via the metaclass, which could lead to surprising effects, so let's dissalow that
        """
        conflicts = []
        if isinstance(adding, basestring):
            adding = [adding]

        for key in adding:
            if key in attrs:
                conflicts.append(key)

        if conflicts:
            raise DeveloperError("Adding attributes {} from metaclass but already defined by hand on same class".format(conflicts), origin=attrs[name])
