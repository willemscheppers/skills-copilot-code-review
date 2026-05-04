"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from typing import Dict, Any, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    """Request payload for create/update announcement."""

    message: str = Field(..., min_length=1, max_length=500)
    expiration_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


def _get_authenticated_teacher(username: str) -> Dict[str, Any]:
    """Validate teacher identity and return teacher record."""
    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")
    return teacher


def _validate_date_window(start_date: Optional[str], expiration_date: str) -> None:
    """Ensure dates are valid and ordered."""
    try:
        parsed_expiration = date.fromisoformat(expiration_date)
        parsed_start = date.fromisoformat(start_date) if start_date else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format") from exc

    if parsed_start and parsed_start > parsed_expiration:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before expiration_date"
        )


def _serialize_announcement(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize Mongo document shape for API responses."""
    return {
        "id": item.get("_id"),
        "message": item.get("message", ""),
        "start_date": item.get("start_date"),
        "expiration_date": item.get("expiration_date"),
        "created_by": item.get("created_by")
    }


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get announcements active on today's date for public display."""
    today = date.today().isoformat()
    # Find announcements that:
    # 1. Haven't expired (expiration_date >= today)
    # 2. Either have no start date OR start date is today or earlier
    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": {"$eq": None}},
            {"start_date": {"$lte": today}}
        ]
    }

    announcements = list(announcements_collection.find(query).sort("expiration_date", 1))
    return [_serialize_announcement(item) for item in announcements]


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: str) -> List[Dict[str, Any]]:
    """Get all announcements for management UI (authenticated teachers only)."""
    _get_authenticated_teacher(teacher_username)

    announcements = announcements_collection.find({}).sort("expiration_date", 1)
    return [_serialize_announcement(item) for item in announcements]


@router.post("", response_model=Dict[str, Any])
def create_announcement(payload: AnnouncementPayload, teacher_username: str) -> Dict[str, Any]:
    """Create a new announcement (authenticated teachers only)."""
    _get_authenticated_teacher(teacher_username)

    sanitized_message = payload.message.strip()
    if not sanitized_message:
        raise HTTPException(status_code=400, detail="message is required")

    _validate_date_window(payload.start_date, payload.expiration_date)

    announcement_id = str(uuid4())
    announcement = {
        "_id": announcement_id,
        "message": sanitized_message,
        "start_date": payload.start_date,
        "expiration_date": payload.expiration_date,
        "created_by": teacher_username
    }

    announcements_collection.insert_one(announcement)

    return {
        "message": "Announcement created",
        "announcement": _serialize_announcement(announcement)
    }


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: str
) -> Dict[str, Any]:
    """Update an announcement (authenticated teachers only)."""
    _get_authenticated_teacher(teacher_username)

    sanitized_message = payload.message.strip()
    if not sanitized_message:
        raise HTTPException(status_code=400, detail="message is required")

    _validate_date_window(payload.start_date, payload.expiration_date)

    update_result = announcements_collection.update_one(
        {"_id": announcement_id},
        {
            "$set": {
                "message": sanitized_message,
                "start_date": payload.start_date,
                "expiration_date": payload.expiration_date
            }
        }
    )

    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated_item = announcements_collection.find_one({"_id": announcement_id})

    return {
        "message": "Announcement updated",
        "announcement": _serialize_announcement(updated_item)
    }


@router.delete("/{announcement_id}", response_model=Dict[str, Any])
def delete_announcement(announcement_id: str, teacher_username: str) -> Dict[str, Any]:
    """Delete an announcement (authenticated teachers only)."""
    _get_authenticated_teacher(teacher_username)

    delete_result = announcements_collection.delete_one({"_id": announcement_id})

    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
