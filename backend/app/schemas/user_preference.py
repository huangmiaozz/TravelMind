from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserPreferencePayload(BaseModel):
    interests: dict[str, float] = Field(default_factory=dict)
    transport_preferences: dict = Field(default_factory=dict)
    accommodation_preferences: dict = Field(default_factory=dict)
    custom_constraints: dict = Field(default_factory=dict)

    @field_validator("interests")
    @classmethod
    def validate_interest_weights(cls, interests: dict[str, float]) -> dict[str, float]:
        invalid = [name for name, weight in interests.items() if not 0 <= weight <= 1]
        if invalid:
            raise ValueError(f"interest weights must be between 0 and 1: {invalid}")
        return interests


class UserPreferenceRead(UserPreferencePayload):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
