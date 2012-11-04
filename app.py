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
class Special(object): pass
class Delegate(Special):
    def __init__(self, name):
        self.name = name
    def transform(self):
        def wrapped_delegate(app, *args, **kwargs):
            if not hasattr(app, self.name):
                raise Exception("Expected app to have a function {}. But it didn't :(".format(self.name))
            return getattr(app, self.name)(*args, **kwargs)
        return wrapped_delegate
class HelloWorld(object):
    def __call__(self):
        print 'hello world'
class GoodbyeWorld(object):
    def __call__(self):
        print 'good bye world!'
class Utility(object):
    def __init__(self, action, log_finish=True, log_startup=True):
        self.action = action
        self.log_finish = log_finish
        self.log_startup = log_startup

    def runner(self, app):
        self.action(app)
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
                self.complain_about_conflicts(attrs, {lowered:instance}, "App already has {}".format(declaration))
                attrs[lowered] = instance

        # Special creators
        self.handle(attrs, declarations, declaration_name_map, known_creators)

    def post_creation(self, app, name, bases, attrs):
        if 'Install' in attrs and self.is_declaration(attrs['Install']):
            if '_installers' not in attrs:
                installers = self.generate_installers(vars(attrs['Install']), attrs)
                if installers:
                    if not hasattr(app, '_installers') or app._installers is None:
                        app._installers = {}
                    else:
                        if not hasattr(app._installers, "update"):
                            raise DeveloperError("App._installers has no update method, we can't add to it")
                    app._installers.update(installers)

    def handle(self, attrs, declarations, name_map, handlers):
        for declaration in sorted(handlers):
            if declaration in name_map:
                name = name_map[declaration]
                if name in declarations:
                    val = declarations[name]
                    handler = handlers[declaration]

                    extendable = self.extendable(handler)
                    inherited = self.find_inherited(name, val, attrs, extendable=extendable)
                    handler(name, val, inherited, attrs)

    def is_declaration(self, obj):
        return type(obj) is type or isinstance(obj, types.ClassType)

    def extendable(self, handler):
        """Determine if a handler says this declaration allows for __extend__"""
        if hasattr(handler, "__extendable__") and not handler.__extendable__:
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
                elif isinstance(val, Special):
                    val = val.transform()
                attributes[key] = val
        return attributes

    def position_for(self, thing):
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

            if location is None:
                return repr(thing)
            else:
                try:
                    _, number = inspect.getsourcelines(thing)
                except IOError:
                    # Couldn't read source file
                    pass

        base = "{} at {}".format(repr(thing), location)
        if number is None:
            return base
        else:
            return "{}:{}".format(base, number)

    def find_inherited(self, name, values, attrs, extendable=True):
        inherited = {}
        if '__extend__' in values and not extendable:
            raise DeveloperError(dedent("""
                  {}
                  {} is a special declaration that puts all it's properties on the instance being created.
                  This means that __extends__ doesn't make sense here.
                  You need to instead overwrite inherited properties to do nothing, or something different.
                  Just as you would with normal inheritance, because subclasses can't (and shouldn't) modify parent classes
                  """.format(self.position_for(attrs[name]), name)
                )
            )

        if '__extend__' not in values or values['__extend__']:
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

    def find_obj(self, attrs, path):
        parts = path.split(".")
        if type(attrs) is not dict:
            obj = attrs
            tail = parts
            found = []
        else:
            head, tail = parts[0], parts[1:]
            if head not in attrs:
                raise DeveloperError("Trying to find {} on app. Don't even have the start of that (couldn't find {})".format(path, head))
            obj = attrs[head]
            found = [head]

        for part in tail:
            if not hasattr(obj, part):
                raise DeveloperError("Specified bad path : {} : Only have up to {}".format(path, found))
            obj = getattr(obj, part)
            found.append(part)
        return obj

    def generate_installers(self, install, attrs):
        installers = {}
        for ident, path in install.items():
            if not ident.startswith("_"):
                if path is None:
                    installers[ident] = None
                else:
                    obj = self.find_obj(attrs, path)
                    if not hasattr(obj, 'install'):
                        raise DeveloperError("{} declaration points to an object with no install method : {}".format(name, path))
                    installer = getattr(obj, 'install')
                    args, varargs, keywords, defaults = inspect.getargspec(installer)
                    if 'app' not in args or (defaults and 'app' not in defaults):
                        raise DeveloperError("Install method for '{}:{}' must have an install function that takes an app parameter".format(path, obj))
                    installers[ident] = installer

        return installers

    def make_attrs(self, name, declaration, inherited, attrs):
        attributes = self.attributes_from(declaration)
        self.complain_about_conflicts(attrs, attributes, inherited, desc="App already has attributes declared by {}".format(name))
        attrs.update(attributes)

    def make_install(self, name, declaration, inherited, attrs):
        pass

    @dec_not_extendable
    def make_bookkeeper(self, name, declaration, inherited, attrs):
        attributes = self.attributes_from(declaration)
        self.complain_about_conflicts(attrs, attributes, inherited, desc="App already has attributes declared by {}".format(name))
        attrs.update(attributes)

    @dec_not_extendable
    def make_components(self, name, declaration, inherited, attrs):
        attributes = {}
        for key, kls in declaration.items():
            if not key.startswith("_"):
                if kls is not None:
                    if key in attrs and key not in inherited:
                        raise DeveloperError("Trying to add one of the {} ({}) but app already has that attribute".format(name, key))
                    attributes[key] = kls()

        identity = name.lower()
        self.complain_about_conflicts(attrs, identity)
        attrs[identity] = type(identity, (object, ), attributes)

    def generate_thing(self, name, declaration, inherited, attrs):
        values = self.combine_dicts(inherited, declaration)

        if '__main__' not in declaration:
            raise DeveloperError("Component {} needs to have a __main__ variable".format(name))

        kwargs = self.attributes_from(declaration)
        return declaration['__main__'](**kwargs)

    @dec_not_extendable
    def create_methods(self, name, methods, inherited, attrs):
        attributes = {}
        for ident, path in methods.items():
            if not ident.startswith("_"):
                def make_wrapper(path=path):
                    def wrapped(app, *args, **kwargs):
                        obj = self.find_obj(app, path)
                        return obj(*args, **kwargs)
                    return wrapped
                attributes[ident] = make_wrapper()

        self.complain_about_conflicts(attrs, attributes, inherited, desc="App already has attributes declared by {}".format(name))
        attrs.update(attributes)

def generate_app(name, bases, attrs):
    factory = AppFactory(name, bases)
    factory.update(attrs)
    app = type(name, bases, attrs)
    factory.post_creation(app, name, bases, attrs)
    return app

class BaseApp(object):
    _installers = {}

    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)

    def install(self):
        for _, installer in self._installers.items():
            if installer:
                installer(self)

    def sanity_check(self):
        # Make sure any dynamically created things are sane on this instance
        if hasattr(self, '__bookkeeper__') and self.__bookkeeper__:
            self.__bookkeeper__.sanity_check()

        # And call any check functions we have
        for attr in dir(self):
            if attr.startswith("check_"):
                checker = getattr(self, attr)
                if isinstance(checker, collections.Callable):
                    checker()

    def execute(self):
        """Install what needs to be installed and run the strategy"""
        self.sanity_check()
        self.install()
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
        action = Delegate("action")

    class Install:
        genie = None

    class Attrs:
        one = 2

    class BookKeeper:
        __location__ = whereami()
        __extend__ = False
        check_one = None

class BetterApp(DifferentApp):
    def action(self):
        print 'joy to the world!'

if __name__ == '__main__':
    BetterApp().execute()
