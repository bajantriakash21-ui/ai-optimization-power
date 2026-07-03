from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class BottleneckType(str, Enum):
    FULL_TABLE_SCAN = "full_table_scan"
    SELECT_STAR = "select_star"
    MISSING_WHERE = "missing_where"
    FUNCTION_ON_COLUMN = "function_on_column"
    LEADING_WILDCARD_LIKE = "leading_wildcard_like"
    OR_CONDITION = "or_condition"
    CARTESIAN_JOIN = "cartesian_join"
    CORRELATED_SUBQUERY = "correlated_subquery"
    ORDER_BY_NO_LIMIT = "order_by_no_limit"
    DISTINCT_OVERUSE = "distinct_overuse"
    NOT_IN_SUBQUERY = "not_in_subquery"
    IMPLICIT_CAST = "implicit_cast"
    OFFSET_PAGINATION = "offset_pagination"
    UNBOUNDED_JOIN = "unbounded_join"


class Bottleneck(BaseModel):
    type: BottleneckType
    severity: Severity
    title: str
    description: str
    location: str | None = None
    suggestion: str


class IndexRecommendation(BaseModel):
    table: str
    columns: list[str]
    index_type: str = "btree"
    reason: str
    estimated_impact: str
    create_statement: str
    priority: int = Field(ge=1, le=5)


class QueryOptimization(BaseModel):
    category: str
    original_fragment: str | None = None
    optimized_fragment: str | None = None
    explanation: str
    impact: str


class PerformancePrediction(BaseModel):
    complexity_score: float = Field(ge=0, le=100)
    estimated_relative_cost: str
    risk_level: Severity
    factors: list[str]
    before_score: float
    after_score: float | None = None
    improvement_percent: float | None = None


class ParsedQuery(BaseModel):
    query_type: str
    tables: list[str]
    columns: list[str]
    where_columns: list[str]
    join_columns: list[str]
    order_by_columns: list[str]
    group_by_columns: list[str]
    has_subquery: bool
    has_distinct: bool
    has_limit: bool
    join_count: int
    raw_query: str


class AnalysisRequest(BaseModel):
    query: str
    dialect: str = "postgres"
    table_sizes: dict[str, int] | None = None
    existing_indexes: dict[str, list[list[str]]] | None = None
    use_ai: bool = True


class AnalysisResponse(BaseModel):
    parsed: ParsedQuery
    bottlenecks: list[Bottleneck]
    index_recommendations: list[IndexRecommendation]
    optimizations: list[QueryOptimization]
    performance: PerformancePrediction
    optimized_query: str | None = None
    ai_summary: str | None = None
    ai_recommendations: list[str] | None = None


class HealthResponse(BaseModel):
    status: str
    ai_enabled: bool
    version: str = "1.0.0"
