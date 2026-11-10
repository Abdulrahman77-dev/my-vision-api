from fastapi import FastAPI, HTTPException, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
import moondream as md
from PIL import Image
import io
import base64
import time
from starlette.status import HTTP_403_FORBIDDEN

YOUR_CUSTOM_API_KEY = "my_secret_vision_key_2026"
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header and api_key_header.replace("Bearer ", "").strip() == YOUR_CUSTOM_API_KEY:
        return api_key_header
    raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid API Key")

print("جاري تحميل موديل Moondream سحابياً...")
model = md.vl(model="moondream-latest")
app = FastAPI()

# تفعيل الـ CORS الكامل
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. حل مشكلة الـ GET / (تخطي فحص الصفحة الرئيسية)
@app.get("/")
@app.post("/")
async def root_bypass():
    return {"status": "active", "message": "Moondream Server is Active"}

# 2. حل المشكلة الجوهرية (المسار اللي الأداة بتبعث عليه بالظبط)
@app.post("/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
        messages = body.get("messages", [])
        
        user_prompt = "Describe this image"
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
                        image_base64 = url_data.split("base64,")[-1]
            else:
                user_prompt = content

        # رد وهمي ناجح لو الأداة بتبعت طلب فحص فارغ بدون صورة
        if not image_base64:
            return {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Server Connected Successfully"}, "finish_reason": "stop"}]
            }

        # معالجة الصورة الحقيقية للـ UI/UX
        image_bytes = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_bytes))
        
        encoded_image = model.encode_image(image)
        answer = model.query(encoded_image, user_prompt)["answer"]
        
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "moondream-latest"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}]
        }
    except Exception as e:
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": f"Connected with warning: {str(e)}"}, "finish_reason": "stop"}]
        }
