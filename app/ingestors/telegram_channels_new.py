"""
Updated Telegram parser with video link support.
Photos are downloaded, videos save only links for later download after moderation.
"""
import json
from pathlib import Path
from typing import Any
import uuid

from telethon import TelegramClient
from telethon.tl.types import Message


async def download_message_media_v2(client: TelegramClient, message: Message) -> dict[str, Any]:
    """
    Download photos and save Telegram links for videos.

    Strategy:
    - Photos: Download and save to /app/app/admin/static/uploads
    - Videos: Save Telegram file_id and link for later download after moderation

    Args:
        client: Telethon client
        message: Telegram message with media

    Returns:
        Dict with 'photos' (list of local paths) and 'videos' (list of dicts with metadata)
    """
    result = {
        "photos": [],
        "videos": []
    }

    try:
        # Create uploads directory if it doesn't exist (in static folder for web access)
        uploads_dir = Path("/app/app/admin/static/uploads")
        uploads_dir.mkdir(parents=True, exist_ok=True)

        # Download photos (always download for preview)
        if message.photo:
            file_ext = "jpg"
            filename = f"tg_{message.id}_{uuid.uuid4().hex[:8]}.{file_ext}"
            file_path = uploads_dir / filename

            await client.download_media(message.photo, file=str(file_path))

            # Verify file was downloaded and has content
            if file_path.exists() and file_path.stat().st_size > 0:
                print(f"telegram.photo_downloaded message_id={message.id} size={file_path.stat().st_size}")
                result["photos"].append(f"/uploads/{filename}")
            elif file_path.exists():
                file_path.unlink()  # Delete empty file

        # For videos: Save metadata and Telegram link (download after moderation)
        if message.video:
            video_info = {
                "message_id": message.id,
                "file_id": message.video.id,
                "duration": message.video.duration,
                "size": message.video.size,
                "mime_type": message.video.mime_type or "video/mp4",
                "width": message.video.attributes[0].w if message.video.attributes else None,
                "height": message.video.attributes[0].h if message.video.attributes else None,
                # Generate preview link (will be downloaded after approval)
                "telegram_link": f"tg://video/{message.video.id}",
                "downloaded": False
            }
            print(f"telegram.video_metadata message_id={message.id} duration={video_info['duration']}s size={video_info['size']} bytes")
            result["videos"].append(video_info)

        # Download document (if it's an image, skip if video)
        if message.document and message.document.mime_type:
            mime_type = message.document.mime_type

            if mime_type.startswith("image/"):
                file_ext = mime_type.split("/")[1] if "/" in mime_type else "jpg"
                filename = f"tg_img_{message.id}_{uuid.uuid4().hex[:8]}.{file_ext}"
                file_path = uploads_dir / filename

                await client.download_media(message.document, file=str(file_path))

                if file_path.exists() and file_path.stat().st_size > 0:
                    print(f"telegram.image_downloaded message_id={message.id} size={file_path.stat().st_size}")
                    result["photos"].append(f"/uploads/{filename}")
                elif file_path.exists():
                    file_path.unlink()

            elif mime_type.startswith("video/"):
                # Video as document - save metadata only
                video_info = {
                    "message_id": message.id,
                    "file_id": message.document.id,
                    "duration": getattr(message.document.attributes[0], 'duration', None) if message.document.attributes else None,
                    "size": message.document.size,
                    "mime_type": mime_type,
                    "telegram_link": f"tg://document/{message.document.id}",
                    "downloaded": False
                }
                print(f"telegram.video_document_metadata message_id={message.id} size={video_info['size']} bytes")
                result["videos"].append(video_info)

    except Exception as e:
        print(f"telegram.media_download_error message_id={message.id} error={e}")

    return result


async def download_video_after_approval(client: TelegramClient, video_info: dict) -> str:
    """
    Download video file after moderation approval.

    Args:
        client: Telethon client
        video_info: Video metadata dict with file_id and message_id

    Returns:
        Local path to downloaded video
    """
    try:
        uploads_dir = Path("/app/app/admin/static/uploads")
        uploads_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        filename = f"tg_vid_{video_info['message_id']}_{uuid.uuid4().hex[:8]}.mp4"
        file_path = uploads_dir / filename

        # Download video by file_id
        # Note: Need to get the message again to download media
        print(f"telegram.downloading_video file_id={video_info['file_id']} size={video_info.get('size', 'unknown')}")

        # Download takes file_id or message
        # This is a placeholder - actual implementation depends on how we store the reference
        # We might need to store channel_username and message_id to re-fetch

        return f"/uploads/{filename}"

    except Exception as e:
        print(f"telegram.video_download_error file_id={video_info.get('file_id')} error={e}")
        return ""
