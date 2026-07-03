"""Detects performance bottlenecks in SQL queries."""

import re

import sqlglot
from sqlglot import exp

from src.models.schemas import (
    Bottleneck,
    BottleneckType,
    ParsedQuery,
    Severity,
)
from src.parser.sql_parser import SQLParser


class BottleneckDetector:
    """Rule-based detection of common SQL performance anti-patterns."""

    LARGE_TABLE_THRESHOLD = 100_000

    def detect(
        self,
        parsed: ParsedQuery,
        table_sizes: dict[str, int] | None = None,
        existing_indexes: dict[str, list[list[str]]] | None = None,
    ) -> list[Bottleneck]:
        table_sizes = table_sizes or {}
        existing_indexes = existing_indexes or {}
        bottlenecks: list[Bottleneck] = []

        bottlenecks.extend(self._check_select_star(parsed))
        bottlenecks.extend(self._check_missing_where(parsed, table_sizes))
        bottlenecks.extend(self._check_function_on_column(parsed.raw_query))
        bottlenecks.extend(self._check_leading_wildcard(parsed.raw_query))
        bottlenecks.extend(self._check_or_conditions(parsed.raw_query))
        bottlenecks.extend(self._check_cartesian_join(parsed))
        bottlenecks.extend(self._check_correlated_subquery(parsed.raw_query))
        bottlenecks.extend(self._check_order_by_no_limit(parsed))
        bottlenecks.extend(self._check_distinct_overuse(parsed))
        bottlenecks.extend(self._check_not_in_subquery(parsed.raw_query))
        bottlenecks.extend(self._check_offset_pagination(parsed.raw_query))
        bottlenecks.extend(self._check_missing_indexes(parsed, existing_indexes, table_sizes))

        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        bottlenecks.sort(key=lambda b: severity_order[b.severity])
        return bottlenecks

    def _check_select_star(self, parsed: ParsedQuery) -> list[Bottleneck]:
        if "*" in parsed.columns or SQLParser.has_select_star(parsed.raw_query):
            return [
                Bottleneck(
                    type=BottleneckType.SELECT_STAR,
                    severity=Severity.MEDIUM,
                    title="SELECT * retrieves all columns",
                    description="Using SELECT * forces the database to read every column, increasing I/O and memory usage.",
                    suggestion="Specify only the columns you need: SELECT col1, col2, col3 FROM table",
                )
            ]
        return []

    def _check_missing_where(
        self, parsed: ParsedQuery, table_sizes: dict[str, int]
    ) -> list[Bottleneck]:
        if parsed.query_type != "SELECT":
            return []

        has_where = bool(re.search(r"\bWHERE\b", parsed.raw_query, re.IGNORECASE))
        if has_where:
            return []

        large_tables = [
            t for t in parsed.tables if table_sizes.get(t, 50_000) >= self.LARGE_TABLE_THRESHOLD
        ]
        if not large_tables and len(parsed.tables) <= 1:
            large_tables = parsed.tables

        if large_tables:
            return [
                Bottleneck(
                    type=BottleneckType.MISSING_WHERE,
                    severity=Severity.HIGH,
                    title="No WHERE clause on large table scan",
                    description=f"Query scans entire table(s): {', '.join(large_tables)} without filtering.",
                    suggestion="Add a WHERE clause to filter rows early, reducing data read from disk.",
                )
            ]
        return []

    def _check_function_on_column(self, query: str) -> list[Bottleneck]:
        patterns = [
            (r"WHERE\s+\w+\(\w+\.", "function wrapped column in WHERE"),
            (r"WHERE\s+LOWER\(", "LOWER() on column prevents index use"),
            (r"WHERE\s+UPPER\(", "UPPER() on column prevents index use"),
            (r"WHERE\s+DATE\(", "DATE() on column prevents index use"),
            (r"WHERE\s+YEAR\(", "YEAR() on column prevents index use"),
            (r"WHERE\s+SUBSTRING\(", "SUBSTRING() on column prevents index use"),
            (r"WHERE\s+TRIM\(", "TRIM() on column prevents index use"),
        ]
        found = []
        for pattern, desc in patterns:
            if re.search(pattern, query, re.IGNORECASE):
                found.append(desc)

        if found:
            return [
                Bottleneck(
                    type=BottleneckType.FUNCTION_ON_COLUMN,
                    severity=Severity.HIGH,
                    title="Function applied to indexed column",
                    description=f"Detected: {', '.join(found)}. Wrapping columns in functions prevents index usage.",
                    suggestion="Rewrite to compare against transformed values, or use functional/expression indexes.",
                )
            ]
        return []

    def _check_leading_wildcard(self, query: str) -> list[Bottleneck]:
        patterns = SQLParser.has_leading_wildcard_like(query)
        if patterns:
            return [
                Bottleneck(
                    type=BottleneckType.LEADING_WILDCARD_LIKE,
                    severity=Severity.HIGH,
                    title="LIKE pattern with leading wildcard",
                    description=f"Pattern {patterns[0]} cannot use a standard B-tree index.",
                    location=patterns[0],
                    suggestion="Use trailing wildcard only (LIKE 'value%'), full-text search, or trigram indexes.",
                )
            ]
        return []

    def _check_or_conditions(self, query: str) -> list[Bottleneck]:
        where_match = re.search(
            r"WHERE\s+(.+?)(?:GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING|$)",
            query,
            re.IGNORECASE | re.DOTALL,
        )
        if where_match:
            where_clause = where_match.group(1)
            or_count = len(re.findall(r"\bOR\b", where_clause, re.IGNORECASE))
            if or_count >= 2:
                return [
                    Bottleneck(
                        type=BottleneckType.OR_CONDITION,
                        severity=Severity.MEDIUM,
                        title="Multiple OR conditions in WHERE clause",
                        description=f"Found {or_count} OR conditions which often prevent efficient index usage.",
                        suggestion="Consider UNION ALL of separate indexed queries, or rewrite using IN (...).",
                    )
                ]
        return []

    def _check_cartesian_join(self, parsed: ParsedQuery) -> list[Bottleneck]:
        if parsed.join_count == 0 and len(parsed.tables) > 1:
            return [
                Bottleneck(
                    type=BottleneckType.CARTESIAN_JOIN,
                    severity=Severity.CRITICAL,
                    title="Potential Cartesian product (cross join)",
                    description=f"Multiple tables ({', '.join(parsed.tables)}) without explicit JOIN conditions.",
                    suggestion="Add explicit JOIN ... ON conditions to link tables properly.",
                )
            ]

        try:
            ast = sqlglot.parse_one(parsed.raw_query)
            for join in ast.find_all(exp.Join):
                if not join.args.get("on") and join.kind != "CROSS":
                    return [
                        Bottleneck(
                            type=BottleneckType.CARTESIAN_JOIN,
                            severity=Severity.CRITICAL,
                            title="JOIN without ON condition",
                            description="A JOIN clause is missing an ON condition, causing a Cartesian product.",
                            suggestion="Add ON clause specifying the relationship between tables.",
                        )
                    ]
        except Exception:
            pass
        return []

    def _check_correlated_subquery(self, query: str) -> list[Bottleneck]:
        if re.search(
            r"WHERE\s+.*\(\s*SELECT\s+.*WHERE\s+.*\b\w+\.\w+\s*=",
            query,
            re.IGNORECASE | re.DOTALL,
        ):
            return [
                Bottleneck(
                    type=BottleneckType.CORRELATED_SUBQUERY,
                    severity=Severity.HIGH,
                    title="Correlated subquery detected",
                    description="Subquery references outer query columns, executing once per outer row.",
                    suggestion="Rewrite as a JOIN or use EXISTS with proper indexing on the correlated column.",
                )
            ]
        return []

    def _check_order_by_no_limit(self, parsed: ParsedQuery) -> list[Bottleneck]:
        if parsed.order_by_columns and not parsed.has_limit:
            return [
                Bottleneck(
                    type=BottleneckType.ORDER_BY_NO_LIMIT,
                    severity=Severity.MEDIUM,
                    title="ORDER BY without LIMIT",
                    description="Sorting entire result set is expensive for large tables.",
                    suggestion="Add LIMIT if you only need top-N results, or ensure an index covers ORDER BY columns.",
                )
            ]
        return []

    def _check_distinct_overuse(self, parsed: ParsedQuery) -> list[Bottleneck]:
        if parsed.has_distinct and parsed.join_count > 0:
            return [
                Bottleneck(
                    type=BottleneckType.DISTINCT_OVERUSE,
                    severity=Severity.MEDIUM,
                    title="DISTINCT with JOINs may indicate duplicate rows",
                    description="DISTINCT after JOINs often masks a join logic issue and adds sort overhead.",
                    suggestion="Fix JOIN conditions to eliminate duplicates, or use GROUP BY with aggregation.",
                )
            ]
        return []

    def _check_not_in_subquery(self, query: str) -> list[Bottleneck]:
        if SQLParser.has_not_in_subquery(query):
            return [
                Bottleneck(
                    type=BottleneckType.NOT_IN_SUBQUERY,
                    severity=Severity.HIGH,
                    title="NOT IN with subquery",
                    description="NOT IN fails on NULL values and is often slower than NOT EXISTS.",
                    suggestion="Replace with NOT EXISTS (SELECT 1 FROM ... WHERE ...) for better performance and NULL safety.",
                )
            ]
        return []

    def _check_offset_pagination(self, query: str) -> list[Bottleneck]:
        offset_match = re.search(r"OFFSET\s+(\d+)", query, re.IGNORECASE)
        if offset_match:
            offset = int(offset_match.group(1))
            if offset >= 1000:
                return [
                    Bottleneck(
                        type=BottleneckType.OFFSET_PAGINATION,
                        severity=Severity.MEDIUM,
                        title="Large OFFSET pagination",
                        description=f"OFFSET {offset} forces the database to scan and discard {offset} rows.",
                        suggestion="Use keyset/cursor pagination: WHERE id > last_seen_id ORDER BY id LIMIT N.",
                    )
                ]
        return []

    def _check_missing_indexes(
        self,
        parsed: ParsedQuery,
        existing_indexes: dict[str, list[list[str]]],
        table_sizes: dict[str, int],
    ) -> list[Bottleneck]:
        bottlenecks = []
        filter_columns = set(parsed.where_columns + parsed.join_columns)

        for table in parsed.tables:
            table_indexes = existing_indexes.get(table, [])
            indexed_columns = {col for idx in table_indexes for col in idx}
            unindexed = filter_columns - indexed_columns

            size = table_sizes.get(table, 10_000)
            if unindexed and size >= self.LARGE_TABLE_THRESHOLD:
                bottlenecks.append(
                    Bottleneck(
                        type=BottleneckType.FULL_TABLE_SCAN,
                        severity=Severity.HIGH,
                        title=f"Likely full table scan on '{table}'",
                        description=f"Filter/join columns {list(unindexed)} appear unindexed on a large table ({size:,} rows).",
                        suggestion=f"Create an index on {table}({', '.join(sorted(unindexed))}).",
                    )
                )
        return bottlenecks
