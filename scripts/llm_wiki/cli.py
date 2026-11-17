"""CLI: JSON-контракт для агента, с ленивым подключением индексатора."""

import argparse
import json
from pathlib import Path
import sys


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("ожидается положительное целое число")
    return number


def _hops(value):
    number = int(value)
    if not 0 <= number <= 3:
        raise argparse.ArgumentTypeError("hops должен быть от 0 до 3")
    return number


def _parser():
    parser = Parser(
        prog="llm-wiki", description="Локальная LLM wiki и поиск по графу документов"
    )
    commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    for name in [
        "init",
        "ingest",
        "convert",
        "index",
        "search",
        "read",
        "graph",
        "lint",
        "status",
    ]:
        command = commands.add_parser(name)
        command.add_argument(
            "--root", type=Path, required=True, help="Корень wiki с .wiki.json"
        )
        if name == "init":
            command.add_argument("--title", default="LLM Wiki")
        elif name == "ingest":
            command.add_argument("source", type=Path)
            command.add_argument("--title")
        elif name == "convert":
            command.add_argument("--force", action="store_true")
        elif name == "index":
            command.add_argument("--lexical-only", action="store_true")
        elif name == "search":
            command.add_argument("query")
            command.add_argument(
                "--mode", choices=["fulltext", "semantic", "hybrid"], default="hybrid"
            )
            command.add_argument("--limit", type=_positive, default=5)
            command.add_argument("--hops", type=_hops, default=1)
            command.add_argument("--scope", default="")
            command.add_argument("--include-history", action="store_true")
        elif name == "read":
            command.add_argument("path")
            command.add_argument("--start", type=_positive, default=1)
            command.add_argument("--end", type=_positive, default=100)
        elif name == "graph":
            command.add_argument("--node")
            command.add_argument("--hops", type=_hops, default=1)
    return parser


def _dispatch(args):
    root = args.root.expanduser().resolve()
    if args.command == "init":
        from .project import init

        return init(root, args.title)
    if args.command == "ingest":
        from .project import ingest

        return ingest(root, args.source, args.title)
    if args.command == "convert":
        from .convert import convert

        return convert(root, force=args.force)
    if args.command == "index":
        from .index import build

        return build(root, lexical_only=args.lexical_only)
    if args.command == "search":
        from .search import query

        return query(
            root,
            args.query,
            mode=args.mode,
            limit=args.limit,
            hops=args.hops,
            scope=args.scope,
            include_history=args.include_history,
        )
    if args.command == "graph":
        from .graph import inspect

        return inspect(root, node=args.node, hops=args.hops)
    if args.command == "read":
        if args.end < args.start:
            raise ValueError("end не может быть меньше start")
        from .health import read_document

        return read_document(root, args.path, start=args.start, end=args.end)
    from . import health

    return health.lint(root) if args.command == "lint" else health.status(root)


def main(argv=None):
    try:
        result = _dispatch(_parser().parse_args(argv))
        if isinstance(result, dict) and result.get("ok") is False:
            print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "type": type(exc).__name__},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
