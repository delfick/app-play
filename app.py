#!/usr/bin/env python

from functools import wraps
from textwrap import dedent
import collections
import inspect
import types
import copy
import os

from core.app_generator import AppHandler
from core.generator import parse_app_spec
from core.introspection import whereami
from core.decorators import Uses
from core.base import BaseApp

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

class App(BaseApp):
    __metaclass__ = parse_app_spec(AppHandler)

    class Genie:
        __main__ = BasicGenie

    class Strategy:
        __main__ = Empty

    class Attrs:
        one = 1

    class Checkers:
        def check_one(self):
            assert self.one == 1

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
    __metaclass__ = parse_app_spec(AppHandler)
    runner = None

    class Strategy:
        __main__ = Utility
        __location__ = whereami()

    class Components:
        blah = 3
        __location__ = whereami()

    class Install:
        genie = None
        __location__ = whereami()

class BetterApp(DifferentApp):
    __metaclass__ = parse_app_spec(AppHandler)
    @Uses("components.blah")
    def action(self, blah):
        print 'joy to the world! : {}'.format(blah)
