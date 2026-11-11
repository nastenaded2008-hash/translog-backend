from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .database import Base, engine, get_db
from . import models, schemas
from .security import hash_password, verify_password, create_access_token
from .deps import get_current_user, require_roles

STATUSES = {"created", "assigned", "in_transit", "at_unloading", "completed"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Для учебного MVP таблицы создаются автоматически при старте.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(
    title="ТРАНСЛОГ — API транспортной логистики",
    description="Backend для заявок, транспорта, водителей и контроля перевозок.",
    version="1.0.0",
    lifespan=lifespan,
)

@app.get("/")
async def root():
    return {"service": "ТРАНСЛОГ API", "docs": "/docs"}

@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    # В отличие от простого ping, этот endpoint проверяет доступность PostgreSQL.
    await db.execute(select(1))
    return {"status": "ok", "database": "connected"}

@app.post("/auth/register", response_model=schemas.UserOut, status_code=201)
async def register(data: schemas.RegisterIn, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(models.User).where(models.User.phone == data.phone))
    if existing:
        raise HTTPException(409, "Пользователь с таким телефоном уже существует")
    user = models.User(
        name=data.name,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role="shipper",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@app.post("/auth/login", response_model=schemas.TokenOut)
async def login(data: schemas.LoginIn, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(models.User).where(models.User.phone == data.phone))
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Неверный телефон или пароль")
    return {"access_token": create_access_token(user.id, user.role), "token_type": "bearer"}

@app.get("/users/me", response_model=schemas.UserOut)
async def me(user: models.User = Depends(get_current_user)):
    return user

@app.get("/users", response_model=list[schemas.UserOut])
async def list_users(
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_roles("admin", "dispatcher", "manager")),
):
    stmt = select(models.User).order_by(models.User.id)
    if role:
        stmt = stmt.where(models.User.role == role)
    return list((await db.scalars(stmt)).all())

@app.post("/vehicles", response_model=schemas.VehicleOut, status_code=201)
async def create_vehicle(
    data: schemas.VehicleCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_roles("admin", "dispatcher")),
):
    existing = await db.scalar(select(models.Vehicle).where(models.Vehicle.plate_number == data.plate_number))
    if existing:
        raise HTTPException(409, "Автомобиль с таким номером уже существует")
    vehicle = models.Vehicle(**data.model_dump())
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle

@app.get("/vehicles", response_model=list[schemas.VehicleOut])
async def list_vehicles(
    available_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    stmt = select(models.Vehicle).where(models.Vehicle.is_active.is_(True)).order_by(models.Vehicle.id)
    if available_only:
        stmt = stmt.where(models.Vehicle.is_available.is_(True))
    return list((await db.scalars(stmt)).all())

@app.patch("/vehicles/{vehicle_id}", response_model=schemas.VehicleOut)
async def update_vehicle(
    vehicle_id: int,
    data: schemas.VehicleUpdate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_roles("admin", "dispatcher")),
):
    vehicle = await db.get(models.Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(404, "Автомобиль не найден")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(vehicle, key, value)
    await db.commit()
    await db.refresh(vehicle)
    return vehicle

@app.post("/shipments", response_model=schemas.ShipmentOut, status_code=201)
async def create_shipment(
    data: schemas.ShipmentCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    shipment = models.Shipment(**data.model_dump(), created_by_id=user.id)
    db.add(shipment)
    await db.flush()
    db.add(models.ShipmentStatusHistory(
        shipment_id=shipment.id, old_status=None, new_status="created", changed_by_id=user.id
    ))
    await db.commit()
    await db.refresh(shipment)
    return shipment

@app.get("/shipments", response_model=list[schemas.ShipmentOut])
async def list_shipments(
    status_filter: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    stmt = select(models.Shipment).order_by(models.Shipment.created_at.desc())
    if user.role == "driver":
        stmt = stmt.where(models.Shipment.driver_id == user.id)
    elif user.role == "shipper":
        stmt = stmt.where(models.Shipment.created_by_id == user.id)
    if status_filter:
        stmt = stmt.where(models.Shipment.status == status_filter)
    return list((await db.scalars(stmt)).all())

@app.get("/shipments/{shipment_id}", response_model=schemas.ShipmentOut)
async def get_shipment(
    shipment_id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    shipment = await db.get(models.Shipment, shipment_id)
    if not shipment:
        raise HTTPException(404, "Заявка не найдена")
    if user.role == "driver" and shipment.driver_id != user.id:
        raise HTTPException(403, "Это не ваша перевозка")
    if user.role == "shipper" and shipment.created_by_id != user.id:
        raise HTTPException(403, "Нет доступа к этой заявке")
    return shipment

@app.patch("/shipments/{shipment_id}", response_model=schemas.ShipmentOut)
async def update_shipment(
    shipment_id: int,
    data: schemas.ShipmentUpdate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_roles("admin", "dispatcher")),
):
    shipment = await db.get(models.Shipment, shipment_id)
    if not shipment:
        raise HTTPException(404, "Заявка не найдена")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(shipment, key, value)
    await db.commit()
    await db.refresh(shipment)
    return shipment

@app.post("/shipments/{shipment_id}/assign", response_model=schemas.ShipmentOut)
async def assign_shipment(
    shipment_id: int,
    data: schemas.AssignIn,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_roles("admin", "dispatcher")),
):
    shipment = await db.get(models.Shipment, shipment_id)
    vehicle = await db.get(models.Vehicle, data.vehicle_id)
    driver = await db.get(models.User, data.driver_id)
    if not shipment:
        raise HTTPException(404, "Заявка не найдена")
    if not vehicle or not vehicle.is_active or not vehicle.is_available:
        raise HTTPException(400, "Автомобиль недоступен")
    if not driver or driver.role != "driver" or not driver.is_active:
        raise HTTPException(400, "Водитель не найден или не имеет роли driver")
    if vehicle.capacity_kg < shipment.weight_kg:
        raise HTTPException(400, "Груз превышает грузоподъемность автомобиля")
    busy = await db.scalar(select(models.Shipment).where(
        models.Shipment.driver_id == driver.id,
        models.Shipment.status.in_(["assigned", "in_transit", "at_unloading"]),
        models.Shipment.id != shipment.id,
    ))
    if busy:
        raise HTTPException(409, "У водителя уже есть активная перевозка")
    shipment.vehicle_id = vehicle.id
    shipment.driver_id = driver.id
    shipment.status = "assigned"
    vehicle.is_available = False
    db.add(models.ShipmentStatusHistory(
        shipment_id=shipment.id, old_status="created", new_status="assigned", changed_by_id=user.id
    ))
    db.add(models.Notification(
        shipment_id=shipment.id, recipient_user_id=driver.id,
        message=f"Вам назначена перевозка №{shipment.id}.", channel="in_app"
    ))
    await db.commit()
    await db.refresh(shipment)
    return shipment

@app.put("/shipments/{shipment_id}/route", response_model=schemas.ShipmentOut)
async def save_route(
    shipment_id: int,
    data: schemas.RouteIn,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_roles("admin", "dispatcher")),
):
    shipment = await db.get(models.Shipment, shipment_id)
    if not shipment:
        raise HTTPException(404, "Заявка не найдена")
    shipment.route_description = data.route_description
    shipment.route_distance_km = data.distance_km
    shipment.route_duration_min = data.duration_min
    await db.commit()
    await db.refresh(shipment)
    return shipment

@app.patch("/shipments/{shipment_id}/status", response_model=schemas.ShipmentOut)
async def change_status(
    shipment_id: int,
    data: schemas.StatusIn,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if data.status not in STATUSES - {"created"}:
        raise HTTPException(400, "Допустимые статусы: assigned, in_transit, at_unloading, completed")
    shipment = await db.get(models.Shipment, shipment_id)
    if not shipment:
        raise HTTPException(404, "Заявка не найдена")
    if user.role == "driver" and shipment.driver_id != user.id:
        raise HTTPException(403, "Это не ваша перевозка")
    if user.role not in {"admin", "dispatcher", "driver"}:
        raise HTTPException(403, "Недостаточно прав")
    old_status = shipment.status
    shipment.status = data.status
    db.add(models.ShipmentStatusHistory(
        shipment_id=shipment.id, old_status=old_status,
        new_status=data.status, changed_by_id=user.id
    ))
    db.add(models.Notification(
        shipment_id=shipment.id, recipient_user_id=shipment.created_by_id,
        message=f"Статус перевозки №{shipment.id} изменен: {data.status}.",
        channel="in_app"
    ))
    if data.status == "completed" and shipment.vehicle_id:
        vehicle = await db.get(models.Vehicle, shipment.vehicle_id)
        if vehicle:
            vehicle.is_available = True
    await db.commit()
    await db.refresh(shipment)
    return shipment

@app.post("/shipments/{shipment_id}/gps", response_model=schemas.GPSOut, status_code=201)
async def add_gps_location(
    shipment_id: int,
    data: schemas.GPSIn,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    shipment = await db.get(models.Shipment, shipment_id)
    if not shipment:
        raise HTTPException(404, "Заявка не найдена")
    if user.role == "driver" and shipment.driver_id != user.id:
        raise HTTPException(403, "Это не ваша перевозка")
    if user.role not in {"admin", "dispatcher", "driver"}:
        raise HTTPException(403, "Недостаточно прав")
    point = models.GPSLocation(shipment_id=shipment_id, **data.model_dump())
    db.add(point)
    await db.commit()
    await db.refresh(point)
    return point

@app.get("/shipments/{shipment_id}/gps/latest", response_model=schemas.GPSOut)
async def latest_gps(
    shipment_id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    shipment = await db.get(models.Shipment, shipment_id)
    if not shipment:
        raise HTTPException(404, "Заявка не найдена")
    if user.role == "driver" and shipment.driver_id != user.id:
        raise HTTPException(403, "Это не ваша перевозка")
    if user.role == "shipper" and shipment.created_by_id != user.id:
        raise HTTPException(403, "Нет доступа к этой заявке")
    point = await db.scalar(select(models.GPSLocation).where(
        models.GPSLocation.shipment_id == shipment_id
    ).order_by(models.GPSLocation.recorded_at.desc()).limit(1))
    if not point:
        raise HTTPException(404, "GPS-координаты пока не поступали")
    return point

@app.get("/shipments/{shipment_id}/history", response_model=list[schemas.HistoryOut])
async def shipment_history(
    shipment_id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    shipment = await db.get(models.Shipment, shipment_id)
    if not shipment:
        raise HTTPException(404, "Заявка не найдена")
    if user.role == "driver" and shipment.driver_id != user.id:
        raise HTTPException(403, "Это не ваша перевозка")
    if user.role == "shipper" and shipment.created_by_id != user.id:
        raise HTTPException(403, "Нет доступа к этой заявке")
    result = await db.scalars(select(models.ShipmentStatusHistory).where(
        models.ShipmentStatusHistory.shipment_id == shipment_id
    ).order_by(models.ShipmentStatusHistory.changed_at))
    return list(result.all())

@app.get("/notifications", response_model=list[schemas.NotificationOut])
async def my_notifications(
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    stmt = select(models.Notification).where(
        models.Notification.recipient_user_id == user.id
    ).order_by(models.Notification.created_at.desc())
    return list((await db.scalars(stmt)).all())

@app.get("/reports/summary")
async def report_summary(
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(require_roles("admin", "dispatcher", "manager")),
):
    total = await db.scalar(select(func.count(models.Shipment.id))) or 0
    completed = await db.scalar(select(func.count(models.Shipment.id)).where(
        models.Shipment.status == "completed"
    )) or 0
    active = await db.scalar(select(func.count(models.Shipment.id)).where(
        models.Shipment.status.in_(["assigned", "in_transit", "at_unloading"])
    )) or 0
    created = await db.scalar(select(func.count(models.Shipment.id)).where(
        models.Shipment.status == "created"
    )) or 0
    return {
        "total_shipments": total,
        "completed": completed,
        "active": active,
        "waiting_for_assignment": created,
    }
