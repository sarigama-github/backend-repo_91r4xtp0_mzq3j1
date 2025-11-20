import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime, timezone

from database import db, create_document, get_documents
from schemas import Gem


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        try:
            return ObjectId(str(v))
        except Exception:
            raise ValueError("Invalid ObjectId")


class GemOut(BaseModel):
    id: str = Field(..., alias="_id")
    name: str
    type: str
    weight: float
    price: float
    description: str
    certification: Optional[str] = None
    image: Optional[str] = None
    gallery: Optional[List[str]] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class LoginRequest(BaseModel):
    password: str


app = FastAPI(title="Gemstone Store API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Gemstone Store Backend Running"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response


# --------- Admin Login (simple password) ---------
@app.post("/api/admin/login")
def admin_login(payload: LoginRequest):
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if payload.password == admin_password:
        return {"token": "admin-token"}
    raise HTTPException(status_code=401, detail="Invalid password")


# --------- Gems CRUD ---------
@app.get("/api/gems")
def list_gems(
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=100),
    sort_by: str = Query("price", pattern="^(price|weight)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    if db is None:
        # Fallback to sample data if DB not connected
        sample = _sample_gems()
        # simple search/type filter
        data = [g for g in sample if (not type or g["type"].lower()==type.lower()) and (not search or search.lower() in g["name"].lower())]
        reverse = sort_order == "desc"
        data = sorted(data, key=lambda x: x[sort_by], reverse=reverse)
        start = (page-1)*limit
        end = start+limit
        return {"items": data[start:end], "total": len(data)}

    query = {}
    if type:
        query["type"] = {"$regex": f"^{type}$", "$options": "i"}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}

    sort_dir = 1 if sort_order == "asc" else -1

    total = db["gem"].count_documents(query)
    cursor = (
        db["gem"]
        .find(query)
        .sort(sort_by, sort_dir)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    items = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        items.append(doc)
    return {"items": items, "total": total}


@app.get("/api/gems/{gem_id}")
def get_gem(gem_id: str):
    if db is None:
        for g in _sample_gems():
            if g["_id"] == gem_id:
                return g
        raise HTTPException(status_code=404, detail="Gem not found")
    try:
        obj_id = ObjectId(gem_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    doc = db["gem"].find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Gem not found")
    doc["_id"] = str(doc["_id"])
    return doc


@app.post("/api/gems")
def create_gem(payload: Gem):
    if db is None:
        # No DB available
        raise HTTPException(status_code=503, detail="Database not available")
    gem_dict = payload.model_dump()
    now = datetime.now(timezone.utc)
    gem_dict["created_at"] = now
    gem_dict["updated_at"] = now
    result = db["gem"].insert_one(gem_dict)
    return {"_id": str(result.inserted_id), **gem_dict}


@app.put("/api/gems/{gem_id}")
def update_gem(gem_id: str, payload: Gem):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        obj_id = ObjectId(gem_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    data = payload.model_dump()
    data["updated_at"] = datetime.now(timezone.utc)
    res = db["gem"].update_one({"_id": obj_id}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Gem not found")
    doc = db["gem"].find_one({"_id": obj_id})
    doc["_id"] = str(doc["_id"])
    return doc


@app.delete("/api/gems/{gem_id}")
def delete_gem(gem_id: str):
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        obj_id = ObjectId(gem_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    res = db["gem"].delete_one({"_id": obj_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Gem not found")
    return {"success": True}


@app.post("/api/seed")
def seed_data():
    if db is None:
        return {"seeded": False, "reason": "Database not available"}
    if db["gem"].count_documents({}) > 0:
        return {"seeded": True, "existing": True}
    data = _sample_gems()
    # convert _id strings back to ObjectIds? We'll let DB assign new IDs.
    for g in data:
        g.pop("_id", None)
    now = datetime.now(timezone.utc)
    for g in data:
        g["created_at"] = now
        g["updated_at"] = now
    db["gem"].insert_many(data)
    return {"seeded": True}


# --------- Helper: Sample Data ---------

def _sample_gems():
    return [
        {
            "_id": "sg-1",
            "name": "Imperial Ruby",
            "type": "Ruby",
            "weight": 2.5,
            "price": 12500,
            "description": "A vivid pigeon-blood ruby with exceptional clarity.",
            "certification": "GIA Certified",
            "image": "https://images.unsplash.com/photo-1603575449299-0b6b76f946e6?q=80&w=1200&auto=format&fit=crop",
            "gallery": [
                "https://images.unsplash.com/photo-1603575449299-0b6b76f946e6?q=80&w=1200&auto=format&fit=crop",
                "https://images.unsplash.com/photo-1618220179428-22790b87a013?q=80&w=1200&auto=format&fit=crop"
            ],
        },
        {
            "_id": "sg-2",
            "name": "Azure Sapphire",
            "type": "Sapphire",
            "weight": 3.1,
            "price": 9800,
            "description": "Deep blue Ceylon sapphire with royal luster.",
            "certification": "GIA Certified",
            "image": "https://images.unsplash.com/photo-1603570404763-47b3a1e3898d?q=80&w=1200&auto=format&fit=crop",
            "gallery": [],
        },
        {
            "_id": "sg-3",
            "name": "Verdant Emerald",
            "type": "Emerald",
            "weight": 4.2,
            "price": 15200,
            "description": "Colombian emerald with rich green saturation.",
            "certification": "IGI Certified",
            "image": "https://images.unsplash.com/photo-1615678857339-4e7a1d870265?q=80&w=1200&auto=format&fit=crop",
            "gallery": [],
        },
        {
            "_id": "sg-4",
            "name": "Golden Topaz",
            "type": "Topaz",
            "weight": 5.0,
            "price": 4200,
            "description": "Honey gold topaz with brilliant facets.",
            "certification": None,
            "image": "https://images.unsplash.com/photo-1560891780-87d88ab4add0?q=80&w=1200&auto=format&fit=crop",
            "gallery": [],
        },
        {
            "_id": "sg-5",
            "name": "Amethyst Royale",
            "type": "Amethyst",
            "weight": 6.3,
            "price": 2100,
            "description": "Regal purple amethyst with superb clarity.",
            "certification": None,
            "image": "https://images.unsplash.com/photo-1609250291995-9cfb68f2915e?q=80&w=1200&auto=format&fit=crop",
            "gallery": [],
        },
        {
            "_id": "sg-6",
            "name": "Crystalline Diamond",
            "type": "Diamond",
            "weight": 1.3,
            "price": 22500,
            "description": "Brilliant-cut diamond with fire and scintillation.",
            "certification": "GIA Certified",
            "image": "https://images.unsplash.com/photo-1602526432604-c8586b197fd1?q=80&w=1200&auto=format&fit=crop",
            "gallery": [],
        },
    ]


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
