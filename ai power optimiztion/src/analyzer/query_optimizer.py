"""Query rewrite and optimization recommendations."""

import re

from src.models.schemas import (
    Bottleneck,
    BottleneckType,
    ParsedQuery,
    QueryOptimization,
)


class QueryOptimizer:
    """Maps detected bottlenecks to actionable query optimizations."""

    _BOTTLENECK_OPTIMIZATIONS: dict[BottleneckType, tuple[str, str, str]] = {
        BottleneckType.SELECT_STAR: (
            "projection",
            "List only required columns instead of SELECT *",
            "Medium — reduces I/O and memory by 30–70% depending on table width",
        ),
        BottleneckType.MISSING_WHERE: (
            "filter",
            "Add a WHERE clause to filter rows before scanning",
            "High — can reduce rows scanned by orders of magnitude",
        ),
        BottleneckType.FUNCTION_ON_COLUMN: (
            "predicate",
            "Move the function to the comparison value, or add a functional index",
            "High — restores index seek instead of full scan",
        ),
        BottleneckType.LEADING_WILDCARD_LIKE: (
            "predicate",
            "Use trailing wildcard only, full-text search, or trigram/GIN index",
            "High — enables index-backed search",
        ),
        BottleneckType.OR_CONDITION: (
            "predicate",
            "Split OR into UNION ALL of indexed queries, or use IN for same-column OR",
            "Medium — allows index usage per branch",
        ),
        BottleneckType.CARTESIAN_JOIN: (
            "join",
            "Add explicit JOIN ... ON conditions linking related tables",
            "Critical — eliminates exponential row explosion",
        ),
        BottleneckType.CORRELATED_SUBQUERY: (
            "rewrite",
            "Rewrite correlated subquery as JOIN or EXISTS with proper indexing",
            "High — changes O(n²) to O(n) execution pattern",
        ),
        BottleneckType.ORDER_BY_NO_LIMIT: (
            "sort",
            "Add LIMIT for top-N queries, or index ORDER BY columns",
            "Medium — avoids sorting entire result set",
        ),
        BottleneckType.DISTINCT_OVERUSE: (
            "aggregation",
            "Fix JOIN logic or replace DISTINCT with GROUP BY",
            "Low — removes unnecessary deduplication pass",
        ),
        BottleneckType.NOT_IN_SUBQUERY: (
            "rewrite",
            "Replace NOT IN with NOT EXISTS for NULL safety and better plans",
            "High — avoids NULL trap and often faster execution",
        ),
        BottleneckType.OFFSET_PAGINATION: (
            "pagination",
            "Use keyset pagination: WHERE id > :last_id ORDER BY id LIMIT N",
            "Medium — O(1) page access vs O(offset) scan",
        ),
        BottleneckType.FULL_TABLE_SCAN: (
            "index",
            "Add indexes on filter/join columns (see index recommendations)",
            "High — converts sequential scan to index seek",
        ),
        BottleneckType.UNBOUNDED_JOIN: (
            "join",
            "Ensure all JOINs have selective ON predicates and supporting indexes",
            "High — reduces intermediate join cardinality",
        ),
        BottleneckType.IMPLICIT_CAST: (
            "predicate",
            "Match column and literal types; avoid implicit casts on indexed columns",
            "Medium — preserves index usage",
        ),
    }

    def recommend(
        self,
        parsed: ParsedQuery,
        bottlenecks: list[Bottleneck],
    ) -> list[QueryOptimization]:
        optimizations: list[QueryOptimization] = []
        seen: set[str] = set()

        for bottleneck in bottlenecks:
            mapping = self._BOTTLENECK_OPTIMIZATIONS.get(bottleneck.type)
            if not mapping:
                continue

            category, explanation, impact = mapping
            key = f"{bottleneck.type.value}:{explanation}"
            if key in seen:
                continue
            seen.add(key)

            optimizations.append(
                QueryOptimization(
                    category=category,
                    original_fragment=bottleneck.location,
                    optimized_fragment=self._suggest_rewrite(bottleneck, parsed),
                    explanation=explanation,
                    impact=impact,
                )
            )

        optimizations.extend(self._structural_optimizations(parsed))
        return optimizations

    def suggest_optimized_query(
        self,
        parsed: ParsedQuery,
        bottlenecks: list[Bottleneck],
    ) -> str | None:
        """Apply safe, mechanical rewrites where possible."""
        bottleneck_types = {b.type for b in bottlenecks}
        query = parsed.raw_query

        if BottleneckType.NOT_IN_SUBQUERY in bottleneck_types:
            return None

        if (
            BottleneckType.SELECT_STAR in bottleneck_types
            and len(parsed.tables) == 1
            and not parsed.has_subquery
        ):
            hinted = self._hint_select_columns(query, parsed.tables[0])
            if hinted != query:
                return hinted

        return None

    def _suggest_rewrite(self, bottleneck: Bottleneck, parsed: ParsedQuery) -> str | None:
        if bottleneck.type == BottleneckType.NOT_IN_SUBQUERY:
            return (
                "NOT EXISTS (SELECT 1 FROM other_table o "
                "WHERE o.id = main.id)"
            )
        if bottleneck.type == BottleneckType.OFFSET_PAGINATION:
            return "WHERE created_at < :cursor ORDER BY created_at DESC LIMIT 20"
        if bottleneck.type == BottleneckType.SELECT_STAR and parsed.tables:
            return f"SELECT col1, col2 FROM {parsed.tables[0]}"
        if bottleneck.type == BottleneckType.FUNCTION_ON_COLUMN:
            return "WHERE email = LOWER(:input)  -- compare against bound value"
        return bottleneck.suggestion

    def _structural_optimizations(self, parsed: ParsedQuery) -> list[QueryOptimization]:
        opts: list[QueryOptimization] = []
        upper = parsed.raw_query.upper()

        if parsed.has_subquery and "WITH" not in upper:
            opts.append(
                QueryOptimization(
                    category="structure",
                    explanation="Materialize intermediate results with CTEs (WITH) for plan stability.",
                    impact="Low — improves readability and can help the optimizer",
                )
            )

        if parsed.join_count > 3:
            opts.append(
                QueryOptimization(
                    category="join",
                    explanation="Consider denormalizing or pre-aggregating for queries with many JOINs.",
                    impact="Medium — reduces join fan-out and memory pressure",
                )
            )

        return opts

    def _hint_select_columns(self, query: str, table: str) -> str:
        return re.sub(
            r"SELECT\s+\*",
            f"SELECT id, /* add required columns */ created_at FROM {table}",
            query,
            count=1,
            flags=re.IGNORECASE,
        )
