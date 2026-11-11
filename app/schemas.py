from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=8, max_length=128)

class LoginIn(BaseModel):
    phone: str
    password: str

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    phone: str
    role: str
    is_active: bool
    created_at: datetime

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class VehicleCreate(BaseModel):
    plate_number: str = Field(min_length=2, max_length=30)
    brand: str = Field(min_length=1, max_length=80)
    capacity_kg: float = Field(gt=0)

class VehicleUpdate(BaseModel):
    plate_number: str | None = None
    brand: str | None = None
    capacity_kg: float | None = Field(default=None, gt=0)
    is_available: bool | None = None
    is_active: bool | None = None

class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    plate_number: str
    brand: str
    capacity_kg: float
    is_available: bool
    is_active: bool

class ShipmentCreate(BaseModel):
    sender_name: str = Field(min_length=1, max_length=120)
    recipient_name: str = Field(min_length=1, max_length=120)
    pickup_address: str = Field(min_length=3)
    delivery_address: str = Field(min_length=3)
    cargo_type: str = Field(min_length=1, max_length=120)
    weight_kg: float = Field(gt=0)
    volume_m3: float | None = Field(default=None, ge=0)
    desired_date: date | None = None

class ShipmentUpdate(BaseModel):
    sender_name: str | None = None
    recipient_name: str | None = None
    pickup_address: str | None = None
    delivery_address: str | None = None
    cargo_type: str | None = None
    weight_kg: float | None = Field(default=None, gt=0)
    volume_m3: float | None = Field(default=None, ge=0)
    desired_date: date | None = None

class AssignIn(BaseModel):
    vehicle_id: int
    driver_id: int

class RouteIn(BaseModel):
    route_description: str = Field(min_length=1)
    distance_km: float | None = Field(default=None, ge=0)
    duration_min: int | None = Field(default=None, ge=0)

class StatusIn(BaseModel):
    status: str

class GPSIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

class GPSOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    shipment_id: int
    latitude: float
    longitude: float
    recorded_at: datetime

class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sender_name: str
    recipient_name: str
    pickup_address: str
    delivery_address: str
    cargo_type: str
    weight_kg: float
    volume_m3: float | None
    desired_date: date | None
    status: str
    vehicle_id: int | None
    driver_id: int | None
    route_description: str | None
    route_distance_km: float | None
    route_duration_min: int | None
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime

class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    shipment_id: int
    old_status: str | None
    new_status: str
    changed_by_id: int | None
    changed_at: datetime

class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    shipment_id: int
    recipient_user_id: int | None
    message: str
    channel: str
    is_sent: bool
    created_at: datetime
