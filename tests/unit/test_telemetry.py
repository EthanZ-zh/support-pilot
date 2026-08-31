from unittest.mock import patch

from fastapi import FastAPI
from sqlalchemy import create_engine

from support_pilot.config import Settings
from support_pilot.telemetry import configure_telemetry


def test_telemetry_is_opt_in_and_does_not_instrument_by_default() -> None:
    app = FastAPI()
    engine = create_engine("sqlite://")

    configured = configure_telemetry(app, engine, Settings(otel_enabled=False))

    assert configured is False
    assert not hasattr(app.state, "telemetry_configured")


def test_enabled_telemetry_wires_fastapi_database_and_otlp_exporter() -> None:
    app = FastAPI()
    engine = create_engine("sqlite://")
    settings = Settings(
        otel_enabled=True,
        otel_service_name="support-pilot-test",
        otel_exporter_otlp_endpoint="http://collector:4318/v1/traces",
    )

    with (
        patch("support_pilot.telemetry.OTLPSpanExporter") as exporter,
        patch("support_pilot.telemetry.BatchSpanProcessor"),
        patch("support_pilot.telemetry.trace.set_tracer_provider"),
        patch("support_pilot.telemetry.FastAPIInstrumentor.instrument_app") as fastapi,
        patch("support_pilot.telemetry.SQLAlchemyInstrumentor.instrument") as database,
    ):
        configured = configure_telemetry(app, engine, settings)

    assert configured is True
    assert app.state.telemetry_configured is True
    exporter.assert_called_once_with(endpoint="http://collector:4318/v1/traces")
    fastapi.assert_called_once()
    database.assert_called_once()
