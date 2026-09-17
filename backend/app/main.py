from fastapi import FastAPI

from app.api.v1.trips import router as trips_router
from app.api.v1.users import router as users_router
from app.api.v1.pois import router as pois_router
from app.api.v1.weather import router as weather_router
from app.api.v1.hotels import router as hotels_router
from app.api.v1.routes import router as routes_router
from app.api.v1.planner import router as planner_router
from app.api.v1.expenses import router as expenses_router


app = FastAPI(
    title="TravelMind API",
    version="0.1.0",
    description="Domestic travel planning API for the TravelMind MVP.",
)

app.include_router(trips_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(pois_router, prefix="/api/v1")
app.include_router(weather_router, prefix="/api/v1")
app.include_router(hotels_router, prefix="/api/v1")
app.include_router(routes_router, prefix="/api/v1")
app.include_router(planner_router, prefix="/api/v1")
app.include_router(expenses_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "travelmind-api"}
