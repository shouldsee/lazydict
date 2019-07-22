
from collections import MutableMapping
from threading import RLock
from inspect import getargspec
# from copy import copy
import copy

import json
import sys
import traceback
def get__callstack(traceback_limit=10):
    return traceback.extract_tb(  sys.exc_info()[-1], limit=traceback_limit)

def get_version():
    VERSION = (     # SEMANTIC
        1,          # major
        0,          # minor
        0,          # patch
        'beta.2',   # pre-release
        None        # build metadata
    )

    version = "%i.%i.%i" % (VERSION[0], VERSION[1], VERSION[2])
    if VERSION[3]:
        version += "-%s" % VERSION[3]
    if VERSION[4]:
        version += "+%s" % VERSION[4]
    return version

class LazyDictionaryError(Exception):
    pass

class CircularReferenceError(LazyDictionaryError):
    pass

class ConstantRedefinitionError(LazyDictionaryError):
    pass

class LazyDictionary(MutableMapping):
    def __init__(self, values={},states={}):
        self.lock = RLock()
        self.values = copy.copy(values)
        self.states = copy.copy(states)
        for key in self.values:
            self.states.setdefault(key, "defined")
#             self.states[key] = 'defined'
            
    def __copy__(self):
        with self.lock:
            res = LazyDictionary(values=copy.copy(self.values), 
                                 states = copy.copy(self.states))
            return res
    def copy(self):
        return self.__copy__()
        
    def __len__(self):
        return len(self.values)

    def __iter__(self):
        return iter(self.values)

    def __getitem__(self, key):
        with self.lock:
            if key in self.states:
                if self.states[key] == 'evaluating':
                    raise CircularReferenceError('value of "%s" depends on itself' % key)
                elif self.states[key] == 'error':
                    raise self.values[key]
                elif self.states[key] == 'defined':
                    value = self.values[key]
                    if callable(value):
                        (args, varargs, keywords, defaults) = getargspec(value)
                        if len(args) == 0:
                            _args = []
                        elif len(args)==1:
                            _args = [self]
                        elif len(args)==2:
                            _args = [self,key]
                        else:
                            assert 0,(len(args),)
                        
                        self.states[key] = 'evaluating'
                        try:
                            self.values[key] = value(*_args)
                        except Exception as ex:
                            self.values[key] = ex
                            self.states[key] = 'error'
                            print (json.dumps(get__callstack()[::-1],indent=4))
                            raise ex
                            
                    self.states[key] = 'evaluated'
            return self.values[key]

    def __contains__(self, key):
        return key in self.values

    def __setitem__(self, key, value):
        with self.lock:
            if key in self.states and self.states[key][0:4] == 'eval':
                raise ConstantRedefinitionError('"%s" is immutable' % key)
            self.values[key] = value
            self.states[key] = 'defined'

    def __delitem__(self, key):
        with self.lock:
            if key in self.states and self.states[key][0:4] == 'eval':
                raise ConstantRedefinitionError('"%s" is immutable' % key)
            del self.values[key]
            del self.states[key]

    def __str__(self):
        return str(self.values)

    def __repr__(self):
        return "LazyDictionary({0})".format(repr(self.values))
