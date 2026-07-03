"""Predicts query performance impact before deployment."""

from src.models.schemas import (
    Bottleneck,
    IndexRecommendation,
    ParsedQuery,
    PerformancePrediction,
    QueryOptimization,
    Severity,
)


class PerformancePredictor:
    """Scores query complexity and estimates relative performance impact."""

    SEVERITY_PENALTY = {
        Severity.CRITICAL: 25,
        Severity.HIGH: 15,
        Severity.MEDIUM: 8,
        Severity.LOW: 3,
        Severity.INFO: 1,
    }

    def predict(
        self,
        parsed: ParsedQuery,
        bottlenecks: list[Bottleneck],
        index_recommendations: list[IndexRecommendation],
        optimizations: list[QueryOptimization],
        table_sizes: dict[str, int] | None = None,
    ) -> PerformancePrediction:
        table_sizes = table_sizes or {}
        factors: list[str] = []
        score = 10.0

        score += parsed.join_count * 5
        if parsed.join_count:
            factors.append(f"{parsed.join_count} table join(s)")

        if parsed.has_subquery:
            score += 10
            factors.append("Contains subquery")

        if parsed.has_distinct:
            score += 5
            factors.append("DISTINCT deduplication")

        total_rows = sum(table_sizes.get(t, 10_000) for t in parsed.tables)
        if total_rows > 1_000_000:
            score += 20
            factors.append(f"Large dataset (~{total_rows:,} total rows)")
        elif total_rows > 100_000:
            score += 10
            factors.append(f"Medium dataset (~{total_rows:,} total rows)")

        for bottleneck in bottlenecks:
            penalty = self.SEVERITY_PENALTY[bottleneck.severity]
            score += penalty
            factors.append(f"{bottleneck.title} ({bottleneck.severity.value})")

        before_score = min(100.0, score)
        risk_level = self._risk_from_score(before_score)

        after_score = before_score
        improvement = 0.0

        if index_recommendations:
            index_gain = min(30, len(index_recommendations) * 8)
            after_score -= index_gain
            factors.append(f"Indexes could reduce cost by ~{index_gain}%")

        if optimizations:
            opt_gain = min(25, len(optimizations) * 5)
            after_score -= opt_gain

        critical_count = sum(1 for b in bottlenecks if b.severity == Severity.CRITICAL)
        if critical_count:
            after_score -= critical_count * 10

        after_score = max(5.0, min(100.0, after_score))
        if after_score < before_score:
            improvement = round((before_score - after_score) / before_score * 100, 1)

        return PerformancePrediction(
            complexity_score=round(before_score, 1),
            estimated_relative_cost=self._cost_label(before_score),
            risk_level=risk_level,
            factors=factors[:12],
            before_score=round(before_score, 1),
            after_score=round(after_score, 1) if improvement else None,
            improvement_percent=improvement if improvement else None,
        )

    def _risk_from_score(self, score: float) -> Severity:
        if score >= 75:
            return Severity.CRITICAL
        if score >= 50:
            return Severity.HIGH
        if score >= 30:
            return Severity.MEDIUM
        if score >= 15:
            return Severity.LOW
        return Severity.INFO

    def _cost_label(self, score: float) -> str:
        if score >= 75:
            return "Very high — likely unacceptable at scale"
        if score >= 50:
            return "High — optimize before production deployment"
        if score >= 30:
            return "Moderate — review under realistic load"
        if score >= 15:
            return "Low — acceptable for most workloads"
        return "Minimal — well-structured query"
