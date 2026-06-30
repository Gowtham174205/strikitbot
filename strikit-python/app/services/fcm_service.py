import logging
import os
import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

_firebase_app = None

def init_firebase():
    global _firebase_app
    if _firebase_app is not None:
        return
        
    cred_path = os.environ.get("FIREBASE_CREDENTIALS_PATH", "")
    if not cred_path or not os.path.exists(cred_path):
        # Fallback to local workspace files
        fallback_path = "firebase-key.json"
        if os.path.exists(fallback_path):
            cred_path = fallback_path
            
    if cred_path and os.path.exists(cred_path):
        try:
            cred = credentials.Certificate(cred_path)
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info("✅ Firebase Admin SDK initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Firebase Admin SDK: {e}")
    else:
        logger.warning("⚠️ FIREBASE_CREDENTIALS_PATH not set or file not found — FCM notifications disabled")

def send_fcm_notification(title: str, body: str, data: dict = None):
    """Send a push notification to the 'admin_alerts' topic."""
    init_firebase()
    if _firebase_app is None:
        logger.info(f"[FCM Mocked] Title: {title} | Body: {body}")
        return
        
    try:
        # Create message to 'admin_alerts' topic
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            topic="admin_alerts",
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    sound="default",
                    default_sound=True,
                    default_vibrate_timings=True,
                )
            )
        )
        
        response = messaging.send(message)
        logger.info(f"✅ Successfully sent FCM notification: {response}")
    except Exception as e:
        logger.error(f"❌ Failed to send FCM notification: {e}")
