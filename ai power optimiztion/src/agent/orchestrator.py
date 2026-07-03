"""Orchestrates the full query analysis pipeline."""

from src.agent.ai_agent import AIAgent
from src.analyzer.bottleneck_detector import BottleneckDetector
from src.analyzer.index_advisor import IndexAdvisor
from src.analyzer.performance_predictor import PerformancePredictor
from src.analyzer.query_optimizer import QueryOptimizer
from src.models.schemas import AnalysisRequest, AnalysisResponse
from src.parser.sql_parser import SQLParser


class QueryAnalysisAgent:
    """Main agent: parse → detect → recommend → predict → optional AI enrich."""

    def __init__(self) -> None:
        self.parser = SQLParser()
        self.detector = BottleneckDetector()
        self.index_advisor = IndexAdvisor()
        self.query_optimizer = QueryOptimizer()
        self.performance_predictor = PerformancePredictor()
        self.ai_agent = AIAgent()

    def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        parsed = self.parser.parse(request.query, request.dialect)

        bottlenecks = self.detector.detect(
            parsed,
            table_sizes=request.table_sizes,
            existing_indexes=request.existing_indexes,
        )

        index_recommendations = self.index_advisor.recommend(
            parsed,
            existing_indexes=request.existing_indexes,
            table_sizes=request.table_sizes,
        )

        optimizations = self.query_optimizer.recommend(parsed, bottlenecks)

        performance = self.performance_predictor.predict(
            parsed,
            bottlenecks,
            index_recommendations,
            optimizations,
            table_sizes=request.table_sizes,
        )

        optimized_query = self.query_optimizer.suggest_optimized_query(parsed, bottlenecks)

        response = AnalysisResponse(
            parsed=parsed,
            bottlenecks=bottlenecks,
            index_recommendations=index_recommendations,
            optimizations=optimizations,
            performance=performance,
            optimized_query=optimized_query,
        )

        if request.use_ai and self.ai_agent.enabled:
            summary, recommendations, ai_query = self.ai_agent.enrich_analysis(
                request.query,
                request.dialect,
                response,
            )
            response.ai_summary = summary
            response.ai_recommendations = recommendations
            if ai_query and not response.optimized_query:
                response.optimized_query = ai_query
        elif request.use_ai:
            response.ai_summary = self.ai_agent._fallback_summary(response)
            response.ai_recommendations = self.ai_agent._fallback_recommendations(response)

        return response
