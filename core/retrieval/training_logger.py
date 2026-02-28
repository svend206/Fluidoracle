"""
Hydraulic Filter Expert — Training Data Logger
==========================================
Captures training data from interactions for future model fine-tuning.

Three types of training data:
  1. Q&A Pairs — good answers validated by the user
  2. Corrections — wrong answers with the correct response
  3. Reasoning Traces — step-by-step problem-solving chains

Exports in three formats simultaneously:
  - OpenAI fine-tuning format (JSONL with messages array)
  - Anthropic format (JSONL with prompt/completion)
  - Generic/Alpaca format (JSONL with instruction/input/output)

Usage:
    py -3.12 training_logger.py --log-qa
    py -3.12 training_logger.py --log-correction
    py -3.12 training_logger.py --log-reasoning
    py -3.12 training_logger.py --export
    py -3.12 training_logger.py --stats
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import TRAINING_DATA_DIR

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
QA_LOG = TRAINING_DATA_DIR / "qa_pairs.jsonl"
CORRECTIONS_LOG = TRAINING_DATA_DIR / "corrections.jsonl"
REASONING_LOG = TRAINING_DATA_DIR / "reasoning_traces.jsonl"

EXPORT_DIR = TRAINING_DATA_DIR / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# Logging Functions
# ===========================================================================

def log_qa_pair():
    """Interactively log a validated Q&A pair."""
    print("\n" + "=" * 60)
    print("LOG Q&A PAIR")
    print("Record a question and its validated correct answer.")
    print("=" * 60 + "\n")

    question = input("Question: ").strip()
    if not question:
        print("Cancelled.")
        return

    answer = input("Answer (validated): ").strip()
    confidence = input("Confidence [HIGH/MEDIUM/LOW]: ").strip().upper() or "MEDIUM"
    sources = input("Sources (comma-separated, optional): ").strip()
    quality = input("Quality reviewed? [y/n]: ").strip().lower()

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "qa_pair",
        "question": question,
        "answer": answer,
        "confidence": confidence,
        "sources": [s.strip() for s in sources.split(",") if s.strip()],
        "quality_reviewed": quality == "y",
    }

    with open(QA_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"\n✓ Q&A pair logged. Total: {_count_lines(QA_LOG)}")


def log_correction():
    """Interactively log a correction (wrong answer → correct answer)."""
    print("\n" + "=" * 60)
    print("LOG CORRECTION")
    print("Record what the agent got wrong and what the correct answer is.")
    print("These are the most valuable training examples.")
    print("=" * 60 + "\n")

    question = input("Original question: ").strip()
    if not question:
        print("Cancelled.")
        return

    wrong = input("Wrong answer (what the agent said): ").strip()
    correct = input("Correct answer: ").strip()
    explanation = input("Why it was wrong (optional): ").strip()
    source = input("Source of correct answer (optional): ").strip()

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "correction",
        "question": question,
        "wrong_answer": wrong,
        "correct_answer": correct,
        "explanation": explanation,
        "source": source,
    }

    with open(CORRECTIONS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"\n✓ Correction logged. Total: {_count_lines(CORRECTIONS_LOG)}")


def log_reasoning_trace():
    """Interactively log a step-by-step reasoning chain."""
    print("\n" + "=" * 60)
    print("LOG REASONING TRACE")
    print("Record a step-by-step problem-solving chain.")
    print("These teach the model HOW to think, not just WHAT to answer.")
    print("=" * 60 + "\n")

    question = input("Problem / question: ").strip()
    if not question:
        print("Cancelled.")
        return

    print("\nEnter reasoning steps (one per line, empty line to finish):")
    steps = []
    while True:
        step = input(f"  Step {len(steps) + 1}: ").strip()
        if not step:
            break
        steps.append(step)

    conclusion = input("Final answer / conclusion: ").strip()

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "reasoning_trace",
        "question": question,
        "steps": steps,
        "conclusion": conclusion,
    }

    with open(REASONING_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"\n✓ Reasoning trace logged. Total: {_count_lines(REASONING_LOG)}")


# ===========================================================================
# Export
# ===========================================================================

def export_training_data():
    """Export all training data in three formats simultaneously."""
    print("\n" + "=" * 60)
    print("EXPORT TRAINING DATA")
    print("=" * 60 + "\n")

    all_entries = []

    # Load all entries
    for log_path in [QA_LOG, CORRECTIONS_LOG, REASONING_LOG]:
        if log_path.exists():
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        all_entries.append(json.loads(line))

    if not all_entries:
        print("No training data to export yet.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    openai_path = EXPORT_DIR / f"openai_{timestamp}.jsonl"
    anthropic_path = EXPORT_DIR / f"anthropic_{timestamp}.jsonl"
    generic_path = EXPORT_DIR / f"generic_{timestamp}.jsonl"

    openai_entries = []
    anthropic_entries = []
    generic_entries = []

    system_msg = (
        "You are a world-class expert on industrial hydraulic filters, atomization, "
        "and spray applications. You provide accurate, well-sourced answers "
        "grounded in engineering principles and empirical data."
    )

    for entry in all_entries:
        if entry["type"] == "qa_pair":
            q = entry["question"]
            a = entry["answer"]
        elif entry["type"] == "correction":
            q = entry["question"]
            a = entry["correct_answer"]
        elif entry["type"] == "reasoning_trace":
            q = entry["question"]
            steps_text = "\n".join(f"Step {i+1}: {s}" for i, s in enumerate(entry["steps"]))
            a = f"{steps_text}\n\nConclusion: {entry['conclusion']}"
        else:
            continue

        # OpenAI format
        openai_entries.append({
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": q},
                {"role": "assistant", "content": a},
            ]
        })

        # Anthropic format
        anthropic_entries.append({
            "prompt": f"\n\nHuman: {q}\n\nAssistant:",
            "completion": f" {a}",
        })

        # Generic / Alpaca format
        generic_entries.append({
            "instruction": q,
            "input": "",
            "output": a,
        })

    # Write files
    for path, entries in [(openai_path, openai_entries), (anthropic_path, anthropic_entries), (generic_path, generic_entries)]:
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    print(f"Exported {len(openai_entries)} training examples:")
    print(f"  OpenAI format:    {openai_path}")
    print(f"  Anthropic format: {anthropic_path}")
    print(f"  Generic format:   {generic_path}")


# ===========================================================================
# Stats
# ===========================================================================

def show_stats():
    """Show training data accumulation stats."""
    print("\n" + "=" * 60)
    print("TRAINING DATA STATS")
    print("=" * 60 + "\n")

    qa_count = _count_lines(QA_LOG)
    correction_count = _count_lines(CORRECTIONS_LOG)
    reasoning_count = _count_lines(REASONING_LOG)
    total = qa_count + correction_count + reasoning_count

    print(f"  Q&A pairs:         {qa_count}")
    print(f"  Corrections:       {correction_count}")
    print(f"  Reasoning traces:  {reasoning_count}")
    print(f"  ─────────────────────────")
    print(f"  Total examples:    {total}")

    if total > 0:
        pct = total / 500 * 100
        print(f"\n  Progress to fine-tuning threshold (500): {pct:.0f}%")
        bar_len = 40
        filled = int(bar_len * min(pct, 100) / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  [{bar}] {total}/500")
    else:
        print("\n  No training data yet. Start by logging Q&A pairs from your sessions.")

    # Check for exports
    if EXPORT_DIR.exists():
        exports = list(EXPORT_DIR.glob("*.jsonl"))
        if exports:
            print(f"\n  Exports: {len(exports)} files in {EXPORT_DIR}")

    print()


# ===========================================================================
# Helpers
# ===========================================================================

def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hydraulic Filter Expert — Training Data Logger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py -3.12 training_logger.py --log-qa          Log a validated Q&A pair
  py -3.12 training_logger.py --log-correction   Log a correction
  py -3.12 training_logger.py --log-reasoning    Log a reasoning trace
  py -3.12 training_logger.py --export           Export in all formats
  py -3.12 training_logger.py --stats            Show accumulation stats
        """,
    )
    parser.add_argument("--log-qa", action="store_true", help="Log a validated Q&A pair")
    parser.add_argument("--log-correction", action="store_true", help="Log a correction")
    parser.add_argument("--log-reasoning", action="store_true", help="Log a reasoning trace")
    parser.add_argument("--export", action="store_true", help="Export training data in all formats")
    parser.add_argument("--stats", action="store_true", help="Show training data stats")

    args = parser.parse_args()

    if args.log_qa:
        log_qa_pair()
    elif args.log_correction:
        log_correction()
    elif args.log_reasoning:
        log_reasoning_trace()
    elif args.export:
        export_training_data()
    elif args.stats:
        show_stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
