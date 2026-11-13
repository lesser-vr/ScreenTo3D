"""Read current options first, retaining legacy launch-script compatibility."""
import os


def get(name,default=None):
    if name in os.environ:return os.environ[name]
    if name.startswith('SCREENTO3D_'):
        for prefix in ('STEREOTO3D_','DEPTHSBS_'):
            old=prefix+name[len('SCREENTO3D_'):]
            if old in os.environ:return os.environ[old]
    return os.environ.get(name,default)


def required(name):
    value=get(name)
    if value is None:raise KeyError(name)
    return value
