"""FastAPI Application Entry Point"""
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.api.routes import router
from app.config import HOST, PORT, DEBUG

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AI Chatbot API",
    description="Production-ready FastAPI + LangChain chatbot",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api", tags=["chat"])

# Mount frontend static files
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

    @app.get("/")
    async def root():
        """Serve the chat UI"""
        from fastapi.responses import FileResponse
        return FileResponse(frontend_path / "index.html")


@app.on_event("startup")
async def startup_event():
    """Initialize agent and data analyzers on startup"""
    logger.info("Application starting up...")
    try:
        # Initialize CSV/JSON Q&A agent (loads LLM + data sources)
        from app.llm.agent import get_agent
        agent = get_agent()
        logger.info("✓ CSV/JSON Q&A agent initialized")
        
        # Verify at least one data source is available
        if agent.json_analyzer and agent.json_analyzer.data:
            num_clients = len(agent.json_analyzer.data.clients)
            logger.info(f"✓ JSON data ready: {num_clients} clients in round {agent.json_analyzer.data.round_num}")
        elif agent.csv_analyzer and agent.csv_analyzer.df is not None:
            num_records = len(agent.csv_analyzer.df)
            num_columns = len(agent.csv_analyzer.df.columns)
            logger.info(f"✓ CSV data ready: {num_records} records, {num_columns} columns")
        else:
            logger.warning("⚠ No data source available (JSON and CSV both unavailable)")
        
        logger.info("✓ Chatbot ready - can answer questions about the detection system")
    except Exception as e:
        logger.error(f"✗ Failed to initialize: {str(e)}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Application shutting down...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="info"
    )
