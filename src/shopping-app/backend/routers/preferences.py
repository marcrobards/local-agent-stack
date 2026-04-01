import uuid

from fastapi import APIRouter

from db import get_db
from models import PreferenceCreate, PreferenceResponse
from services.preferences import store_preference

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=list[PreferenceResponse])
async def list_preferences():
    db = await get_db()
    try:
        cursor = await db.execute("SELECT key, value FROM preferences")
        rows = await cursor.fetchall()
        return [PreferenceResponse(key=row["key"], value=row["value"]) for row in rows]
    finally:
        await db.close()


@router.post("", response_model=PreferenceResponse)
async def upsert_preference(body: PreferenceCreate):
    db = await get_db()
    try:
        # Check if key exists
        cursor = await db.execute(
            "SELECT id FROM preferences WHERE key = ?", (body.key,)
        )
        existing = await cursor.fetchone()

        if existing:
            await db.execute(
                "UPDATE preferences SET value = ?, updated_at = datetime('now') WHERE key = ?",
                (body.value, body.key),
            )
        else:
            pref_id = uuid.uuid4().hex
            await db.execute(
                "INSERT INTO preferences (id, key, value) VALUES (?, ?, ?)",
                (pref_id, body.key, body.value),
            )
        await db.commit()
    finally:
        await db.close()

    # Dual-write to Qdrant
    await store_preference(body.key, body.value)

    return PreferenceResponse(key=body.key, value=body.value)
