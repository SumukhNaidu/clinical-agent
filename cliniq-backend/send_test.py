import requests
url='http://127.0.0.1:8005/upload'
with open('temp_uploads/test_upload.pdf','rb') as f:
    files={'file':('test_upload.pdf', f, 'application/pdf')}
    r=requests.post(url, files=files)
    print('status', r.status_code)
    print('headers', r.headers)
    print('text', r.text)
    print('content repr', repr(r.content))
