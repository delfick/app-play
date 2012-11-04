#!/usr/bin/env python

from functools import wraps
from textwrap import dedent
import collections
import inspect
import logging
import types
import copy
import os

def whereami():
    source, line = inspect.stack()[-2][1:3]
    return (os.path.abspath(source), line)

class DeveloperError(Exception): pass
class HelloWorld(object):
    def __call__(self):
        print 'hello world'
class GoodbyeWorld(object):
    def __call__(self):
        print 'good bye world!'
class Utility(object):
    __uses__ = ['action']

    def __init__(self, log_finish=True, log_startup=True):
        self.log_finish = log_finish
        self.log_startup = log_startup

    def runner(self, app):
        app.action()
class Empty(object):
    def runner(self):
        pass
class Logger(object): pass
class Proctitle(object):
    def install(self, app):
        print 'installing proctitle'
    def get_title(self):
        return ''
class SigTermStop(object):
    def install(self, app):
        print 'installing sigterm stop'
class BasicGenie(object):
    def install(self, app):
        print 'installing genie'
class BackGroundTasks(object):
    def install(self, app):
        print 'installing background tasks'
class Cli(object):
    def get_parser(self):
        pass

def dec_not_extendable(f):
    f.__extendable__ = False
    return f
def dec_not_nullable(f):
    f.__nullable__ = False
    return f

def location_of(thing):
    if hasattr(thing, '__location__'):
        location, number = thing.__location__
    else:
        number = None
        location = None
        try:
            location = os.path.abspath(inspect.getsourcefile(thing))
        except TypeError:
            # Must have been a builtin
            pass

        if location is not None:
            try:
                _, number = inspect.getsourcelines(thing)
            except IOError:
                # Couldn't read source file
                pass
    return location, number

def position_for(thing):
    location, number = location_of(thing)
    if location is None:
        return repr(thing)

    base = "{} at {}".format(repr(thing), location)
    if number is None:
        return base
    else:
        return "{}:{}".format(base, number)

class NotFound(Exception):
    def __init__(self, *args, **kwargs):
        self.base = kwargs.get('base')
        self.path = kwargs.get('path')
        self.found = kwargs.get('found')
        super(NotFound, self).__init__(*args)

def find_obj(base, path):
    obj = base
    found = []
    parts = path.split(".")

    for part in parts:
        if not hasattr(obj, part):
            raise NotFound(path=path, base=base, found=found)
        obj = getattr(obj, part)
        found.append(part)
    return obj

class Uses(object):
    def __init__(self, *paths):
        self.paths = paths

    def __call__(self, func):
        @wraps(func)
        def wrapped(app, *args, **kwargs):
            objs = []
            for path in self.paths:
                try:
                    nxt = find_obj(app, path)
                except NotFound, error:
                    message = dedent("""
                        Function '{}'
                        Requires obj '{}' on '{}'.
                        Only have up to '{}'
                        """.format(position_for(func), error.path, error.base, '.'.join(error.found))
                        )
                    raise DeveloperError(message)
                objs.append(nxt)
            positional = list(objs) + list(args)
            return func(app, *positional, **kwargs)
        return wrapped

class BookKeeper(object):
    def __init__(self):
        self.requirements = []

    def add_requirement(self, paths, identity, origin):
        if isinstance(paths, basestring):
            paths = [paths]
        self.requirements.append((paths, identity, origin))

    def sanity_check(self, base, paths, identity, origin):
        for path in paths:
            try:
                find_obj(base, path)
            except NotFound as error:
                message = dedent("""
                    {}
                    Created attribute '{}' which requires '{}'
                    Now calling from '{}' but only have up to '{}'
                    """.format(position_for(origin), identity, error.path, error.base, error.found)
                    )
                raise DeveloperError(message)

class AppFactory(object):
    def __init__(self, name, bases):
        self.name = name
        self.bases = bases

    def update(self, attrs):
        declaration_objs = self.find_declarations(attrs)
        declarations = {key:vars(dec) for key, dec in declaration_objs.items()}
        declaration_name_map = {dec.lower():dec for dec in declarations}

        known_creators = self.get_helpers(prefix="create_")
        known_declarations = self.get_helpers(prefix="make_")

        # Special declaration blocks
        self.handle(attrs, declarations, declaration_name_map, known_declarations)

        # Unknown declaration blocks
        for declaration in sorted(declarations):
            lowered = declaration.lower()
            if lowered not in known_declarations and lowered not in known_creators:
                spec = declarations[declaration]
                inherited = self.find_inherited(declaration, spec, attrs)
                instance = self.generate_thing(declaration, spec, inherited, attrs)
                attributes = {lowered:instance}
                self.complain_about_conflicts(attrs, attributes, "App already has {}".format(declaration))
                attrs.update(attributes)
                self.add_sanity_checks(attrs, attributes, attrs[declaration])

        # Special creators
        self.handle(attrs, declarations, declaration_name_map, known_creators)

    def handle(self, attrs, declarations, name_map, handlers):
        for declaration in sorted(handlers):
            if declaration in name_map:
                name = name_map[declaration]
                if name in declarations:
                    val = declarations[name]
                    handler = handlers[declaration]

                    nullable = self.is_nullable(handler)
                    extendable = self.is_extendable(handler)
                    inherited = self.find_inherited(name, val, attrs, extendable=extendable, nullable=nullable)

                    attributes = handler(name, val, inherited, attrs)
                    if attributes:
                        self.complain_about_conflicts(attrs, attributes, inherited, desc="App already has attributes declared by {}".format(name))
                        attrs.update(attributes)
                        self.add_sanity_checks(attrs, attributes, attrs[name])

    def add_sanity_checks(self, attrs, added_attributes, origin):
        if '__bookkeeper__' not in attrs:
            attrs['__bookkeeper__'] = BookKeeper()

        for key, val in added_attributes.items():
            if hasattr(val, '__uses__') and val.__uses__:
                attrs['__bookkeeper__'].add_requirement(val.__uses__, key, origin)

    def is_declaration(self, obj):
        return type(obj) is type or isinstance(obj, types.ClassType)

    def is_nullable(self, handler):
        """Determine if a handler says this declaration allows for __nullify_inherited__"""
        if not getattr(handler, "__nullable__", True):
            return False
        else:
            return True

    def is_extendable(self, handler):
        """Determine if a handler says this declaration allows for __extend__"""
        if not getattr(handler, "__extendable__", True):
            return False
        else:
            return True

    def find_declarations(self, attrs):
        declarations = {}
        for key, val in attrs.items():
            if self.is_declaration(val):
                declarations[key] = val
        return declarations

    def get_helpers(self, prefix):
        known = {}
        for attr in dir(self):
            if attr.startswith(prefix):
                name = attr[len(prefix):].lower()
                handler = getattr(self, attr)
                if name in known:
                    raise DeveloperError("Declaration for {} specified twice".format(name))
                known[name] = handler
        return known

    def attributes_from(self, attrs):
        attributes = {}
        for key, val in attrs.items():
            if not key.startswith("_"):
                if isinstance(val, types.LambdaType) and val.__name__ == '<lambda>':
                    val = val()
                attributes[key] = val
        return attributes

    def find_inherited(self, name, values, attrs, extendable=True, nullable=True):
        inherited = {}
        if '__extend__' in values and not extendable:
            message = dedent("""
                {}
                '{}' is a special declaration that puts all it's properties on the instance being created.
                This means that __extends__ doesn't make sense here.
                You need to instead overwrite inherited properties to do nothing, or something different.
                Just as you would with normal inheritance, because subclasses can't (and shouldn't) modify parent classes
                """.format(position_for(attrs[name]), name)
                )
            raise DeveloperError(message)
        if '__nullify_inherited__' in values and not nullable:
            message = dedent("""
                {}
                '{}' is a declaration that doesn't put all it's properties on the instance being created.
                This means that if you want to not use properties inherited from super declarations, use __extend__=False
                """.format(position_for(attrs[name]), name)
                )
            raise DeveloperError(message)

        if values.get('__extend__', True):
            for base in self.bases:
                if hasattr(base, name):
                    inherited.update(vars(getattr(base, name)))
        return inherited

    def combine_dicts(self, *dicts):
        values = {}
        for dct in dicts:
            values.update(dct)
        return values

    def complain_about_conflicts(self, original, adding, inherited=None, desc=None):
        if desc is None and isinstance(adding, basestring):
            desc = "App already has an {} attribute".format(adding)
        else:
            desc = "App already has following attributes declared"

        conflicts = []
        if isinstance(adding, basestring):
            adding = [adding]

        for key in adding:
            if key in original and (not inherited or key not in inherited):
                conflicts.append(key)

        if conflicts:
            raise DeveloperError("{} : {}".format(desc, conflicts))

    def nulls_if_necessary(self, values, inherited):
        if values.get('__nullify_inherited__'):
            return {key:None for key in inherited}
        return {}

    def replace_nulled_functions(self, attributes, inherited, origin):
        for key, val in attributes.items():
            if val is None and key in inherited and inherited[key] is not None:
                def make_empty(key=key):
                    def nothing_func(app, *args, **kwargs):
                        message = dedent("""
                            {}
                            Made inherited attribute '{}' None
                            """.format(position_for(origin), key)
                            )
                        raise NotImplementedError(message)
                    nothing_func.__checker__ = False
                    return nothing_func
                attributes[key] = make_empty()

    def make_method_delegate(self, ident, path, name, attrs):
        cached = {}
        def getter(app):
            if 'val' not in cached:
                try:
                    obj = find_obj(app, path)
                except NotFound as error:
                    message = dedent("""
                        {}
                        Created a delegate method to '{}' with identitfier '{}'
                        Now calling from '{}' but only have up to '{}'
                        """.format(position_for(attrs[name]), error.path, ident, error.base, error.found)
                        )
                    raise DeveloperError(message)
                cached['val'] = obj

            return cached['val']

        def setter(app, val):
            cached['val'] = val

        return property(getter, setter)

    def generate_thing(self, name, declaration, inherited, attrs):
        values = declaration
        if declaration.get("__extends__", True):
            values = self.combine_dicts(inherited, declaration)

        if '__main__' not in declaration:
            raise DeveloperError("Component {} needs to have a __main__ variable".format(name))

        kls = declaration['__main__']
        kwargs = self.attributes_from(values)

        try:
            return kls(**kwargs)
        except Exception as error:
            import traceback
            error = "\n{}".format('\n'.join("\t{}".format(line) for line in dedent(traceback.format_exc()).split('\n')))
            message = dedent("""
                {}
                Failed to create custom object '{}'
                calling={}
                error=%s
                Calling object with {}
                Object wants {}
                """.format(position_for(attrs[name]), name, position_for(kls.__init__), kwargs, inspect.getargspec(kls.__init__))
                )
            raise DeveloperError(message % error)

    @dec_not_extendable
    def copy_attributes_to_instance(self, name, declaration, inherited, attrs):
        attributes = self.nulls_if_necessary(declaration, inherited)
        attributes.update(self.attributes_from(declaration))
        self.replace_nulled_functions(attributes, inherited, attrs[name])
        return attributes
    make_attrs = copy_attributes_to_instance
    make_bookkeeper = copy_attributes_to_instance

    @dec_not_nullable
    def make_install(self, name, declaration, inherited, attrs):
        attributes = {'_installers' : {key:val for key, val in declaration.items() if not key.startswith("_")}}
        attributes['_installers']['__extend__'] = declaration.get("__extend__", True)
        return attributes

    @dec_not_nullable
    def make_components(self, name, declaration, inherited, attrs):
        values = declaration
        if declaration.get("__extends__", True):
            values = self.combine_dicts(inherited, declaration)

        for key, kls in values.items():
            if not key.startswith("_"):
                if kls is not None and isinstance(kls, collections.Callable):
                    values[key] = kls()

        identity = name.lower()
        return {name.lower():type(identity, (object, ), values)}

    @dec_not_extendable
    def create_methods(self, name, methods, inherited, attrs):
        attributes = self.nulls_if_necessary(methods, inherited)
        for ident, path in methods.items():
            if not ident.startswith("_"):
                if path is None:
                    attributes[ident] = path
                else:
                    attributes[ident] = self.make_method_delegate(ident, path, name, attrs)
        self.replace_nulled_functions(attributes, inherited, attrs[name])
        return attributes

def generate_app(name, bases, attrs):
    factory = AppFactory(name, bases)
    factory.update(attrs)
    app = type(name, bases, attrs)
    return app

class AppAdministration(object):
    def __init__(self, app):
        self.app = app

    def bootstrap(self):
        self.sanity_check()
        self.install()

    def sanity_check(self):
        app = self.app

        # Make sure any dynamically created things are sane on this instance
        for paths, identity, origin in self.sanity_requirements:
            app.__bookkeeper__.sanity_check(app, paths, identity, origin)

        # And call any check functions we have
        for attr in dir(app):
            if attr.startswith("check_"):
                checker = getattr(app, attr)
                if isinstance(checker, collections.Callable) and getattr(checker, '__checker__', True):
                    checker()

    def install(self):
        app = self.app

        for key, installer, origin in self.installers:
            try:
                obj = find_obj(app, installer)
            except NotFound as error:
                message = dedent("""
                    {}
                    Created a delegate method to install obj at '{}' (identitfier='{}')
                    Now calling from '{}' but only have up to '{}'
                    """.format(position_for(origin), installer, key, error.base, '.'.join(error.found))
                    )
                raise DeveloperError(message)

            if not hasattr(obj, 'install'):
                message = dedent("""
                    {}
                    Created a delegate method to install obj at '{}' (identitfier='{}')
                    Found the obj ({}), but it doesn't have an install method
                    """.format(position_for(origin), installer, key, obj)
                    )
                raise DeveloperError(message)
            
            # And finally, call the installer
            obj.install(app)

    def from_mro(self, key):
        installed = {}
        for obj in inspect.getmro(self.app.__class__):
            try:
                yield find_obj(obj, key), obj
            except NotFound:
                pass

    @property
    def installers(self):
        installed = []
        for installers, base in self.from_mro("_installers"):
            if installers:
                for key, installer in installers.items():
                    if key not in installed and not key.startswith("_"):
                        installed.append(key)
                        if installer is not None:
                            origin = base
                            if hasattr(base, "Install"):
                                origin = base.Install
                            yield key, installer, origin

                # Make sure we ignore inherited things to install if need be
                if not installers.get('__extend__', True):
                    break 

    @property
    def sanity_requirements(self):
        found = []
        for requirements, _ in self.from_mro('__bookkeeper__.requirements'):
            if requirements:
                for paths, identity, origin in requirements:
                    if identity not in found:
                        found.append(identity)
                        yield paths, identity, origin

class BaseApp(object):
    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)
        self.__administration__ = AppAdministration(self)

    def execute(self):
        """Bootstrap the app and start running"""
        self.__administration__.bootstrap()
        self.runner(self)

class App(BaseApp):
    __metaclass__ = generate_app

    class Genie:
        __main__ = BasicGenie

    class Strategy:
        __main__ = Empty

    class Attrs:
        one = 1

    class BookKeeper:
        def check_one(self):
            assert self.one ==1

    class Components:
        cli = Cli
        logging = Logger
        proctitle = Proctitle
        sigtermstop = SigTermStop
        backgroundtasks = BackGroundTasks

    class Methods:
        runner = "strategy.runner"
        get_title = "components.proctitle.get_title"
        get_parser = "components.cli.get_parser"

    class Install:
        genie = "genie"
        sigterm = "components.sigtermstop"
        proctitle = "components.proctitle"

class DifferentApp(App):
    __metaclass__ = generate_app

    class Strategy:
        __main__ = Utility
        __location__ = whereami()

    class Components:
        blah = 3

    class Install:
        genie = None
        __location__ = whereami()

class BetterApp(DifferentApp):
    @Uses("components.blah")
    def action(self, blah):
        print 'joy to the world! : {}'.format(blah)

if __name__ == '__main__':
    BetterApp().execute()
