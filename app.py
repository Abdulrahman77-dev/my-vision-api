from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import json
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/chat/completions")
async def debug_endpoint(request: Request):
    # 1. قراءة البيانات الخام اللي الأداة بعتاها
    raw_body = await request.body()
    body_str = raw_body.decode("utf-8", errors="ignore")
    
    print("\n" + "="*50)
    print("🚨 [1] HEADERS المبعوتة من الأداة:")
    print(dict(request.headers))
    
    print("\n🚨 [2] BODY البيانات المبعوتة من الأداة (أول 1000 حرف):")
    # بنطبع أول 1000 حرف بس عشان منملاش الشاشة بكود الصورة
    print(body_str[:1000]) 
    print("="*50 + "\n")

    # 2. هنرجع رد تجريبي ثابت نشوف الأداة هتقراه ولا لا
    response_payload = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "moondream-latest",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "TEST_SUCCESS_123"
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
    }
    
    print("🚨 [3] الرد اللي السيرفر بعته للأداة:")
    print(json.dumps(response_payload))
    return response_payload
