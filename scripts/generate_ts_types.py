"""Generate TypeScript types from packages/contracts. Build spec 4; M0.

    packages/contracts is the single source of truth for data shapes. TypeScript
    types are generated from it; never hand-write a duplicate.  -- CLAUDE.md

The generator walks the Pydantic models and emits interfaces, string-literal
unions for the enums, and a discriminated union for Primitive. It writes a header
saying the file is generated, and the output is gitignored, so there is no way to
edit it and have the edit survive.

Run with `make contracts-ts`.
"""

from __future__ import annotations

import datetime
import enum
import sys
import types
import typing
from pathlib import Path

from pydantic import BaseModel

import groma_contracts
from groma_contracts.version import CONTRACTS_VERSION

HEADER = """/* Generated from packages/contracts by scripts/generate_ts_types.py.
 * Contracts version {version}.
 *
 * Do not edit. Change the Pydantic model and run `make contracts-ts`:
 * packages/contracts is the single source of truth for data shapes, and a
 * hand-written duplicate is how the viewer starts disagreeing with its own
 * reports.
 */
"""

SCALARS: dict[object, str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
    datetime.datetime: "string",
    datetime.date: "string",
    type(None): "null",
}


def ts_type(annotation: object) -> str:
    """Render a Python annotation as a TypeScript type."""
    if annotation in SCALARS:
        return SCALARS[annotation]

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin in (typing.Union, types.UnionType):
        parts = [ts_type(a) for a in args]
        # Collapse `| null` into TypeScript's more idiomatic `| null` at the end.
        non_null = [p for p in parts if p != "null"]
        if len(non_null) < len(parts):
            return " | ".join([*dict.fromkeys(non_null), "null"])
        return " | ".join(dict.fromkeys(parts))

    if origin in (list, set, frozenset):
        return f"{ts_type(args[0])}[]" if args else "unknown[]"

    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return f"{ts_type(args[0])}[]"
        return "[" + ", ".join(ts_type(a) for a in args) + "]"

    if origin is dict:
        key, value = ((*args, object, object))[:2]
        key_ts = "string" if key is str else ts_type(key)
        if isinstance(key, type) and issubclass(key, enum.Enum):
            key_ts = key.__name__
        return f"Partial<Record<{key_ts}, {ts_type(value)}>>"

    if origin is typing.Literal:
        return " | ".join(f'"{a}"' if isinstance(a, str) else str(a).lower() for a in args)

    if isinstance(annotation, type):
        if issubclass(annotation, enum.Enum):
            return annotation.__name__
        if issubclass(annotation, BaseModel):
            return annotation.__name__

    # Annotated[...] carries the real type first; discriminated unions arrive here.
    if args:
        return ts_type(args[0])

    return "unknown"


def render_enum(cls: type[enum.Enum]) -> str:
    values = " | ".join(f'"{member.value}"' for member in cls)
    return f"export type {cls.__name__} = {values};\n"


def is_tag(annotation: object) -> bool:
    """True for a Literal with exactly one value — a discriminator, not a choice.

    Pydantic gives these a default (`kind: Literal["box"] = "box"`), which would
    otherwise render them optional. An optional tag breaks narrowing: TypeScript
    cannot discriminate `Primitive` on a field the caller is allowed to omit, and
    the failure shows up as a type error in the viewer rather than here.
    """
    return typing.get_origin(annotation) is typing.Literal and len(typing.get_args(annotation)) == 1


def render_model(cls: type[BaseModel]) -> str:
    lines = [f"export interface {cls.__name__} {{"]
    for name, field in cls.model_fields.items():
        # Optional in TypeScript only when the Python default is None: the server
        # always fills a field that has a real default (a status, a count, an
        # empty list), so the viewer may rely on it. A None default is genuinely
        # absent-or-null on the wire.
        optional = (
            not field.is_required() and field.default is None and not is_tag(field.annotation)
        )
        rendered = ts_type(field.annotation)
        suffix = "?" if optional else ""
        if field.description:
            lines.append(f"  /** {field.description} */")
        lines.append(f"  {name}{suffix}: {rendered};")
    lines.append("}\n")
    return "\n".join(lines)


def collect() -> tuple[list[type[enum.Enum]], list[type[BaseModel]]]:
    enums: dict[str, type[enum.Enum]] = {}
    models: dict[str, type[BaseModel]] = {}

    for name in groma_contracts.__all__:
        obj = getattr(groma_contracts, name)
        if isinstance(obj, type) and issubclass(obj, enum.Enum):
            enums[obj.__name__] = obj
        elif isinstance(obj, type) and issubclass(obj, BaseModel):
            models[obj.__name__] = obj
            # Pull in nested models that are not themselves exported.
            for field in obj.model_fields.values():
                for arg in (field.annotation, *typing.get_args(field.annotation)):
                    if isinstance(arg, type) and issubclass(arg, BaseModel):
                        models.setdefault(arg.__name__, arg)
                    elif isinstance(arg, type) and issubclass(arg, enum.Enum):
                        enums.setdefault(arg.__name__, arg)

    return (
        sorted(enums.values(), key=lambda c: c.__name__),
        sorted(models.values(), key=lambda c: c.__name__),
    )


def generate() -> str:
    enums, models = collect()
    out = [HEADER.format(version=CONTRACTS_VERSION)]

    out.append("\n// Enums\n")
    out.extend(render_enum(e) for e in enums)

    out.append("\n// Models\n")
    out.extend(render_model(m) for m in models)

    out.append(
        "\n// Discriminated on `kind`, matching groma_contracts.geometry.Primitive.\n"
        "export type Primitive = BoxPrim | CylinderPrim | ExtrudedPolyline;\n"
    )
    out.append(f'\nexport const CONTRACTS_VERSION = "{CONTRACTS_VERSION}";\n')
    return "\n".join(out)


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "apps/web/src/api/contracts.ts")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generate(), encoding="utf-8")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
