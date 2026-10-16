from typing import Any

from django import forms


class StyledFormMixin:
    """Apply the template's CSS classes to every widget of a form."""

    fields: dict[str, forms.Field]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault('class', 'Textarea')
                widget.attrs.setdefault('rows', 3)
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault('class', 'Input Select')
            elif isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
                continue
            else:
                widget.attrs.setdefault('class', 'Input')
