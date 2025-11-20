"""
Database Schemas for Gemstone Store

Each Pydantic model represents a collection in MongoDB.
Collection name is the lowercase of the class name.
"""
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl, conlist, confloat, constr


class Gem(BaseModel):
    """
    Gem collection schema
    Collection name: "gem"
    """
    name: constr(strip_whitespace=True, min_length=2) = Field(..., description="Gem name")
    type: constr(strip_whitespace=True, min_length=2) = Field(..., description="Gem type, e.g., Ruby, Sapphire")
    weight: confloat(ge=0) = Field(..., description="Weight in carats")
    price: confloat(ge=0) = Field(..., description="Price in USD")
    description: constr(strip_whitespace=True, min_length=10) = Field(..., description="Short description")
    certification: Optional[str] = Field(None, description="Certification details, if any")
    image: Optional[HttpUrl] = Field(None, description="Primary image URL")
    gallery: Optional[conlist(HttpUrl, min_length=0)] = Field(default_factory=list, description="Gallery image URLs")


# Example schemas retained for reference
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = None
    is_active: bool = True


class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
