"""
Interactive CLI for evaluating the RAG generator.

Run:
    uv run python 5_chat/run_chat.py          # default k=5
    uv run python 5_chat/run_chat.py --k 8    # override retrieval k

Commands during session:
    /k <n>   — change retrieval k on the fly
    /quit    — exit
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generator import generate


def _print_sources(results):
    print("\nSources:")
    for i, (doc, origin, rerank_score, sem_score) in enumerate(results, 1):
        meta = doc.metadata
        label = meta.get("source_name", "unknown")
        parts = [f"  {i}. {label}"]
        if "page" in meta:
            parts.append(f"p.{meta['page']}")
        if "speaker" in meta:
            parts.append(meta["speaker"])
        parts.append(f"[{meta.get('source_type', '')}]")
        parts.append(f"origin={origin}")
        parts.append(f"rerank={rerank_score:.4f}")
        sem_str = f"{sem_score:.4f} (lower=better)" if sem_score is not None else "n/a"
        parts.append(f"semantic_distance={sem_str}")
        print("  ·  ".join(parts))
        preview = " ".join(doc.page_content.split())[:200]
        print(f"     {preview}...")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5, help="Number of chunks to retrieve")
    args = parser.parse_args()

    k = args.k
    history = []
    print(f"Course RAG — gpt-4o-mini  (k={k})")
    print("Commands: /k <n> to change k, /quit to exit\n")

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not query:
            continue
        if query == "/quit":
            break
        if query.startswith("/k "):
            try:
                k = int(query.split()[1])
                print(f"  k set to {k}\n")
            except ValueError:
                print("  Usage: /k <integer>\n")
            continue

        print()
        answer, results = generate(query, history=history, k=k)
        print(f"Answer:\n{answer}\n")
        _print_sources(results)

        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
