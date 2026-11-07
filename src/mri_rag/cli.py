"""CLI del laboratorio educativo; todo local y reproducible."""

from __future__ import annotations

import argparse
import json

from .answer import ask
from .corpus import load_corpus, verify_manifest
from .evaluation import evaluate
from .retrieval import build_index


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MRI-RAG-HELPER | laboratorio educativo")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="Verifica manifiesto y construye SQLite FTS5")
    sub.add_parser("preflight", help="Comprueba integridad y metadatos")
    ask_p = sub.add_parser("ask", help="Pregunta al RAG local")
    ask_p.add_argument("question")
    ask_p.add_argument("--mode", choices=["sparse", "hybrid"], default="sparse")
    ask_p.add_argument("--llm", choices=["none", "ollama"], default="none")
    ask_p.add_argument("--model", default="qwen3:1.7b")
    eval_p = sub.add_parser("eval", help="Métricas de búsqueda")
    eval_p.add_argument("--split", choices=["dev", "test", "all"], default="test")
    eval_p.add_argument("--k", type=int, default=3)
    args = p.parse_args(argv)
    if args.command == "build":
        out = build_index()
    elif args.command == "preflight":
        cards, sources = load_corpus()
        checks = verify_manifest()
        out = {
            "status": "PASS" if all(checks.values()) else "FAIL",
            "cards": len(cards),
            "sources": len(sources),
            "hashes": checks,
        }
    elif args.command == "ask":
        out = ask(args.question, mode=args.mode, llm=args.llm, model=args.model)
    else:
        out = evaluate(split=args.split, k=args.k)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
