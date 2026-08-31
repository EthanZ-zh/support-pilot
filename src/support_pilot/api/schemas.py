from pydantic import BaseModel, ConfigDict


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(StrictSchema):
    code: str
    message: str


class ErrorResponse(StrictSchema):
    error: ErrorBody
