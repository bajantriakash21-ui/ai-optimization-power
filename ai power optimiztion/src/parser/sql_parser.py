"""SQL query parser using sqlglot."""

import re
from typing import Any

import sqlglot
from sqlglot import exp

from src.models.schemas import ParsedQuery


class SQLParser:
    """Parses SQL queries into structured metadata for analysis."""

    DIALECT_MAP = {
        "postgres": "postgres",
        "postgresql": "postgres",
        "mysql": "mysql",
        "mariadb": "mysql",
        "sqlite": "sqlite",
        "mssql": "tsql",
        "sqlserver": "tsql",
        "oracle": "oracle",
        "bigquery": "bigquery",
        "snowflake": "snowflake",
    }

    def parse(self, query: str, dialect: str = "postgres") -> ParsedQuery:
        normalized_dialect = self.DIALECT_MAP.get(dialect.lower(), dialect)
        cleaned = query.strip().rstrip(";")

        try:
            parsed = sqlglot.parse_one(cleaned, read=normalized_dialect)
        except Exception:
            parsed = sqlglot.parse_one(cleaned, read="postgres")

        query_type = self._get_query_type(parsed)
        tables = self._extract_tables(parsed)
        columns = self._extract_columns(parsed)
        where_columns = self._extract_where_columns(parsed)
        join_columns = self._extract_join_columns(parsed)
        order_by_columns = self._extract_order_by_columns(parsed)
        group_by_columns = self._extract_group_by_columns(parsed)

        return ParsedQuery(
            query_type=query_type,
            tables=tables,
            columns=columns,
            where_columns=where_columns,
            join_columns=join_columns,
            order_by_columns=order_by_columns,
            group_by_columns=group_by_columns,
            has_subquery=self._has_subquery(parsed),
            has_distinct=bool(parsed.find(exp.Distinct)),
            has_limit=bool(parsed.find(exp.Limit)),
            join_count=len(list(parsed.find_all(exp.Join))),
            raw_query=cleaned,
        )

    def _get_query_type(self, parsed: exp.Expression) -> str:
        if isinstance(parsed, exp.Select):
            return "SELECT"
        if isinstance(parsed, exp.Insert):
            return "INSERT"
        if isinstance(parsed, exp.Update):
            return "UPDATE"
        if isinstance(parsed, exp.Delete):
            return "DELETE"
        return parsed.__class__.__name__.upper()

    def _extract_tables(self, parsed: exp.Expression) -> list[str]:
        tables: list[str] = []
        for table in parsed.find_all(exp.Table):
            name = table.name
            if name and name not in tables:
                tables.append(name)
        return tables

    def _extract_columns(self, parsed: exp.Expression) -> list[str]:
        columns: list[str] = []
        select = parsed.find(exp.Select)
        if not select:
            return columns

        for expr in select.expressions:
            if isinstance(expr, exp.Star):
                columns.append("*")
            elif isinstance(expr, exp.Column):
                col = expr.name
                if col and col not in columns:
                    columns.append(col)
            elif hasattr(expr, "alias") and expr.alias:
                columns.append(expr.alias)
        return columns

    def _extract_where_columns(self, parsed: exp.Expression) -> list[str]:
        columns: list[str] = []
        where = parsed.find(exp.Where)
        if where:
            for col in where.find_all(exp.Column):
                if col.name and col.name not in columns:
                    columns.append(col.name)
        return columns

    def _extract_join_columns(self, parsed: exp.Expression) -> list[str]:
        columns: list[str] = []
        for join in parsed.find_all(exp.Join):
            on = join.args.get("on")
            if on:
                for col in on.find_all(exp.Column):
                    if col.name and col.name not in columns:
                        columns.append(col.name)
        return columns

    def _extract_order_by_columns(self, parsed: exp.Expression) -> list[str]:
        columns: list[str] = []
        order = parsed.find(exp.Order)
        if order:
            for col in order.find_all(exp.Column):
                if col.name and col.name not in columns:
                    columns.append(col.name)
        return columns

    def _extract_group_by_columns(self, parsed: exp.Expression) -> list[str]:
        columns: list[str] = []
        group = parsed.find(exp.Group)
        if group:
            for col in group.find_all(exp.Column):
                if col.name and col.name not in columns:
                    columns.append(col.name)
        return columns

    def _has_subquery(self, parsed: exp.Expression) -> bool:
        for sub in parsed.find_all(exp.Subquery):
            if sub != parsed:
                return True
        return bool(parsed.find(exp.Exists) or parsed.find(exp.In) and parsed.find(exp.Select))

    def get_ast_summary(self, query: str, dialect: str = "postgres") -> dict[str, Any]:
        """Return a lightweight AST summary for AI context."""
        parsed_query = self.parse(query, dialect)
        return parsed_query.model_dump()

    @staticmethod
    def has_select_star(query: str) -> bool:
        return bool(re.search(r"SELECT\s+\*", query, re.IGNORECASE))

    @staticmethod
    def has_leading_wildcard_like(query: str) -> list[str]:
        patterns = re.findall(r"LIKE\s+['\"]%[^'\"]*['\"]", query, re.IGNORECASE)
        return patterns

    @staticmethod
    def has_offset_pagination(query: str) -> bool:
        return bool(re.search(r"\bOFFSET\s+\d+", query, re.IGNORECASE))

    @staticmethod
    def has_not_in_subquery(query: str) -> bool:
        return bool(re.search(r"NOT\s+IN\s*\(\s*SELECT", query, re.IGNORECASE))
