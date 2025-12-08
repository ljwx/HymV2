import json
import urllib
from urllib import request


class NetworkRequest:

    def __init__(self, domain: str):
        self.domain = domain

    def get(self, api: str):
        url = self.domain + api
        response = urllib.request.urlopen(url)
        status_code = response.getcode()
        
        if not (200 <= status_code < 300):
            print(f"请求失败，状态码: {status_code}")
            return None
        
        try:
            data = json.loads(response.read().decode())
            return data
        except Exception as e:
            print(f"JSON 解析失败: {e}")
            return None

    def post(self, api: str, data: dict):
        url = self.domain + api
        json_data = json.dumps(data).encode('utf-8')
        req = request.Request(url, data=json_data, headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        status_code = response.getcode()
        
        if not (200 <= status_code < 300):
            print(f"请求失败，状态码: {status_code}")
            return None
        
        try:
            result = json.loads(response.read().decode())
            return result
        except Exception as e:
            print(f"JSON 解析失败: {e}")
            return None


#print(NetworkRequest("https://kn.codemao.cn/").get("manifest.json"))