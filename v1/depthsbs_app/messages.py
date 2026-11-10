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


class ErrorMessage(Message):
    """Stable error identity plus detached parameters and opaque diagnostics."""
    def __new__(cls, error_id, *, details='', public=False, **values):
        from .catalogs import ERRORS
        if not isinstance(error_id, str) or not re.fullmatch(r'E_[A-Z0-9_]{1,80}', error_id):
            raise ValueError('Invalid error ID')
        definition = ERRORS.get(error_id, ERRORS['E_UNKNOWN'])
        source = definition['public' if public else 'source']
        value = super().__new__(cls, source, **values)
        value.error_id = error_id
        value.details = str(message_value(details)) if details else ''
        value.public = bool(public)
        return value

    def __getnewargs_ex__(self):
        return (self.error_id,), dict(details=self.details, public=self.public, **self.values)


def as_error(value):
    """Normalize legacy UI failures at the boundary without guessing translated text."""
    from .catalogs import ERRORS_BY_SOURCE
    value = message_value(value)
    if isinstance(value, ErrorMessage):
        return value
    if isinstance(value, Message) and value.source in ERRORS_BY_SOURCE:
        return ErrorMessage(ERRORS_BY_SOURCE[value.source], **value.values)
    return ErrorMessage('E_UNKNOWN', details=value)


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
    if isinstance(value, ErrorMessage):
        return dict(error_id=value.error_id, values={k: payload(v) if isinstance(v, (Message, JoinedMessage, BaseException)) else v for k,v in value.values.items()},
                    details=value.details, public=value.public)
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
    if set(value)=={'error_id','values','details','public'}:
        if (not isinstance(value['values'],dict) or len(value['values'])>32
                or not isinstance(value['details'],str) or len(value['details'])>16384
                or not isinstance(value['public'],bool)):
            raise ValueError('Invalid error payload')
        args=_payload_arguments(value['values'],depth,reserved=('details','public','error_id'))
        return ErrorMessage(value['error_id'],details=value['details'],public=value['public'],**args)
    if set(value)=={'source','values'} and isinstance(value['source'],str) and isinstance(value['values'],dict):
        if len(value['source'])>4096 or len(value['values'])>32:
            raise ValueError('Message size limit exceeded')
        for _,name,spec,conversion in Formatter().parse(value['source']):
            if name is not None and (not name.isidentifier() or not re.fullmatch(r'(?:\.[0-6]f)?',spec) or conversion not in (None,'s','r','a')):
                raise ValueError('Unsupported message format')
        args=_payload_arguments(value['values'],depth)
        return Message(value['source'],**args)
    raise ValueError('Invalid message payload')


def _payload_arguments(values,depth,reserved=()):
    args={}
    for key,item in values.items():
        if not isinstance(key,str) or not key.isidentifier() or key in reserved:
            raise ValueError('Invalid message argument')
        if isinstance(item,dict):
            item=from_payload(item,depth+1)
        elif item is not None and not isinstance(item,(str,int,float,bool)):
            raise ValueError('Invalid message argument type')
        args[key]=item
    return args


PREFIX='ScreenTo3D-message-v1:'


def encode_message(value, limit=1000):
    value=message_value(value)
    raw=str(value).encode('utf-8')
    if isinstance(value,(Message,JoinedMessage)):
        try:
            encoded=(PREFIX+json.dumps(payload(value),ensure_ascii=False,separators=(',',':'))).encode('utf-8')
            if len(encoded)<=limit:
                return encoded
            if isinstance(value,ErrorMessage):
                # Mailboxes are bounded. Preserve identity and translatability even
                # when private diagnostic strings do not fit; never slice JSON.
                compact=payload(value)
                def shrink(item,size):
                    if isinstance(item,str):return item.encode('utf-8')[:size].decode('utf-8','ignore')
                    if isinstance(item,dict):return {k:shrink(v,size) for k,v in item.items()}
                    if isinstance(item,list):return [shrink(v,size) for v in item]
                    return item
                for size in (256,128,64,16,0):
                    compact['details']=shrink(value.details,size)
                    compact['values']={k:shrink(str(v) if isinstance(v,(Message,JoinedMessage)) else v,size) for k,v in value.values.items()}
                    encoded=(PREFIX+json.dumps(compact,ensure_ascii=False,separators=(',',':'))).encode('utf-8')
                    if len(encoded)<=limit:
                        return encoded
        except (TypeError,ValueError):
            pass
    if isinstance(value,ErrorMessage):
        raw=(f'[{value.error_id}] '+str(value)).encode('utf-8')
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
