
import requests

# Create a small test file (we'll rename it to .pdf for test)
with open("test_file.pdf", "w") as f:
    f.write("This is a test file for upload")

# Upload the file
url = "http://localhost:8000/upload"
with open("test_file.pdf", "rb") as f:
    files = {"file": f}
    try:
        response = requests.post(url, files=files)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
