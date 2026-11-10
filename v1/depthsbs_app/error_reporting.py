"""Stable worker error IDs; private exception detail remains explicitly opt-in."""
from .catalogs import ERRORS
from .messages import ErrorMessage, as_error, message_value, payload


def error_event(error, *, detailed=False):
    value=message_value(error)
    typed=as_error(value)
    if typed.error_id=='E_UNKNOWN' and not isinstance(value,ErrorMessage):
        # Compatibility adapter for unconverted media tools and third-party errors.
        # Typed application errors never depend on English/translated wording.
        text=str(error)
        error_id=next((key for key,item in ERRORS.items()
                       if any(text.startswith(prefix) for prefix in item.get('legacy_prefixes',[]))), 'E_CONVERSION')
        typed=ErrorMessage(error_id)
    definition=ERRORS.get(typed.error_id,ERRORS['E_UNKNOWN'])
    public=ErrorMessage(typed.error_id,public=True)
    diagnostics='\n'.join(dict.fromkeys(filter(None,[str(error),typed.details,*getattr(error,'__notes__',[])]))) if detailed else ''
    shown=ErrorMessage(typed.error_id,details=diagnostics[:16000],**typed.values) if detailed else public
    event=dict(event='error',type=type(error).__name__,code=definition['category'],
               error_id=typed.error_id,message=str(error) if detailed else str(public),
               localized=payload(shown),cleanup_failed=bool(getattr(error,'__notes__',None)))
    if detailed:
        event['notes']=getattr(error,'__notes__',[])
    return event
