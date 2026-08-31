from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from support_pilot.api.routes import router
from support_pilot.config import get_settings
from support_pilot.domain.errors import DomainError
from support_pilot.infrastructure.database import get_engine
from support_pilot.telemetry import configure_telemetry


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")

    @app.exception_handler(DomainError)
    async def handle_domain_error(_request: Request, error: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": str(error)}},
        )

    app.include_router(router)
    configure_telemetry(app, get_engine(), settings)
    return app


app = create_app()
