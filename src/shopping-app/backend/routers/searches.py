import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException

logger = logging.getLogger(__name__)

from db import get_db
from models import (
    MessageCreate,
    MessageResponse,
    ProductCard,
    SearchDetail,
    SearchSummary,
    StatusResponse,
)
from services.clarify import clarify
from services.preferences import recall_preferences
from services.search import execute_search

router = APIRouter(prefix="/searches", tags=["searches"])


@router.get("", response_model=list[SearchSummary])
async def list_searches():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, created_at, updated_at, status, spec, results FROM searches ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        summaries = []
        for row in rows:
            result_count = 0
            if row["results"]:
                try:
                    result_count = len(json.loads(row["results"]))
                except (json.JSONDecodeError, TypeError):
                    pass
            spec = None
            if row["spec"]:
                try:
                    spec = json.loads(row["spec"])
                except (json.JSONDecodeError, TypeError):
                    pass
            summaries.append(
                SearchSummary(
                    id=row["id"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    status=row["status"],
                    spec=spec,
                    result_count=result_count,
                )
            )
        return summaries
    finally:
        await db.close()


@router.post("")
async def create_search():
    search_id = uuid.uuid4().hex
    logger.info("Creating search %s", search_id)
    db = await get_db()
    try:
        await db.execute("INSERT INTO searches (id) VALUES (?)", (search_id,))
        await db.commit()
    finally:
        await db.close()
    return {"id": search_id, "status": "clarifying"}


@router.get("/{search_id}", response_model=SearchDetail)
async def get_search(search_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, status, spec, results, error FROM searches WHERE id = ?",
            (search_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Search not found")

        # Load messages
        msg_cursor = await db.execute(
            "SELECT id, role, content, created_at FROM messages WHERE search_id = ? ORDER BY created_at",
            (search_id,),
        )
        msg_rows = await msg_cursor.fetchall()
        messages = [
            MessageResponse(
                id=r["id"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
            )
            for r in msg_rows
        ]

        spec = None
        if row["spec"]:
            try:
                spec = json.loads(row["spec"])
            except (json.JSONDecodeError, TypeError):
                pass

        results = []
        if row["results"]:
            try:
                raw = json.loads(row["results"])
                results = [ProductCard(**p) for p in raw]
            except (json.JSONDecodeError, TypeError):
                pass

        return SearchDetail(
            id=row["id"],
            status=row["status"],
            spec=spec,
            messages=messages,
            results=results,
            error=row["error"],
        )
    finally:
        await db.close()


@router.post("/{search_id}/messages", response_model=MessageResponse)
async def send_message(search_id: str, body: MessageCreate):
    db = await get_db()
    try:
        # Verify search exists
        cursor = await db.execute(
            "SELECT id FROM searches WHERE id = ?", (search_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Search not found")

        # Save user message
        logger.info("Search %s: user message: %s", search_id, body.content[:100])
        user_msg_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO messages (id, search_id, role, content) VALUES (?, ?, ?, ?)",
            (user_msg_id, search_id, "user", body.content),
        )
        await db.commit()

        # Load full conversation history
        msg_cursor = await db.execute(
            "SELECT role, content FROM messages WHERE search_id = ? ORDER BY created_at",
            (search_id,),
        )
        msg_rows = await msg_cursor.fetchall()
        history = [{"role": r["role"], "content": r["content"]} for r in msg_rows]

        # Recall relevant preferences
        preferences = await recall_preferences(body.content)

        # Call clarify service
        reply, spec = await clarify(history, preferences)

        # Save assistant reply
        asst_msg_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO messages (id, search_id, role, content) VALUES (?, ?, ?, ?)",
            (asst_msg_id, search_id, "assistant", reply),
        )

        # If spec is ready, update search
        if spec:
            await db.execute(
                "UPDATE searches SET spec = ?, updated_at = datetime('now') WHERE id = ?",
                (json.dumps(spec), search_id),
            )

        await db.commit()

        # Fetch the saved message to get created_at
        asst_cursor = await db.execute(
            "SELECT id, role, content, created_at FROM messages WHERE id = ?",
            (asst_msg_id,),
        )
        asst_row = await asst_cursor.fetchone()

        return MessageResponse(
            id=asst_row["id"],
            role=asst_row["role"],
            content=asst_row["content"],
            created_at=asst_row["created_at"],
        )
    finally:
        await db.close()


async def _run_search(search_id: str):
    """Background task that executes the product search."""
    logger.info("Search %s: background search starting", search_id)
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT spec FROM searches WHERE id = ?", (search_id,)
        )
        row = await cursor.fetchone()
        spec = json.loads(row["spec"]) if row and row["spec"] else {}

        # Load conversation history
        msg_cursor = await db.execute(
            "SELECT role, content FROM messages WHERE search_id = ? ORDER BY created_at",
            (search_id,),
        )
        msg_rows = await msg_cursor.fetchall()
        messages = [{"role": r["role"], "content": r["content"]} for r in msg_rows]

        logger.info("Search %s: executing with spec %s", search_id, json.dumps(spec)[:200])
        products = await execute_search(spec, messages)
        logger.info("Search %s: got %d products", search_id, len(products))

        await db.execute(
            "UPDATE searches SET results = ?, status = 'complete', updated_at = datetime('now') WHERE id = ?",
            (json.dumps(products), search_id),
        )
        await db.commit()
        logger.info("Search %s: complete", search_id)
    except Exception as e:
        logger.error("Search %s: failed: %s", search_id, e, exc_info=True)
        await db.execute(
            "UPDATE searches SET status = 'failed', error = ?, updated_at = datetime('now') WHERE id = ?",
            (str(e), search_id),
        )
        await db.commit()
    finally:
        await db.close()


@router.post("/{search_id}/confirm")
async def confirm_search(search_id: str, background_tasks: BackgroundTasks):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, spec FROM searches WHERE id = ?", (search_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Search not found")

        # If no spec yet, generate one from conversation history
        if not row["spec"]:
            msg_cursor = await db.execute(
                "SELECT role, content FROM messages WHERE search_id = ? ORDER BY created_at",
                (search_id,),
            )
            msg_rows = await msg_cursor.fetchall()
            history = [{"role": r["role"], "content": r["content"]} for r in msg_rows]
            _, spec = await clarify(history)
            if spec:
                await db.execute(
                    "UPDATE searches SET spec = ?, updated_at = datetime('now') WHERE id = ?",
                    (json.dumps(spec), search_id),
                )

        await db.execute(
            "UPDATE searches SET status = 'searching', updated_at = datetime('now') WHERE id = ?",
            (search_id,),
        )
        await db.commit()
    finally:
        await db.close()

    background_tasks.add_task(_run_search, search_id)
    return {"status": "searching"}


@router.post("/{search_id}/refine")
async def refine_search(
    search_id: str, body: MessageCreate, background_tasks: BackgroundTasks
):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM searches WHERE id = ?", (search_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Search not found")

        # Save user refinement message
        user_msg_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO messages (id, search_id, role, content) VALUES (?, ?, ?, ?)",
            (user_msg_id, search_id, "user", body.content),
        )
        await db.commit()

        # Load conversation history
        msg_cursor = await db.execute(
            "SELECT role, content FROM messages WHERE search_id = ? ORDER BY created_at",
            (search_id,),
        )
        msg_rows = await msg_cursor.fetchall()
        history = [{"role": r["role"], "content": r["content"]} for r in msg_rows]

        # Generate acknowledgment
        preferences = await recall_preferences(body.content)
        reply, spec = await clarify(history, preferences)

        # Save assistant acknowledgment
        asst_msg_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO messages (id, search_id, role, content) VALUES (?, ?, ?, ?)",
            (asst_msg_id, search_id, "assistant", reply),
        )

        # Update spec if a new one was generated
        if spec:
            await db.execute(
                "UPDATE searches SET spec = ?, updated_at = datetime('now') WHERE id = ?",
                (json.dumps(spec), search_id),
            )

        await db.execute(
            "UPDATE searches SET status = 'searching', updated_at = datetime('now') WHERE id = ?",
            (search_id,),
        )
        await db.commit()
    finally:
        await db.close()

    background_tasks.add_task(_run_search, search_id)
    return {"status": "searching"}


@router.get("/{search_id}/status", response_model=StatusResponse)
async def get_status(search_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT status, error FROM searches WHERE id = ?", (search_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Search not found")
        return StatusResponse(status=row["status"], error=row["error"])
    finally:
        await db.close()
