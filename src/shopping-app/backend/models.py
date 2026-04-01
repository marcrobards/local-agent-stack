from pydantic import BaseModel


class SearchCreate(BaseModel):
    pass


class SearchSummary(BaseModel):
    id: str
    created_at: str
    updated_at: str
    status: str
    spec: dict | None = None
    result_count: int = 0


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ProductCard(BaseModel):
    name: str
    price: str
    store: str
    image_url: str | None = None
    product_url: str


class SearchDetail(BaseModel):
    id: str
    status: str
    spec: dict | None = None
    messages: list[MessageResponse] = []
    results: list[ProductCard] = []
    error: str | None = None


class MessageCreate(BaseModel):
    content: str


class PreferenceCreate(BaseModel):
    key: str
    value: str


class PreferenceResponse(BaseModel):
    key: str
    value: str


class StatusResponse(BaseModel):
    status: str
    error: str | None = None
