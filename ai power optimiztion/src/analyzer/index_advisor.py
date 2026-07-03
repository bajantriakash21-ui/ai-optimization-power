"""Recommends database indexes based on query patterns."""

from src.models.schemas import IndexRecommendation, ParsedQuery


class IndexAdvisor:
    """Generates index recommendations from parsed query metadata."""

    def recommend(
        self,
        parsed: ParsedQuery,
        existing_indexes: dict[str, list[list[str]]] | None = None,
        table_sizes: dict[str, int] | None = None,
    ) -> list[IndexRecommendation]:
        existing_indexes = existing_indexes or {}
        table_sizes = table_sizes or {}
        recommendations: list[IndexRecommendation] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()

        for table in parsed.tables:
            existing = existing_indexes.get(table, [])
            existing_sets = {tuple(sorted(idx)) for idx in existing}

            # WHERE column indexes
            where_cols = [c for c in parsed.where_columns if c]
            if where_cols:
                rec = self._make_recommendation(
                    table=table,
                    columns=where_cols[:3],
                    reason="Columns used in WHERE clause for row filtering",
                    priority=5 if table_sizes.get(table, 0) > 100_000 else 4,
                    existing_sets=existing_sets,
                    seen=seen,
                )
                if rec:
                    recommendations.append(rec)

            # JOIN column indexes
            join_cols = [c for c in parsed.join_columns if c]
            if join_cols:
                rec = self._make_recommendation(
                    table=table,
                    columns=join_cols[:2],
                    reason="Columns used in JOIN conditions",
                    priority=5,
                    existing_sets=existing_sets,
                    seen=seen,
                )
                if rec:
                    recommendations.append(rec)

            # ORDER BY covering index
            if parsed.order_by_columns:
                composite = list(dict.fromkeys(where_cols + parsed.order_by_columns))[:4]
                rec = self._make_recommendation(
                    table=table,
                    columns=composite,
                    reason="Covering index for WHERE + ORDER BY (avoids sort step)",
                    priority=4,
                    existing_sets=existing_sets,
                    seen=seen,
                )
                if rec:
                    recommendations.append(rec)

            # GROUP BY index
            if parsed.group_by_columns:
                composite = list(dict.fromkeys(parsed.group_by_columns + where_cols))[:4]
                rec = self._make_recommendation(
                    table=table,
                    columns=composite,
                    reason="Index supports GROUP BY aggregation",
                    priority=3,
                    existing_sets=existing_sets,
                    seen=seen,
                )
                if rec:
                    recommendations.append(rec)

        recommendations.sort(key=lambda r: -r.priority)
        return recommendations

    def _make_recommendation(
        self,
        table: str,
        columns: list[str],
        reason: str,
        priority: int,
        existing_sets: set[tuple[str, ...]],
        seen: set[tuple[str, tuple[str, ...]]],
    ) -> IndexRecommendation | None:
        if not columns:
            return None

        key = (table, tuple(columns))
        if key in seen:
            return None
        seen.add(key)

        col_tuple = tuple(sorted(columns))
        if col_tuple in existing_sets:
            return None

        # Check if a prefix of existing index already covers these columns
        for existing in existing_sets:
            if list(existing)[: len(columns)] == sorted(columns):
                return None

        col_list = ", ".join(columns)
        create_stmt = f"CREATE INDEX idx_{table}_{'_'.join(columns)} ON {table} ({col_list});"

        impact = "High — eliminates full table scan" if priority >= 5 else "Medium — reduces sort/hash cost"

        return IndexRecommendation(
            table=table,
            columns=columns,
            reason=reason,
            estimated_impact=impact,
            create_statement=create_stmt,
            priority=priority,
        )
