from fastapi.testclient import TestClient
import api

client = TestClient(api.app)

with open('temp_uploads/test_upload.pdf','rb') as f:
    files={'file':('test_upload.pdf', f, 'application/pdf')}
    resp = client.post('/upload', files=files)
    print('status', resp.status_code)
    print('headers', resp.headers)
    print('text', resp.text)
    print('json?', None)
    try:
        print('json body:', resp.json())
    except Exception as e:
        print('json parse error', e)
