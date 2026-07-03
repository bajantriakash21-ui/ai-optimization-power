"""Command-line interface for query analysis."""

import argparse
import json
import sys
from pathlib import Path

from src.agent.orchestrator import QueryAnalysisAgent
from src.models.schemas import AnalysisRequest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI-powered database query optimizer",
    )
    parser.add_argument("query", nargs="?", help="SQL query string to analyze")
    parser.add_argument("-f", "--file", help="Read SQL from a file")
    parser.add_argument(
        "-d", "--dialect", default="postgres", help="SQL dialect (default: postgres)"
    )
    parser.add_argument(
        "--no-ai", action="store_true", help="Skip AI enrichment (rule-based only)"
    )
    parser.add_argument(
        "--json", action="store_true", dest="output_json", help="Output raw JSON"
    )
    parser.add_argument(
        "--table-sizes",
        help='JSON map of table row counts, e.g. \'{"orders": 500000}\'',
    )
    args = parser.parse_args()

    query = args.query
    if args.file:
        query = Path(args.file).read_text(encoding="utf-8")
    if not query:
        parser.error("Provide a query string or --file")

    table_sizes = None
    if args.table_sizes:
        table_sizes = json.loads(args.table_sizes)

    agent = QueryAnalysisAgent()
    result = agent.analyze(
        AnalysisRequest(
            query=query,
            dialect=args.dialect,
            table_sizes=table_sizes,
            use_ai=not args.no_ai,
        )
    )

    if args.output_json:
        print(result.model_dump_json(indent=2))
        return

    _print_report(result)


def _print_report(result) -> None:
    print("=" * 60)
    print("QUERY ANALYSIS REPORT")
    print("=" * 60)

    print(f"\nQuery type: {result.parsed.query_type}")
    print(f"Tables: {', '.join(result.parsed.tables) or 'none'}")
    print(f"Joins: {result.parsed.join_count}")

    perf = result.performance
    print(f"\n--- Performance Prediction ---")
    print(f"Complexity score: {perf.complexity_score}/100")
    print(f"Risk level: {perf.risk_level.value}")
    print(f"Estimated cost: {perf.estimated_relative_cost}")
    if perf.improvement_percent:
        print(
            f"Projected improvement: {perf.improvement_percent}% "
            f"(score {perf.before_score} -> {perf.after_score})"
        )

    if result.bottlenecks:
        print(f"\n--- Bottlenecks ({len(result.bottlenecks)}) ---")
        for i, b in enumerate(result.bottlenecks, 1):
            print(f"\n{i}. [{b.severity.value.upper()}] {b.title}")
            print(f"   {b.description}")
            print(f"   -> {b.suggestion}")

    if result.index_recommendations:
        print(f"\n--- Index Recommendations ({len(result.index_recommendations)}) ---")
        for i, idx in enumerate(result.index_recommendations, 1):
            print(f"\n{i}. {idx.create_statement}")
            print(f"   Reason: {idx.reason}")
            print(f"   Impact: {idx.estimated_impact}")

    if result.optimizations:
        print(f"\n--- Query Optimizations ({len(result.optimizations)}) ---")
        for i, opt in enumerate(result.optimizations, 1):
            print(f"\n{i}. [{opt.category}] {opt.explanation}")
            print(f"   Impact: {opt.impact}")
            if opt.optimized_fragment:
                print(f"   Suggested: {opt.optimized_fragment}")

    if result.optimized_query:
        print(f"\n--- Suggested Optimized Query ---")
        print(result.optimized_query)

    if result.ai_summary:
        print(f"\n--- AI Summary ---")
        print(result.ai_summary)

    if result.ai_recommendations:
        print(f"\n--- AI Recommendations ---")
        for i, rec in enumerate(result.ai_recommendations, 1):
            print(f"  {i}. {rec}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
