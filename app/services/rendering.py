from __future__ import annotations

from jinja2 import Environment, StrictUndefined


_env = Environment(
    autoescape=False,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_template(template: str | None, params: dict) -> str | None:
    if template is None:
        return None
    tpl = _env.from_string(template)
    return tpl.render(**(params or {}))


