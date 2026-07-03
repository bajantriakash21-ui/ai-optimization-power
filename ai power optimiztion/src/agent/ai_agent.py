"""AI-powered analysis using OpenAI."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from src.config import settings
from src.models.schemas import (
    AnalysisResponse,
    Bottleneck,
    IndexRecommendation,
    QueryOptimization,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert database performance engineer.
Analyze SQL queries for bottlenecks, indexing strategies, and rewrites.
Be specific, actionable, and concise. Focus on impact before deployment.
Respond only with valid JSON matching the requested schema."""


class AIAgent:
    """Optional LLM layer for richer explanations and recommendations."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self._client: OpenAI | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def client(self) -> OpenAI:
        if not self.api_key:
            raise RuntimeError("OpenAI API key not configured")
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def enrich_analysis(
        self,
        query: str,
        dialect: str,
        analysis: AnalysisResponse,
    ) -> tuple[str | None, list[str] | None, str | None]:
        """Return (summary, recommendations, optimized_query) from AI."""
        if not self.enabled:
            return None, None, None

        context = self._build_context(query, dialect, analysis)
        prompt = f"""Analyze this SQL query and the rule-based findings below.

SQL ({dialect}):
```sql
{query}
```

Rule-based analysis:
{json.dumps(context, indent=2)}

Return JSON with exactly these keys:
- "summary": string (2-4 sentences executive summary)
- "recommendations": array of 3-6 specific actionable strings
- "optimized_query": string or null (rewritten query if meaningful improvements exist)
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=1500,
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            return (
                data.get("summary"),
                data.get("recommendations"),
                data.get("optimized_query"),
            )
        except Exception as exc:
            logger.warning("AI enrichment failed: %s", exc)
            return self._fallback_summary(analysis), self._fallback_recommendations(analysis), None

    def _build_context(
        self,
        query: str,
        dialect: str,
        analysis: AnalysisResponse,
    ) -> dict[str, Any]:
        return {
            "dialect": dialect,
            "parsed": analysis.parsed.model_dump(),
            "bottlenecks": [b.model_dump() for b in analysis.bottlenecks],
            "index_recommendations": [i.model_dump() for i in analysis.index_recommendations],
            "optimizations": [o.model_dump() for o in analysis.optimizations],
            "performance": analysis.performance.model_dump(),
        }

    def _fallback_summary(self, analysis: AnalysisResponse) -> str:
        count = len(analysis.bottlenecks)
        risk = analysis.performance.risk_level.value
        if count == 0:
            return "No major performance anti-patterns detected. Query structure looks reasonable."
        return (
            f"Found {count} potential bottleneck(s) with {risk} deployment risk. "
            f"Complexity score: {analysis.performance.complexity_score}/100. "
            "Review index recommendations and query rewrites before deploying."
        )

    def _fallback_recommendations(self, analysis: AnalysisResponse) -> list[str]:
        recs: list[str] = []
        for idx in analysis.index_recommendations[:3]:
            recs.append(f"Create index on {idx.table}({', '.join(idx.columns)}): {idx.reason}")
        for opt in analysis.optimizations[:3]:
            recs.append(f"{opt.category.title()}: {opt.explanation}")
        for b in analysis.bottlenecks[:2]:
            recs.append(b.suggestion)
        return recs[:6]
