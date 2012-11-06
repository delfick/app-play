#!/usr/bin/env python

import logging
import sys

if __name__ == '__main__':
    logger = logging.getLogger('')
    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter("time=%(asctime)s\tcomponent=%(name)s\tmsg=%(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)

    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    from app import BetterApp
    BetterApp().execute()
