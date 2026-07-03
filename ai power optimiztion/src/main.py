"""FastAPI application for the query optimizer agent."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src import __version__
from src.agent.orchestrator import QueryAnalysisAgent
from src.config import settings
from src.models.schemas import AnalysisRequest, AnalysisResponse, HealthResponse

agent = QueryAnalysisAgent()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(
    title="AI Database Query Optimizer",
    description=(
        "Analyzes SQL queries, detects bottlenecks, recommends indexes and "
        "optimizations, and predicts performance impact before deployment."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    

    return {
        "message": "AI Database Query Optimizer API is running",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        ai_enabled=settings.ai_enabled,
        version=__version__,
    )


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_query(request: AnalysisRequest) -> AnalysisResponse:
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        return agent.analyze(request)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Analysis failed: {exc}") from exc


@app.post("/api/v1/analyze", response_model=AnalysisResponse)
async def analyze_query_v1(request: AnalysisRequest) -> AnalysisResponse:
    return await analyze_query(request)
