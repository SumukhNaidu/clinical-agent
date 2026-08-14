
import requests

try:
    response = requests.get("http://localhost:3002/")
    print(f"Status: {response.status_code}")
    print("First 500 chars of response:")
    print(response.text[:500])
except Exception as e:
    print(f"Error: {e}")
