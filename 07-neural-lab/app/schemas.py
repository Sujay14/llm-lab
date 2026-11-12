from pydantic import BaseModel, Field

class RunRequest(BaseModel):
    task: str = Field(min_length=2, max_length=40)
    text: str = Field(min_length=1, max_length=24000)
    context: str = Field(default="", max_length=30000)
    target_language: str = Field(default="Spanish", max_length=80)
    style: str = Field(default="clear and natural", max_length=120)
    model: str = Field(default="", max_length=120)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    custom_system: str = Field(default="", max_length=5000)
    max_tokens: int = Field(default=700, ge=1, le=4096)
