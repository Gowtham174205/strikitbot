"""
WhatsApp Service — Meta Cloud API wrapper for sending messages.
Supports: text, buttons, lists, documents, images.
Falls back to mock/console output when API keys not configured.
"""
import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

WHATSAPP_API_URL = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}"

# ── Mock message store for testing ──
mock_sent_messages: list[dict] = []


def get_mock_messages() -> list[dict]:
    return mock_sent_messages


def clear_mock_messages():
    mock_sent_messages.clear()


async def _send_whatsapp_request(payload: dict) -> dict:
    """Send a payload to Meta Cloud API or mock it in dev."""
    if not settings.whatsapp_configured:
        mock_sent_messages.append(payload)
        to = payload.get("to", "unknown")
        if payload.get("type") == "text":
            logger.info(f"[MOCK WA → {to}] {payload['text']['body'][:100]}")
        elif payload.get("type") == "interactive":
            body = payload.get("interactive", {}).get("body", {}).get("text", "")
            logger.info(f"[MOCK WA → {to}] Interactive: {body[:100]}")
        elif payload.get("type") == "document":
            logger.info(f"[MOCK WA → {to}] Document: {payload['document'].get('filename', '')}")
        elif payload.get("type") == "image":
            logger.info(f"[MOCK WA → {to}] Image: {payload['image'].get('link', '')[:60]}")
        return {"contacts": [{"wa_id": to}], "messages": [{"id": f"wamid.mock_{id(payload)}"}]}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"[WhatsApp API Error] {e.response.status_code}: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"[WhatsApp API Error] {e}")
        raise


async def send_text(to: str, text: str) -> dict:
    """Send a plain text message."""
    return await _send_whatsapp_request({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": text},
    })


async def send_buttons(to: str, text: str, buttons: list[dict]) -> dict:
    """Send interactive button message. Max 3 buttons, 20 char titles."""
    formatted = [
        {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
        for b in buttons[:3]
    ]
    return await _send_whatsapp_request({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text},
            "action": {"buttons": formatted},
        },
    })


async def send_list(to: str, text: str, button_text: str, sections: list[dict]) -> dict:
    """Send interactive list menu message."""
    return await _send_whatsapp_request({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": text},
            "action": {"button": button_text[:20], "sections": sections},
        },
    })


async def send_document(to: str, file_url: str, filename: str, caption: str = "") -> dict:
    """Send a document attachment (PDF, etc.)."""
    return await _send_whatsapp_request({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "document",
        "document": {"link": file_url, "filename": filename, "caption": caption},
    })


async def send_image(to: str, image_url: str, caption: str = "") -> dict:
    """Send an image attachment."""
    return await _send_whatsapp_request({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "image",
        "image": {"link": image_url, "caption": caption},
    })


async def get_media_url(media_id: str) -> str:
    """Get the download URL for a WhatsApp media object."""
    if not settings.whatsapp_configured:
        return f"https://mock-whatsapp-media.strikit.in/media/{media_id}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{WHATSAPP_API_URL}/{media_id}",
                headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            )
            resp.raise_for_status()
            return resp.json().get("url", f"{WHATSAPP_API_URL}/{media_id}")
    except Exception as e:
        logger.error(f"[WhatsApp Media URL Error] {e}")
        return f"{WHATSAPP_API_URL}/{media_id}"


async def download_whatsapp_media(media_id: str, filename_prefix: str) -> str:
    """
    Downloads media from WhatsApp Cloud API, saves it to the local static directory,
    and returns the public URL.
    """
    import os
    if not settings.whatsapp_configured:
        return f"https://bot.strikit.in/static/mock_media.jpg"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{WHATSAPP_API_URL}/{media_id}",
                headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            )
            resp.raise_for_status()
            data = resp.json()
            download_url = data.get("url")
            mime_type = data.get("mime_type", "")
            
            ext = ".jpg"
            if "pdf" in mime_type:
                ext = ".pdf"
            elif "png" in mime_type:
                ext = ".png"
            elif "jpeg" in mime_type:
                ext = ".jpg"
                
            if not download_url:
                logger.error(f"[WhatsApp Media] No download URL in metadata for media_id {media_id}")
                return ""
                
            media_resp = await client.get(
                download_url,
                headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            )
            media_resp.raise_for_status()
            
            os.makedirs("static", exist_ok=True)
            filename = f"{filename_prefix}_{media_id}{ext}"
            filepath = os.path.join("static", filename)
            
            with open(filepath, "wb") as f:
                f.write(media_resp.content)
                
            public_url = f"https://bot.strikit.in/static/{filename}"
            logger.info(f"✅ Successfully downloaded WhatsApp media {media_id} -> {public_url}")
            return public_url
    except Exception as e:
        logger.error(f"❌ Failed to download WhatsApp media {media_id}: {e}")
        return ""


async def send_developer_verification_alert(owner) -> None:
    """Send owner onboarding alert to all configured developer numbers, attaching media directly."""
    dev_numbers = settings.developer_numbers_list
    if not dev_numbers:
        logger.info("[Developer Alert] No developer numbers configured.")
        return

    # Clean text notification without long links to avoid clutter
    msme_val = "Uploaded" if owner.msmeCardUrl else "N/A"
    utility_val = "Uploaded" if owner.utilityBillUrl else "N/A"
    photos_count = 0
    import json
    try:
        urls = json.loads(owner.photoUrls)
        if isinstance(urls, list):
            photos_count = len(urls)
    except Exception:
        if owner.photoUrls:
            photos_count = 1

    text = (
        f"🆕 *New Owner Onboarding Request* 🆕\n\n"
        f"• *ID:* {owner.id}\n"
        f"• *Name:* {owner.name}\n"
        f"• *Phone:* {owner.mobile}\n"
        f"• *Turf:* {owner.turfName}\n"
        f"• *Location:* {owner.location}\n"
        f"• *Photos:* {photos_count} uploaded\n"
        f"• *GST:* {owner.gst or 'N/A'}\n"
        f"• *MSME:* {msme_val}\n"
        f"• *Utility Bill:* {utility_val}\n\n"
        f"*Action Commands:*\n"
        f"👉 To approve: reply with `/approve {owner.id}`\n"
        f"👉 To reject: reply with `/reject {owner.id}`\n\n"
        f"_Powered by STRIKIT_"
    )

    for phone in dev_numbers:
        try:
            # 1. Send the text notification
            await send_text(phone, text)
            
            # 2. Send the actual Turf Photos directly as photo messages
            try:
                if owner.photoUrls:
                    urls = json.loads(owner.photoUrls)
                    if isinstance(urls, list):
                        for idx, url in enumerate(urls, 1):
                            if url.startswith("http"):
                                await send_image(phone, url, caption=f"Turf Photo {idx} - {owner.turfName}")
                    elif isinstance(urls, str) and urls.startswith("http"):
                        await send_image(phone, urls, caption=f"Turf Photo - {owner.turfName}")
            except Exception as e:
                logger.error(f"[Developer Alert] Failed to send photos to {phone}: {e}")

            # 3. Send MSME Certificate
            if owner.msmeCardUrl and owner.msmeCardUrl.startswith("http"):
                try:
                    if owner.msmeCardUrl.lower().endswith((".jpg", ".jpeg", ".png")):
                        await send_image(phone, owner.msmeCardUrl, caption=f"MSME Certificate - {owner.name}")
                    else:
                        await send_document(phone, owner.msmeCardUrl, "MSME_Certificate", caption=f"MSME Certificate - {owner.name}")
                except Exception as e:
                    logger.error(f"[Developer Alert] Failed to send MSME to {phone}: {e}")

            # 4. Send Utility Bill
            if owner.utilityBillUrl and owner.utilityBillUrl.startswith("http"):
                try:
                    if owner.utilityBillUrl.lower().endswith((".jpg", ".jpeg", ".png")):
                        await send_image(phone, owner.utilityBillUrl, caption=f"Utility Bill - {owner.name}")
                    else:
                        await send_document(phone, owner.utilityBillUrl, "Utility_Bill", caption=f"Utility Bill - {owner.name}")
                except Exception as e:
                    logger.error(f"[Developer Alert] Failed to send Utility Bill to {phone}: {e}")
                    
        except Exception as e:
            logger.error(f"[Developer Alert] Failed to send alert to {phone}: {e}")
