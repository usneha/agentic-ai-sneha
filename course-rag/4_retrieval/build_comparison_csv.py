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
        "semantic": "Retrieval: Good (3/5 relevant - \"A Primer on How AI Agents Work\" plus two \"Understanding the 6 Levels of Agent Autonomy\" chunks; 2 slots are generic/title-only). Generation: Good - covers the model-as-brain reasoning framing and how the agent's autonomy level (explicit goals vs. self-determined goals) shapes its decisions, but stays fairly general.",
        "bm25": "Retrieval: Partial (2/5 clearly relevant - the \"A 6-Step Framework for Designing Agentic Applications\" step3/step4 chunk and \"Today's Agenda\"; the rest are tangential RAG-pipeline/embedding-model chunks). Generation: Very good - despite thin retrieval, grounds the answer in concrete decision steps (select/reject/escalate to a human), action inference via APIs (email, CRM), and the system-prompt framing.",
        "hybrid": "Retrieval: Good (mix of RAG-pipeline, \"Context Engineering\", the \"6-Step Framework\" step3/step4 chunk, and \"A Primer on How AI Agents Work\"). Generation: Best - combines decision-making based on user intent/goals, action evaluation via APIs, and risk-factor assessment at each step - the most complete answer of the three.",
        "winner": "Hybrid",
        "why": "Hybrid's RRF merge pulls in both the \"A 6-Step Framework for Designing Agentic Applications\" chunk (decisions, action inference via APIs, risk factors) and \"A Primer on How AI Agents Work\", producing the most complete answer - covering decision criteria, action inference, AND risk assessment. BM25 alone reaches a similarly detailed answer from the same 6-step-framework chunk but without the risk-factor framing; semantic's retrieval is good but more general (autonomy-levels framing only).",
    },
    "How does a transformer understand relationships between words?": {
        "semantic": "Retrieval: Excellent (4/5 relevant - three \"The Illustrated Transformer\" chunks, \"Attention Is All You Need\", plus a transformer-architecture transcript chunk). Generation: Good - covers self-attention and positional encoding clearly, though doesn't surface the Query/Key/Value vector mechanism.",
        "bm25": "Retrieval: Good (3/5 relevant - two \"Illustrated Transformer\" chunks plus \"Attention Is All You Need\"; the other 2 are a tangential \"Evolution of LLMs\" chunk and an Illustrated-Transformer discussion-links chunk). Generation: Good - same self-attention + positional-encoding coverage as semantic, comparable quality.",
        "hybrid": "Retrieval: Excellent (4/5 relevant - three \"Illustrated Transformer\" chunks plus \"Attention Is All You Need\"). Generation: Good - self-attention + positional encoding, on par with semantic and BM25.",
        "winner": "Semantic (near three-way tie)",
        "why": "All three methods now retrieve predominantly from \"The Illustrated Transformer\"/\"Attention Is All You Need\" and produce near-identical, accurate answers covering self-attention and positional encoding. With OpenAI embeddings, BM25's retrieval (previously the weak link) is now comparable to semantic/hybrid - none of the three surfaces the Query/Key/Value vector detail this time, which was previously semantic's distinguishing edge.",
    },
    "How do prompts influence model behavior?": {
        "semantic": "Retrieval: Excellent (5/5 relevant - \"Essential LLM Terminology Explained\", \"Prompt Anti-Patterns\", \"Prompt Engineering Fundamentals\" (Claude docs), \"Prompting Fundamentals and Advanced Techniques\", and \"Prompt Engineering vs. Context Engineering\"). Generation: Best - covers the prompt definition, anti-patterns/clarity effects, the system-prompt vs. user-prompt distinction, AND assistant pre-filling as a steering technique.",
        "bm25": "Retrieval: Partial (2/5 relevant - \"Prompt Anti-Patterns\" and \"Prompting Fundamentals\"; the other 3 are LangChain/N8N-framework and project-closing chunks). Generation: Decent - covers steering/clarity and prompt-management tooling, but misses the system-prompt distinction and pre-filling technique.",
        "hybrid": "Retrieval: Good (3/5 relevant - \"Prompt Anti-Patterns\", \"Essential LLM Terminology\", and \"Prompt Engineering Fundamentals\" (Claude docs); 2 LangChain/N8N-framework chunks add little). Generation: Good - covers the prompt definition, anti-patterns, and the importance of prompt engineering for steering output, but thinner than semantic (no system-prompt distinction or pre-filling).",
        "winner": "Semantic",
        "why": "With OpenAI embeddings, semantic retrieval is now 5/5 relevant - including a new web source (\"Prompt Engineering Fundamentals\", Claude docs) not surfaced before - giving the LLM the richest context (anti-patterns + system/user prompt distinction + assistant pre-filling) and the most complete answer. This flips the previous winner (Hybrid), whose retrieval mix is now diluted by 2 LangChain/N8N chunks that crowd out some of semantic's strongest hits.",
    },
    "What are good ways to judge whether an LLM output is correct?": {
        "semantic": "Retrieval: Weak (1/5 relevant - only \"RAG Evaluation Metrics\"; the other 4 are about structured output/function calling and prompting, not evaluation). Generation: Poor - hedges into \"I cannot provide a definitive answer\", mentioning only the \"LLM as a judge\" concept.",
        "bm25": "Retrieval: Partial (2/5 relevant - \"RAG Evaluation Metrics\" and one \"Conclusion and Q&A: LLM as a judge\" chunk; the rest are repeated/tangential Q&A chunks). Generation: Poor - same hedge pattern as semantic.",
        "hybrid": "Retrieval: Partial (2/5 relevant - \"RAG Evaluation Metrics\" and \"Conclusion and Q&A\"; the rest overlap with semantic's structured-output chunks). Generation: Poor - still hedges into a non-answer.",
        "winner": "None / Tie",
        "why": "All three methods now hedge into \"I cannot provide a definitive answer\" - a regression from the prior (HuggingFace-embeddings) run, where hybrid confidently listed 5 evaluation metrics (faithfulness/precision/NDCG/recall/MRR) by retrieving a dedicated metrics-enumeration chunk. With OpenAI embeddings, none of the three retrieves that chunk in their top 5; all default to the generic \"LLM as a judge\" framing and hedge. This looks like a retrieval-shift issue specific to this query, worth re-checking if Stage 5 surfaces it again.",
    },
    "What components do agentic AI systems need?": {
        "semantic": "Retrieval: Excellent (5/5 relevant - three \"Exploring Agentic Frameworks: The AI Tech Stack\" chunks, the \"A 6-Step Framework for Designing Agentic Applications\" chapter chunk, and \"Deep Dive: The AI Agent Tech Stack\"). Generation: Excellent - confidently lists 4 concrete components (Domain Knowledge, Goals, Inputs, Tools) drawn from the 6-step-framework chapter, with no hedging.",
        "bm25": "Retrieval: Partial (1/5 relevant - \"Exploring Agentic Frameworks: The AI Tech Stack\"; the rest are LangChain/N8N comparison, course agenda, and Q&A chunks that miss the 6-step-framework chapter). Generation: Poor - hedges into \"cannot provide a definitive answer\".",
        "hybrid": "Retrieval: Good (3/5 relevant - two \"Exploring Agentic Frameworks: The AI Tech Stack\" chunks plus the \"A 6-Step Framework\" chapter chunk). Generation: Excellent - same confident 4-component answer (Domain Knowledge, Goals, Inputs, Tools) as semantic, nearly identical quality.",
        "winner": "Semantic / Hybrid (tie)",
        "why": "This flips dramatically from the prior run, where all three methods hedged. With OpenAI embeddings, both semantic and hybrid retrieve the \"A 6-Step Framework for Designing Agentic Applications\" chapter-overview chunk, which explicitly enumerates the prerequisites (domain knowledge, goals, inputs, tools) for building an agentic application - letting both produce a confident, well-structured, near-identical answer. BM25 still misses that chunk and hedges, the one method now lagging on this question.",
    },
    "What is BM25?": {
        "semantic": "Retrieval: Excellent (4/5 relevant - Week 2-Session 1.pdf p.25 \"BM25 is the king of this family\", p.39 (TF/IDF/length-normalization scoring detail), p.40 \"BM25 beats vectors\", and a transcript chunk on BM25 vs. vector search). Generation: Excellent - comprehensive, cites all three PDF pages plus the transcript, covering definition, scoring factors, and use cases.",
        "bm25": "Retrieval: Failed (0/5 relevant - same as before: \"Introduction to RAG Evaluation\", \"A Primer on How AI Agents Work\", \"Project 2 Overview\", \"Building a Golden Dataset\", \"Demo Part 1\" - none mention BM25's definition). Generation: Honest failure - \"the provided context does not contain any information about BM25\".",
        "hybrid": "Retrieval: Good (2/5 relevant - recovers p.25 and p.39 via the semantic leg; the other 3 BM25-only slots are the same irrelevant chunks as BM25-only). Generation: Excellent - nearly matches semantic, citing p.25 and p.39 with TF/IDF/length-normalization detail.",
        "winner": "Semantic",
        "why": "Confirms the documented IDF limitation persists independent of the embedding-model swap: BM25's own retrieval still completely misses the chunks that define BM25 (the term \"bm25\" is too frequent across the corpus - low IDF - to be discriminative), so BM25-only retrieval and generation both fail outright. Semantic search (now via OpenAI embeddings) retrieves all the right slides and produces a fully cited, comprehensive answer; hybrid recovers most of it through its semantic leg.",
    },
    "What does the course say about Pinecone?": {
        "semantic": "Retrieval: Excellent (5/5 relevant - \"The Vector Search Pipeline\" (guest-lecture mention), two \"Demo Part 1/2\" chunks on Pinecone usage, and Week 2-Session 1.pdf p.13 on vector-search/ANN/Pinecone features). Generation: Excellent - comprehensive, covers Pinecone as a managed vector DB, ANN index, metadata filters, hybrid search, and the guest lecture.",
        "bm25": "Retrieval: Failed (0/5 relevant - \"Today's Agenda\", \"Live Demo: create_agent\", \"Context Engineering with Many Tools\", \"Live Demo: Stock Portfolio Analyzer\", and \"Agent Harness\" - none mention Pinecone). Generation: Honest failure - \"the provided context does not contain any information about Pinecone\".",
        "hybrid": "Retrieval: Partial (2/5 relevant - \"The Vector Search Pipeline\" and \"Demo Part 1\" recovered via the semantic leg; the other 3 BM25-only slots are irrelevant). Generation: Good - covers Pinecone as a vector DB for semantic search/RAG at scale and the guest lecture, but misses the ANN-index/metadata-filter detail semantic includes.",
        "winner": "Semantic",
        "why": "Same pattern as before the embedding swap: BM25's whitespace tokenizer lets common words in the natural-language query (\"the\", \"course\", \"about\") dominate, so it retrieves zero Pinecone-relevant chunks and fails outright. Semantic search (OpenAI embeddings) retrieves all 5 of the most relevant chunks and produces the most complete answer; hybrid recovers a decent but thinner answer via its semantic leg.",
    },
    "What does Aishwarya Srinivasan say about embeddings?": {
        "semantic": "Retrieval: Good (4/5 relevant - \"Understanding Embeddings\", \"The Building Blocks of LLMs: Transformers, Tokens, and Context\", \"Choosing an Embedding Model\", and \"AI Builder of the Week\"). Generation: Excellent - detailed, correctly attributed, covers the numerical-representation analogy, vector ranges (-1 to +1), and model-selection criteria (parameter size, context length, domain).",
        "bm25": "Retrieval: Failed (0/5 relevant - \"AI Builder of the Week\" (name-mention), Week 1 PDF cover slides, \"Live Demo: create_agent\", and \"Meet Your Instructors\" - all name/title mentions, zero embeddings content). Generation: Honest failure - \"context does not contain any information about Aishwarya Srinivasan's views... cannot answer\".",
        "hybrid": "Retrieval: Partial (2/5 relevant - \"Understanding Embeddings\" and \"The Building Blocks of LLMs\" recovered via the semantic leg). Generation: Excellent - nearly matches semantic, covering the numerical-representation/comparison analogy and vector ranges, though it misses the model-selection criteria semantic includes.",
        "winner": "Semantic",
        "why": "BM25 still over-indexes on the literal name \"Aishwarya Srinivasan\" (appearing on nearly every slide title and as a speaker label) without any pull toward \"embeddings\", producing 5 name-only matches and a complete non-answer - unchanged by the embedding swap, since this is a BM25 tokenization issue, not a semantic one. Semantic (OpenAI embeddings) correctly captures the speaker+topic combination and gives the most complete answer; hybrid recovers most of it via its semantic leg but loses the model-selection detail.",
    },
    "vector database": {
        "semantic": "Retrieval: Excellent (5/5 relevant - Week 2-Session 1.pdf p.12/p.13 (definitions + ANN search), \"Demo Part 1\" (Pinecone usage), and two \"Introduction to Vector Databases\" chunks). Generation: Excellent - comprehensive, covering storage/ANN search, the dataset/embeddings/metadata breakdown, and Pinecone's specific features (ANN index, metadata filters, autoscaling).",
        "bm25": "Retrieval: Good (2/5 strongly relevant - p.12 and \"Introduction to Vector Databases\"; the other 3 are tangential quiz/text-splitter/retrieval-strategy chunks). Generation: Excellent - covers storage, ANN methods (HNSW/IVF/PQ) by name, the dataset/embeddings/metadata breakdown, and semantic-vs-SQL framing - comparable depth to semantic.",
        "hybrid": "Retrieval: Good (3/5 relevant - p.12, \"Introduction to Vector Databases\", and \"Demo Part 1\"; 2 BM25-only quiz/text-splitter chunks add little). Generation: Excellent - covers storage, ANN search, dataset/embeddings/metadata, and semantic-vs-SQL framing, very close to BM25's answer.",
        "winner": "Semantic (near three-way tie)",
        "why": "\"Vector database\" remains a core, heavily-covered topic - all three methods produce comprehensive, accurate answers. Semantic edges ahead slightly by being the only one to surface Pinecone's specific managed-DB features (ANN index, metadata filters, autoscaling) alongside the general vector-DB definition; BM25 and hybrid both give excellent but slightly more generic answers. The near-identical quality across all three confirms this remains an \"easy\" control case even after the embedding swap.",
    },
    "How can you tell if a chatbot's answer is good or bad?": {
        "semantic": "Retrieval: Excellent (4/5 relevant - three \"RAG Evaluation Metrics\" chunks plus \"Live Q&A Session\" on evaluating RAG; one \"From Traditional to Agentic Automation\" chunk is more tangential). Generation: Best - uniquely combines both perspectives: online user-feedback signals (follow-up questions = dissatisfaction) AND offline metrics (relevancy, accuracy, faithfulness).",
        "bm25": "Retrieval: Partial (2/5 relevant - two \"Measuring and Optimizing Context\" chunks and \"Introduction to RAG Evaluation\"; \"Use Cases for RAG\" and \"Context Engineering with Many Tools\" are tangential). Generation: Good - well-structured, lists concrete criteria (relevance, clarity, completeness, conciseness, perspective) plus the golden-dataset concept, but only covers the offline-metrics perspective.",
        "hybrid": "Retrieval: Good (4/5 relevant - two \"Measuring and Optimizing Context\" and two \"RAG Evaluation Metrics\" chunks). Generation: Good - covers the online user-feedback signal (follow-up questions) plus qualitative metrics (length, clarity, multiple perspectives), but doesn't use the relevancy/accuracy/faithfulness framing semantic does.",
        "winner": "Semantic",
        "why": "With OpenAI embeddings, semantic retrieval alone now surfaces enough chunks to combine both the online (user-feedback/follow-up-questions) and offline (relevancy/accuracy/faithfulness metrics) evaluation perspectives in a single answer - previously this required hybrid's merge of semantic + BM25 results. Hybrid still produces a good answer combining online feedback with qualitative metrics, but doesn't reach the relevancy/accuracy/faithfulness framing; BM25 covers only the offline-criteria perspective.",
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
