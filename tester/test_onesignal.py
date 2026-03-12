import os
import requests
import json

# ======================================================================
# OneSignal REST API - Python Trigger Example
# ======================================================================

# To use this, you need to set up OneSignal and get these keys from your dashboard:
APP_ID = os.environ.get("ONESIGNAL_APP_ID", "YOUR_ONESIGNAL_APP_ID")
REST_API_KEY = os.environ.get("ONESIGNAL_REST_API_KEY", "YOUR_REST_API_KEY")

def send_push_notification(heading, content, target_url=None):
    """
    Sends a push notification via the OneSignal REST API.
    In ZenTara, you would call this inside the app when a Critical Alert triggers.
    """
    url = "https://api.onesignal.com/notifications"
    
    headers = {
        "accept": "application/json",
        "Authorization": f"Basic {REST_API_KEY}",
        "content-type": "application/json"
    }
    
    payload = {
        "app_id": APP_ID,
        "included_segments": ["Subscribed Users"],  # Send to all subscribed devices
        "headings": {"en": heading},
        "contents": {"en": content},
        "name": "ZenTara System Alert"
    }
    
    if target_url:
        # Where the user will go when they tap the notification
        payload["url"] = target_url

    print(f"Sending notification: '{heading}' ...")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            print("✅ Push notification sent successfully!")
            print(f"Response: {response.json()}")
            return True
        else:
            print(f"❌ Failed to send notification. Status code {response.status_code}")
            print(f"Error details: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception occurred: {e}")
        return False


if __name__ == "__main__":
    print("Testing ZenTara Push Notifications")
    print("-" * 40)
    print("NOTE: Make sure you have substituted YOUR_ONESIGNAL_APP_ID")
    print("      and YOUR_REST_API_KEY in this file or ENV defaults.")
    
    # Example: Send a critical SLA alert
    send_push_notification(
        heading="Critical 🚨: FedEx Deadline",
        content="Claim filing window for shipment #FX-8832 closes in 24 hours.",
        target_url="https://your-zentara-app.onrender.com/alerts"
    )
