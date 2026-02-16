#!/usr/bin/env python3
"""
Fix subscriber email via API endpoint.
Usage: python fix_email_via_api.py
"""
import requests
import os
from getpass import getpass

# Configuration
BASE_URL = "https://knowledgeinchain.com"
OLD_EMAIL = "dperez-enciso@ iberdrola.es"
NEW_EMAIL = "dperez-enciso@iberdrola.es"

def main():
    # Get dashboard password
    password = os.getenv("DASHBOARD_PASSWORD") or getpass("Dashboard password: ")

    # Login first to get token
    print("Logging in...")
    login_response = requests.post(
        f"{BASE_URL}/dashboard/login",
        data={"password": password}
    )

    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.text}")
        return

    # Get cookie from login response
    cookies = login_response.cookies

    # Update email
    print(f"\nUpdating email:")
    print(f"  Old: {OLD_EMAIL}")
    print(f"  New: {NEW_EMAIL}")

    update_response = requests.patch(
        f"{BASE_URL}/api/dashboard/subscribers/update-email",
        json={
            "old_email": OLD_EMAIL,
            "new_email": NEW_EMAIL
        },
        cookies=cookies
    )

    if update_response.status_code == 200:
        result = update_response.json()
        print(f"\n✓ {result['message']}")
    else:
        print(f"\n❌ Update failed: {update_response.text}")

if __name__ == "__main__":
    main()
