from pydantic import BaseModel


class PlaceResult(BaseModel):
    display_name: str
    lat: float
    lng: float
