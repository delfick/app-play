from bookkeeper import BookKeeper
from admin import AppAdmin
import logging

class BaseApp(object):
    admin_kls = AppAdmin
    bookkeeper_kls = BookKeeper

    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)

    def bootstrap(self):
        self.admin_kls(self).bootstrap()

    def execute(self):
        """Bootstrap the app and start running"""
        self.bootstrap()
        self.runner(self)
