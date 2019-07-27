
from collections import MutableMapping
from threading import RLock
from inspect import getargspec
# from copy import copy
import copy

import json
import sys
import traceback
import re
import inspect

def PlainFunction(f):
    f._plain =True
    return f

def is__plainFunction(f):
    return getattr(f,'_plain',False)

class NullContextManager(object):
    def __init__(self, dummy_resource=None):
        self.dummy_resource = dummy_resource
    def __enter__(self):
        return self.dummy_resource
    def __exit__(self, *args):
        pass
    

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

def _sanitised(s,):
    return re.sub("[^a-zA-Z0-9_]",'_',s)

#### get __file__ 
# import inspect
def get__frameDict(frame=None,level=0, getter="dict"):
    return get__frame(frame,level=level+1,getter=getter)

def get__frame(frame=None,level=0, getter="dict"):
    '''
    if level==0, get the calling frame
    if level > 0, walk back <level> levels from the calling frame
    '''
    if frame is None:
        frame = inspect.currentframe().f_back

    for i in range(level):
        frame = frame.f_back
    _getter  = {
        "dict":lambda x:x.f_locals,
        "func_name":lambda x:x.f_code.co_name
    }[getter]
    context = _getter(frame)
#     context = frame.f_locals
    del frame
    return context
    
class LazyDictionary(MutableMapping):
    def __init__(self, values={},states={}, tb_limit = 10,level=1):
        self.lock = RLock()
        self.values = copy.copy(values)
        self.states = copy.copy(states)
        self.tb_limit = tb_limit
        setattr(self,'__file__',
                get__frameDict(level=level).get('__file__','__file__'))
        setattr(self,'__name__',
                get__frameDict(level=level).get('__name__','__name__'))

        for key in self.values:
            self.states.setdefault(key, "defined")
#             self.states[key] = 'defined'
            
#     def __copy__(self):
#         with self.lock:
#             res = LazyDictionary(values=copy.copy(self.values), 
#                                  states = copy.copy(self.states),
#                                  tb_limit=self.tb_limit,)
#             return res
        
    def __copy__(self):
        with self.lock:
            newone = type(self)()
            newone.__dict__.update({k:copy.copy(v) for 
                                    k,v in self.__dict__.items()
                                   if k not in ['lock']})
        return newone        
        
    def copy(self):
        return self.__copy__()
    
    def redefine(self,level=1):
        with self.lock:
            newone = type(self)(level=level+1)
            newone.__dict__.update({k:copy.copy(v) for 
                                    k,v in self.__dict__.items()
                                   if k not in ['lock','__file__','__name__']})
        return newone    
    
    def unlock(self):
#         del self.lock
        self.lock = NullContextManager()
        return self
        
    def __len__(self):
        return len(self.values)

    def __iter__(self):
        return iter(self.values)
    
    @property
    def keysFromSanitised(self):
        res = {}
        for k in self.values:
            k_sans = _sanitised(k)
            assert k_sans not in res, (k, res[k_sans])
            res[k_sans] = k 
            
#         {k:_sanitised(v) for k,v in self.values}
        return res

    def __getitem__(self, key):
        with self.lock:
            if key in self.states:
                if self.states[key] == 'evaluating':
                    raise CircularReferenceError('value of "%s" depends on itself' % key)
                elif self.states[key] == 'error':
                    raise self.values[key]
                elif self.states[key] == 'defined':
                    value = self.values[key]
                    if callable(value) and not is__plainFunction(value):
                        (args, varargs, keywords, defaults) = getargspec(value)
                        if len(args) == 0:
                            _args = []
                        elif len(args)==1:
                            _args = [self]
                        elif len(args)==2:
                            _args = [self,key]
                        elif len(args) >= 3:
                            _args = [self,key]
                            for k in args[2:]:
                                _args.append( self[ self.keysFromSanitised[k] ] )
                        else:
                            assert 0,(len(args),)
                        
                        self.states[key] = 'evaluating'
                        try:
                            self.values[key] = value(*_args)
                        except Exception as ex:
                            self.values[key] = ex
                            self.states[key] = 'error'
                            print (json.dumps(get__callstack(self.tb_limit)[::-1],indent=4))
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
    def toDill(self, to= None):
        import dill
        if to is None:
            v = dill.dumps(self)
            return v
        else:
            with open(to,'wb') as f:
                dill.dump(self,f)
            return 