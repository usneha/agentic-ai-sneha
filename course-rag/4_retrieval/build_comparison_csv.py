"""
Builds the retrieval-vs-generation comparison CSV from output/rag_eval.json.

Generated answers come from rag_eval.json; the verdicts/winner/why columns
are a manual analysis of retrieval relevance and answer quality for each
(question, method) pair.

Run from the repo root:
    uv run python 4_retrieval/build_comparison_csv.py

Writes output/retrieval_comparison.csv
"""

import csv
import json
from pathlib import Path

RAG_EVAL_PATH = Path(__file__).parent.parent / "output" / "rag_eval.json"
OUTPUT_PATH = Path(__file__).parent.parent / "output" / "retrieval_comparison.csv"

ANALYSIS = {
    "How does an AI agent decide what actions to take?": {
        "semantic": "Retrieval: Partial (3/5 relevant; two generic slide chunks like \"What is an AI Agent? *we'll cover this in Week 3\" added little). Generation: Good but generic - covers the model-as-brain/reasoning framing only.",
        "bm25": "Retrieval: Good (4/5 relevant, uniquely surfaced the \"6-Step Framework for Designing Agentic Applications\" chunk - judgment calls, action inference via APIs, risk factors). Generation: Best - most detailed and grounded answer.",
        "hybrid": "Retrieval: Good (mix of primer + RAG pipeline + tool-calling chunks). Generation: Good - adds tool-calling/system-prompt framing but misses BM25's \"6-step framework\" detail.",
        "winner": "BM25",
        "why": "BM25 uniquely retrieved the \"6-Step Framework for Designing Agentic Applications\" chunk (decisions/judgment, action inference via APIs, risk factors per step) - the most precise answer to \"how does an agent decide actions\" in the corpus. Semantic and hybrid both missed it and gave more generic answers.",
    },
    "How does a transformer understand relationships between words?": {
        "semantic": "Retrieval: Excellent (5/5 relevant, all from \"The Illustrated Transformer\"/\"Attention Is All You Need\", directly on-topic). Generation: Excellent - full coverage of self-attention, Q/K/V vectors, and positional encoding.",
        "bm25": "Retrieval: Weak (2/5 relevant; pulled in tangential transcript chunks about LLM history, chunking, and temperature/topK that share generic words like \"model\"/\"word\"). Generation: Decent - LLM filtered the noise but the answer is thinner on Q/K/V detail.",
        "hybrid": "Retrieval: Good (3/5 relevant). Generation: Good - covers self-attention and Q/K/V, comparable to semantic with one fewer supporting chunk.",
        "winner": "Semantic",
        "why": "All 5 semantic results are directly about transformer self-attention mechanics from the dedicated source material, giving the cleanest, most complete context. BM25 retrieval was diluted by transcript chunks sharing generic vocabulary (\"model\", \"word\", \"transformer\") but discussing unrelated topics (LLM history, chunking, temperature/topK).",
    },
    "How do prompts influence model behavior?": {
        "semantic": "Retrieval: Good (4/5 relevant, including the system-prompt vs prompt distinction and prompt anti-patterns). Generation: Good - covers prompt vs system prompt and structure/clarity.",
        "bm25": "Retrieval: Good (4/5 relevant, strong on anti-patterns and \"prompts are the only way to steer your LLM\"). Generation: Decent but thinner - misses the system-prompt vs prompt distinction.",
        "hybrid": "Retrieval: Good (combines anti-patterns + system-prompt distinction + lost-in-the-middle context chunks). Generation: Best - covers both the prompt/system-prompt distinction and structural effects on output quality.",
        "winner": "Hybrid",
        "why": "Hybrid's RRF merge pulled in both the \"system prompt vs prompt\" chunk (semantic-favored) and the \"prompt anti-patterns / steering the LLM\" chunks (BM25-favored), giving the most complete picture and the most thorough answer of the three.",
    },
    "What are good ways to judge whether an LLM output is correct?": {
        "semantic": "Retrieval: Partial (2/5 strongly relevant - faithfulness/precision/NDCG/recall/MRR chunk and a RAG-evals-frameworks chunk; rest are noise/title-only). Generation: Poor - despite having the metrics chunk, the LLM hedged with \"cannot provide a definitive answer.\"",
        "bm25": "Retrieval: Good (3/5 relevant - strong \"LLM as a judge\" chunks). Generation: Poor - extracted the \"LLM as a judge\" concept but still hedged into a non-answer.",
        "hybrid": "Retrieval: Good (combines the \"LLM as a judge\" chunks with the faithfulness/precision/NDCG/recall/MRR chunk). Generation: Best - confidently lists and defines all 5 evaluation metrics without hedging.",
        "winner": "Hybrid",
        "why": "Clearest case of hybrid beating both pure methods: semantic-only and BM25-only each retrieved only half the relevant evidence (metrics vs. LLM-as-judge concept) and both generators hedged into a non-answer. Hybrid's merged context gave the LLM complete, mutually-reinforcing evidence to produce a confident, well-structured answer.",
    },
    "What components do agentic AI systems need?": {
        "semantic": "Retrieval: Partial (mostly meta-level \"agentic frameworks\" discussion plus 2 irrelevant slide-title chunks). Generation: Poor - declined to answer despite the \"AI Agent Tech Stack\" chunk describing concrete layers (frameworks, SDKs, harness).",
        "bm25": "Retrieval: Partial (similar framework-level chunks, plus an \"intents and entities\" chunk). Generation: Poor - same hedge pattern, \"cannot provide a definitive answer.\"",
        "hybrid": "Retrieval: Partial (best mix - includes the \"Deep Dive: AI Agent Tech Stack\" chunk describing frameworks/SDKs/harness/memory layers). Generation: Poor - still hedges despite having the most concrete chunk of the three.",
        "winner": "None / Tie",
        "why": "All three retrieved overlapping, framework-level chunks rather than a single chunk that explicitly enumerates \"components,\" and all three generations hedged into a non-answer regardless of which chunks were present - even hybrid, which had the most concrete \"Tech Stack\" chunk. This looks like a generation/prompting issue (overly conservative refusal) rather than a retrieval differentiator.",
    },
    "What is BM25?": {
        "semantic": "Retrieval: Excellent (5/5 relevant, including the literal \"BM25 is the king of this family\" definition slide and the \"BM25 beats vectors\" slide). Generation: Excellent - comprehensive, accurate definition covering ranking function, use cases, and tradeoffs.",
        "bm25": "Retrieval: Failed (0/5 relevant - none of the top results mention BM25's definition, likely because \"BM25\" appears so often across the corpus that its IDF is too low to be discriminative, so common query words dominate). Generation: Honest failure - correctly states the context contains no info on BM25, but useless as an answer.",
        "hybrid": "Retrieval: Good (3/5 relevant - recovers the BM25 definition slide via the semantic leg of RRF, but 2 BM25-only slots are wasted on irrelevant chunks). Generation: Excellent - comprehensive and accurate, nearly matching semantic.",
        "winner": "Semantic",
        "why": "The predicted BM25 blind spot for this edge case: BM25-only retrieval completely misses the slide that defines BM25, almost certainly because the term \"BM25\" is too frequent across the corpus (low IDF) to be discriminative. Semantic search nails the definition via embedding similarity. Hybrid recovers it through its semantic leg but wastes 2/5 slots on BM25-only noise that semantic-only avoids.",
    },
    "What does the course say about Pinecone?": {
        "semantic": "Retrieval: Excellent (5/5 relevant - managed vector DB definition, guest lecture announcement, demo usage). Generation: Excellent - comprehensive and accurate, covers ANN index, metadata filters, hybrid search, guest lecture.",
        "bm25": "Retrieval: Failed (1/5 relevant - only the \"production-grade Pinecone/Weaviate\" tech-stack chunk mentions Pinecone; the rest are dominated by common words like \"course\"/\"about\" from the natural-language query). Generation: Honest but thin - \"no further details provided about Pinecone.\"",
        "hybrid": "Retrieval: Partial (2/5 relevant - semantic leg recovers 2 good Pinecone chunks, but 3 BM25-only irrelevant chunks crowd out semantic's strongest hits like the guest-lecture/managed-DB slide). Generation: Thin - mentions Pinecone's role in graph/embedding storage but misses the core \"managed vector DB + guest lecture\" framing.",
        "winner": "Semantic",
        "why": "Counter to the assumption that BM25 excels at proper-noun queries: BM25's simple whitespace tokenizer with no stopword removal let common words in the natural-language query (\"the\", \"course\", \"about\") dominate scoring, so chunks that repeat \"course\" often outranked chunks that actually discuss Pinecone. Semantic correctly retrieved all 5 of the most Pinecone-relevant chunks. Hybrid's RRF was dragged down by BM25's irrelevant contributions, producing a noticeably thinner answer.",
    },
    "What does Aishwarya Srinivasan say about embeddings?": {
        "semantic": "Retrieval: Excellent (5/5 relevant - directly hits the \"Understanding Embeddings\" chapter where Aishwarya explains embeddings, plus model-selection and vector-space chunks). Generation: Excellent - detailed, correctly attributed, covers the numerical-representation analogy and model-selection criteria.",
        "bm25": "Retrieval: Failed (0/5 relevant - all 5 chunks merely mention \"Aishwarya Srinivasan\" as a name/speaker label or course-title author, with zero embeddings content). Generation: Honest failure - \"context does not contain any information about Aishwarya Srinivasan's views on embeddings.\"",
        "hybrid": "Retrieval: Partial (2/5 relevant via the semantic leg - \"Understanding Embeddings\" and \"Choosing an Embedding Model\"). Generation: Good but thinner - covers the core analogy but misses the model-selection/vector-space detail semantic included.",
        "winner": "Semantic",
        "why": "Another instructor-name edge case where BM25 over-indexes on the literal name \"Aishwarya Srinivasan\" - which appears on nearly every slide title and as a speaker label throughout - without any pull toward \"embeddings,\" producing 5 name-only matches and a complete non-answer. Semantic correctly captured the *combination* of speaker + topic. Hybrid recovers some of this via its semantic leg but loses ground to 3 irrelevant BM25-only name-mention chunks.",
    },
    "vector database": {
        "semantic": "Retrieval: Excellent (5/5 relevant - direct definitions, Aishwarya's explanation, and demo usage). Generation: Excellent - comprehensive coverage of storage, ANN/HNSW, filtering, and operational features.",
        "bm25": "Retrieval: Excellent (5/5 relevant - same core definition chunks plus a \"dense vs sparse search\" quiz chunk adding a hybrid-search angle). Generation: Excellent - comparable depth to semantic, slightly more concise.",
        "hybrid": "Retrieval: Excellent (5/5 relevant, including 2 \"both\"-origin results where semantic and BM25 agreed - strong consensus signal). Generation: Excellent - broadest answer, combining direct definitions with the dense/sparse hybrid-search angle.",
        "winner": "Hybrid (slight edge / effectively a 3-way tie)",
        "why": "\"Vector database\" is a core, heavily-covered topic, so all three methods retrieved 5/5 relevant chunks and produced comprehensive, accurate answers - the expected \"easy\" control case. Hybrid edges out marginally by combining the clearest direct-definition chunks (flagged as \"both\" origin) with the BM25-favored \"dense vs sparse search\" chunk. The near-identical quality across all three confirms hybrid doesn't hurt well-covered topics.",
    },
    "How can you tell if a chatbot's answer is good or bad?": {
        "semantic": "Retrieval: Partial (2/5 relevant - online-eval/monitoring chunks; rest are tangential chatbot-architecture chunks). Generation: Partial - correctly describes the user-feedback/online-eval signal, but misses the offline relevancy/accuracy/faithfulness framing.",
        "bm25": "Retrieval: Good (2/5 strongly relevant - the \"how to evaluate RAG: relevancy/accuracy/faithfulness\" chunk and the golden-dataset chunk). Generation: Good - clean, well-structured answer around offline metrics, though it misses the online/user-feedback angle.",
        "hybrid": "Retrieval: Good (combines the offline-metrics chunk from BM25 with the retrieval-vs-generation debugging chunk from semantic). Generation: Best - covers both offline metrics (relevancy/accuracy/faithfulness) and the retrieval/generation separation framing.",
        "winner": "Hybrid",
        "why": "Despite this query deliberately avoiding course jargon (\"LLM evaluation\", \"judge\"), BM25 still found the key \"how to evaluate RAG: relevancy, accuracy, faithfulness\" chunk via shared words like \"good\" and \"answers\". Semantic found a complementary \"debug retrieval vs. generation separately\" chunk. Hybrid's merge captured both perspectives - a good outcome for hybrid even on a query designed to favor semantic search.",
    },
}


def build_csv():
    rag_eval = json.loads(RAG_EVAL_PATH.read_text())
    answers = {(r["question"], r["method"]): r["answer"] for r in rag_eval}

    rows = []
    for question, analysis in ANALYSIS.items():
        row = {"Question": question, "Winner": analysis["winner"], "Why": analysis["why"]}
        for method, column in (("semantic", "Semantic"), ("bm25", "BM25"), ("hybrid", "Hybrid")):
            answer = answers[(question, method)]
            row[column] = f"{answer}\n\nVerdict: {analysis[method]}"
        rows.append(row)

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Question", "Semantic", "BM25", "Hybrid", "Winner", "Why"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    build_csv()
