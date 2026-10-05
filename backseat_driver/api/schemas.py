"""Request and response bodies of the API routes."""

from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    max_scenes: int | None = Field(default=None, gt=0, description="Only process the first N scenes")


class DescribeResponse(BaseModel):
    description: str
    model_name: str
