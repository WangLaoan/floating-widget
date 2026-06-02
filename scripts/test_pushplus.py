"""PushPlus 推送连通性测试"""
import json
import urllib.request

PUSHPLUS_TOKEN = "f28d79309c2f4d1cb7d80cb06b7aa472"
PUSHPLUS_API = "http://www.pushplus.plus/send"

data = json.dumps({
    "token": PUSHPLUS_TOKEN,
    "title": "ETF小组件 测试",
    "content": "PushPlus 推送测试成功! 如果你在微信收到这条消息, 说明通道正常。",
}).encode("utf-8")

req = urllib.request.Request(PUSHPLUS_API, data=data, headers={
    "Content-Type": "application/json",
})

try:
    resp = urllib.request.urlopen(req, timeout=10)
    print("状态:", resp.status)
    print("响应:", resp.read().decode("utf-8"))
except Exception as e:
    print("推送失败:", e)
