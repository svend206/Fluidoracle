#!/usr/bin/env python3
"""
search_possessed.py — Search across all possessed documents for specific terms.

Usage:
    python3 search_possessed.py "keyword"
    python3 search_possessed.py "keyword1" "keyword2" --context 300
    python3 search_possessed.py "keyword" --files "*.txt"

Returns: matching passages with source file + character position.
All matching done case-insensitively. Each match includes surrounding context.
"""

import sys
import os
import re
import glob
import argparse

RAW_FETCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw-fetch")

def search_file(filepath, terms, context_chars=250):
    """Search a file for all terms, return list of (term, passage, position) tuples."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        return []

    results = []
    content_lower = content.lower()

    for term in terms:
        term_lower = term.lower()
        start = 0
        while True:
            pos = content_lower.find(term_lower, start)
            if pos == -1:
                break
            # Extract surrounding context
            ctx_start = max(0, pos - context_chars)
            ctx_end = min(len(content), pos + len(term) + context_chars)
            passage = content[ctx_start:ctx_end].strip()
            # Clean up whitespace
            passage = re.sub(r'\n{3,}', '\n\n', passage)
            results.append((term, passage, pos))
            start = pos + len(term)

    return results


def main():
    parser = argparse.ArgumentParser(description='Search possessed documents for terms')
    parser.add_argument('terms', nargs='+', help='Search terms')
    parser.add_argument('--context', type=int, default=250, help='Context chars around match (default: 250)')
    parser.add_argument('--files', type=str, default='*.txt *.md', help='File glob patterns (space-separated)')
    parser.add_argument('--max-per-file', type=int, default=3, help='Max matches per term per file (default: 3)')
    args = parser.parse_args()

    # Collect files
    patterns = args.files.split()
    files = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(RAW_FETCH, pattern)))
    files = sorted(set(files))

    if not files:
        print(f"No files found in {RAW_FETCH}")
        sys.exit(1)

    print(f"Searching {len(files)} files for: {args.terms}\n")
    print("=" * 80)

    total_matches = 0
    for filepath in files:
        filename = os.path.basename(filepath)
        results = search_file(filepath, args.terms, args.context)

        if not results:
            continue

        # Group by term, limit per file
        by_term = {}
        for term, passage, pos in results:
            by_term.setdefault(term, []).append((passage, pos))

        for term, matches in by_term.items():
            limited = matches[:args.max_per_file]
            for passage, pos in limited:
                print(f"\nSOURCE: {filename}")
                print(f"TERM:   '{term}' (at char {pos})")
                print(f"{'─' * 60}")
                print(passage)
                print()
                total_matches += 1

    print("=" * 80)
    print(f"Total matches: {total_matches}")


if __name__ == '__main__':
    main()
