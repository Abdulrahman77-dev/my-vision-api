from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import moondream as md
from PIL import Image
import io
import base64
import time

print("جاري تحميل موديل Moondream سحابياً...")
model = md.vl(model="moondream-latest")
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.options("/{catchall:path}")
async def keep_alive_options():
    return {"message": "OK"}

@app.get("/")
@app.post("/")
async def root_bypass():
    return {"status": "active", "message": "Moondream Server is Active"}

@app.post("/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
        messages = body.get("messages", [])
        
        user_prompt = "Describe this UI screenshot in detail for a UX case study."
        image_base64 = None
        
        if messages:
            last_message = messages[-1]
            content = last_message.get("content", "")
            
            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "text":
                        user_prompt = item.get("text")
                    elif item.get("type") == "image_url":
                        url_data = item.get("image_url", {}).get("url", "")
                        if "base64," in url_data:
                            image_base64 = url_data.split("base64,")[-1]
                        else:
                            image_base64 = url_data
            else:
                user_prompt = content

        # التصحيح العبقري: فحص لو الصورة ممسوحة أو مبعوتة فاضية بدون تعليق الكود
        if not image_base64 or len(str(image_base64).strip()) < 10:
            return {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model", "moondream-latest"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Ready"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}
            }

        # تنظيف وفك تشفير الصورة الحقيقية
        image_base64 = str(image_base64).replace("data:image/png;base64,", "")
        image_base64 = image_base64.replace("data:image/jpeg;base64,", "")
        image_base64 = image_base64.replace("data:image/jpg;base64,", "")
        image_base64 = image_base64.strip()

        image_bytes = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_bytes))
        
        # معالجة الصورة عبر الموديل السحابي الخاص بك
        encoded_image = model.encode_image(image)
        answer = model.query(encoded_image, user_prompt)["answer"]
        
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "moondream-latest"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": answer
                    },
                    "logprobs": None,
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(user_prompt) // 4 + 1000,
                "completion_tokens": len(answer) // 4,
                "total_tokens": (len(user_prompt) // 4 + 1000) + (len(answer) // 4)
            }
        }
    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "moondream-latest",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": f"Error: {str(e)}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }
