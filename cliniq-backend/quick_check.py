
import requests
import time

for i in range(5):
    try:
        response = requests.get("http://localhost:8005/health", timeout=2)
        if response.status_code == 200:
            print(f"Backend is UP! Status: {response.status_code}")
            break
        else:
            print(f"Attempt {i+1}: Status {response.status_code}")
    except Exception as e:
        print(f"Attempt {i+1}: Not ready yet - {e}")
        time.sleep(2)
else:
    print("Backend may still be starting...")
