from __future__ import with_statement
import sys
import types
import fenrir.bottle
sys.modules['bottle'] = fenrir.bottle
fenrir.bottle.__path__ = []
fenrir.bottle.ext = fenrir.bottle._ImportRedirect('bottle.ext', 'bottle_%s').module

# Make all fenrir.bottle classes report __module__ as 'bottle'
for name, obj in list(fenrir.bottle.__dict__.items()):
    if isinstance(obj, type) and obj.__module__ == 'fenrir.bottle':
        obj.__module__ = 'bottle'

# Map test.example_settings for compatibility
from . import example_settings
test_mod = sys.modules.setdefault('test', types.ModuleType('test'))
test_mod.example_settings = example_settings
sys.modules['test.example_settings'] = example_settings

from .tools import chdir
import unittest
import os

try:
    import coverage  # type: ignore
    coverage.process_startup()
except ImportError:
    pass

import bottle
bottle.debug(True)

