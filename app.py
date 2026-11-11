from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import json
import time
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ⚠️ حط هنا توكن Hugging Face المجاني بتاعك (تقدر تضيف أكتر من توكن للتبديل التلقائي)
HF_TOKENS = [
    "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"
]
current_token_idx = 0

def get_hf_headers():
    global current_token_idx
    token = HF_TOKENS[current_token_idx % len(HF_TOKENS)]
    current_token_idx += 1
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

# الرابط الرسمي الموحد لـ Hugging Face Inference Providers
HF_ROUTER_URL = "https://huggingface.co"

# موديل رؤية مجاني وذكي جداً بيفهم الصور وبيطلع JSON سليم 100%
VISION_JSON_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"

@app.options("/{catchall:path}")
async def keep_alive_options():
    return {"message": "OK"}

async def stream_response_generator(text: str, model_name: str):
    chat_id = f"chatcmpl-{int(time.time())}"
    created_time = int(time.time())

    first_chunk = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": model_name,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]
    }
    yield f"data: {json.dumps(first_chunk)}\n\n"

    chunk_size = 100
    for i in range(0, len(text), chunk_size):
        part = text[i:i+chunk_size]
        chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model_name,
            "choices": [{"index": 0, "delta": {"content": part}, "finish_reason": None}]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.01)

    end_chunk = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": model_name,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    }
    yield f"data: {json.dumps(end_chunk)}\n\n"
    yield "data: [DONE]\n\n"

@app.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    is_stream = body.get("stream", False)
    model_name = body.get("model", "moondream")

    # فحص هل ده طلب Test فاضي (بدون صور)
    has_image = False
    if messages and isinstance(messages[-1].get("content"), list):
        for item in messages[-1]["content"]:
            if item.get("type") == "image_url":
                has_image = True
                break

    if not has_image:
        final_answer = "OK"
    else:
        # إضافة تعليمات صارمة في السيستم لضمان خروج JSON سليم يحتوي على sections
        enhanced_messages = [
            {
                "role": "system",
                "content": "You are a senior UX designer and strict JSON generator. Output ONLY valid raw JSON starting with { and ending with }, containing the exact 'sections' array requested. Do not use markdown code blocks."
            }
        ] + messages

        hf_payload = {
            "model": VISION_JSON_MODEL,
            "messages": enhanced_messages,
            "max_tokens": 4096,
            "temperature": 0.7,
            "stream": False
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(HF_ROUTER_URL, json=hf_payload, headers=get_hf_headers())
            print(f"🚨 HF Router Status: {res.status_code}")

            if res.status_code == 200:
                res_data = res.json()
                raw_text = res_data["choices"][0]["message"]["content"]
                # تنظيف الرد واستخراج الـ JSON الصافي من أول { لآخر }
                start_idx = raw_text.find("{")
                end_idx = raw_text.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    final_answer = raw_text[start_idx:end_idx+1]
                else:
                    final_answer = raw_text
                print(f"🚨 Success JSON Preview: {final_answer[:200]}")
            else:
                print(f"🚨 HF Error Body: {res.text[:500]}")
                final_answer = json.dumps({"error": f"HF Router Error {res.status_code}", "details": res.text[:200]})

    if is_stream:
        return StreamingResponse(
            stream_response_generator(final_answer, model_name),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )

    return JSONResponse(content={
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": final_answer}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": len(final_answer) // 4, "total_tokens": 200}
    })
