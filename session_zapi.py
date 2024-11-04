import requests 
import base64
from base64 import b64decode
import json
import io
from uuid import uuid4

API_URL = "https://api.zyte.com/v1/extract"
API_KEY = "be8e0737c3664421a37adc8e0a48d9cf" #Enter_your_api_key

session_id = str(uuid4())

response = requests.post(API_URL, auth=(API_KEY, ''), json={
  "browserHtml": True,
  "url": "https://www.yelp.com/search/snippet?find_desc=LIVe%20music&find_loc=Los%20Angeles%2C%20CA%2C%20USA&start=1180&parent_request_id=cff2259236faa40b&request_origin=user",
  "session": {
        "id": session_id
    }
})

data = json.loads(response.text)
print(data)
print("initial request ------" +  str(data["statusCode"]))
for i in range(1):
    response1 = requests.post(API_URL, auth=(API_KEY, ''), json={
        "url": "https://www.yelp.com/search/snippet?find_desc=LIVe%20music&find_loc=Los%20Angeles%2C%20CA%2C%20USA&start=1180&parent_request_id=cff2259236faa40b&request_origin=user",
        'httpResponseBody': True,
        "session": {
            "id": session_id
        }
    })
    print(response1.json())
    response_output = response1.json()['httpResponseBody']
    print(response1.status_code)
    decoded_output = b64decode(response_output)
    name = str(i) +  "_yelp.html"
    with open(name, 'wb') as f:
        f.write(decoded_output)

print("final request ------" +  str(response1.status_code))