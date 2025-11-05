#!/usr/bin/env python3
"""
Helper script to list Box users in your enterprise.
This helps you find your user ID for as-user authentication.
"""

from boxsdk import Client, JWTAuth

# Load JWT config
jwt_config_file = "box_config.json"
auth = JWTAuth.from_settings_file(jwt_config_file)
client = Client(auth)

print("Fetching users from your Box enterprise...\n")

try:
    # Get all users in the enterprise
    users = client.users(limit=100)

    print(f"{'User ID':<20} {'Name':<30} {'Email':<50}")
    print("=" * 100)

    for user in users:
        print(f"{user.id:<20} {user.name:<30} {user.login:<50}")

    print("\n" + "=" * 100)
    print("\nTo use a user for as-user authentication, add this to your config:")
    print("\nbox_crawler:")
    print("  as_user_id: <USER_ID_FROM_ABOVE>")
    print("\nTip: Use an admin user's ID for full enterprise access.")

except Exception as e:
    print(f"Error: {e}")
    print("\nNote: The service account needs 'Manage users' permission to list users.")
    print("Alternative: You can find your user ID by:")
    print("1. Go to https://app.box.com/developers/console")
    print("2. Select your app → 'General' tab")
    print("3. Click 'Test' → 'View API calls'")
    print("4. Look for your user ID in the responses")
