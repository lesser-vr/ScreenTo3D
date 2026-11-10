"""Language-independent messages shared with workers; no Qt or GPU dependency."""
import json
import re
from numbers import Integral, Real
from string import Formatter


class Message(str):
    """English diagnostic text with its untranslated template and arguments."""
    def __new__(cls, source, **values):
        values = {key: _argument(value) for key, value in values.items()}
        value = super().__new__(cls, source.format(**values))
        value.source, value.values = source, values
        return value

    def __add__(self, other):
        return JoinedMessage((self, other))

    def __radd__(self, other):
        return JoinedMessage((other, self))

    def __getnewargs_ex__(self):
        return (self.source,), self.values


class JoinedMessage(str):
    def __new__(cls, parts):
        parts = tuple(_argument(part) for part in parts)
        value = super().__new__(cls, ''.join(map(str, parts)))
        value.parts = tuple(parts)
        return value

    def __add__(self, other):
        return JoinedMessage((*self.parts, other))

    def __radd__(self, other):
        return JoinedMessage((other, *self.parts))

    def __getnewargs_ex__(self):
        return (self.parts,), {}


def message_value(value):
    if isinstance(value, BaseException):
        return value.args[0] if len(value.args) == 1 and isinstance(value.args[0], (Message, JoinedMessage)) else str(value)
    return value if isinstance(value, (Message, JoinedMessage)) else str(value)


def _argument(value):
    # A saved UI message must not retain an exception traceback or native owner.
    if isinstance(value, BaseException):
        return message_value(value)
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        return float(value)
    return str(value)


def joined(separator, values):
    parts=[]
    for value in values:
        if parts:
            parts.append(separator)
        parts.append(value)
    return JoinedMessage(parts)


def payload(value):
    value = message_value(value)
    if isinstance(value, Message):
        return {'source': value.source, 'values': {k: payload(v) if isinstance(v, (Message, JoinedMessage, BaseException)) else v for k,v in value.values.items()}}
    if isinstance(value, JoinedMessage):
        return {'parts': [payload(v) for v in value.parts]}
    return value


def from_payload(value, depth=0):
    if depth > 8:
        raise ValueError('Message nesting limit exceeded')
    if isinstance(value,str):
        return value
    if not isinstance(value,dict):
        raise ValueError('Invalid message payload')
    if set(value)=={'parts'} and isinstance(value['parts'],list) and len(value['parts']) <= 64:
        return JoinedMessage(tuple(from_payload(v,depth+1) for v in value['parts']))
    if set(value)=={'source','values'} and isinstance(value['source'],str) and isinstance(value['values'],dict):
        if len(value['source'])>4096 or len(value['values'])>32:
            raise ValueError('Message size limit exceeded')
        for _,name,spec,conversion in Formatter().parse(value['source']):
            if name is not None and (not name.isidentifier() or not re.fullmatch(r'(?:\.[0-6]f)?',spec) or conversion not in (None,'s','r','a')):
                raise ValueError('Unsupported message format')
        args={}
        for key,item in value['values'].items():
            if not isinstance(key,str) or not key.isidentifier():
                raise ValueError('Invalid message argument')
            if isinstance(item,dict):
                item=from_payload(item,depth+1)
            elif item is not None and not isinstance(item,(str,int,float,bool)):
                raise ValueError('Invalid message argument type')
            args[key]=item
        return Message(value['source'],**args)
    raise ValueError('Invalid message payload')


PREFIX='ScreenTo3D-message-v1:'


def encode_message(value, limit=1000):
    value=message_value(value)
    raw=str(value).encode('utf-8')
    if isinstance(value,(Message,JoinedMessage)):
        try:
            encoded=(PREFIX+json.dumps(payload(value),ensure_ascii=False,separators=(',',':'))).encode('utf-8')
            if len(encoded)<=limit:
                return encoded
        except (TypeError,ValueError):
            pass
    return raw[:limit].decode('utf-8','ignore').encode('utf-8')


def decode_message(value):
    if isinstance(value,bytes):
        value=value.decode('utf-8','replace')
    if value.startswith(PREFIX):
        try:
            return from_payload(json.loads(value[len(PREFIX):]))
        except (ValueError,TypeError,KeyError,IndexError,AttributeError):
            pass
    return value
