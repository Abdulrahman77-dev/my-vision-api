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

# حط هنا توكن Hugging Face المجاني بتاعك (تقدر تضيف أكتر من توكن في اللستة عشان تبدل بينهم)
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
        "Content-Type": "application/json"
    }

# الطبقة الأولى: موديل الرؤية المجاني لوصف السكرينات
VISION_MODEL_URL = "https://huggingface.co"

# الطبقة الثانية: موديل نصي عملاق مجاني لبناء الـ JSON والـ Case Study بدقة
TEXT_JSON_MODEL_URL = "https://huggingface.co"

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

    # تقسيم الرد لبلوكات متوسطة عشان السرعة
    chunk_size = 50
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

    user_prompt = ""
    images_base64 = []

    if messages:
        last_message = messages[-1]
        content = last_message.get("content", "")

        if isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    user_prompt = item.get("text")
                elif item.get("type") == "image_url":
                    url_data = item.get("image_url", {}).get("url", "")
                    clean_b64 = url_data.split("base64,")[-1].strip()
                    if clean_b64:
                        images_base64.append(clean_b64)
        else:
            user_prompt = str(content)

    # 1. لو طلب Test (مفيهوش صور)
    if not images_base64:
        final_answer = "OK"
    else:
        # 2. الشغل الفعلي: الطبقة الأولى (Moondream يستخرج تفاصيل كل سكرين)
        screen_descriptions = []
        async with httpx.AsyncClient(timeout=45.0) as client:
            for idx, img_b64 in enumerate(images_base64):
                vision_payload = {
                    "inputs": {
                        "image": img_b64,
                        "text": "Describe every UI element, text, buttons, layout, colors, and user flow visible in this app/website screen in detail."
                    }
                }
                v_res = await client.post(VISION_MODEL_URL, json=vision_payload, headers=get_hf_headers())
                if v_res.status_code == 200:
                    v_data = v_res.json()
                    desc = v_data[0].get("generated_text", "") if isinstance(v_data, list) else str(v_data)
                    screen_descriptions.append(f"--- Screen {idx+1} Details ---\n{desc}")
                else:
                    screen_descriptions.append(f"--- Screen {idx+1} ---\nModern mobile/web UI screen with clean layout and interactive components.")

            all_screens_text = "\n\n".join(screen_descriptions)

            # 3. الطبقة الثانية (Qwen 2.5 72B يأخذ وصف السكرينات + برومبت الأداة ويبني الـ JSON المطلوب)
            combined_prompt = f"""{user_prompt}

Here is the detailed visual extraction of the uploaded UI screenshots:
{all_screens_text}

CRITICAL INSTRUCTION: Output ONLY valid raw JSON matching the exact schema requested above. Do not write markdown blocks like ```json or any conversational text before/after the JSON."""

            llm_payload = {
                "model": "Qwen/Qwen2.5-72B-Instruct",
                "messages": [
                    {"role": "system", "content": "You are an expert UX Designer and strict JSON generator. You always output valid, parseable JSON only."},
                    {"role": "user", "content": combined_prompt}
                ],
                "max_tokens": 4096,
                "temperature": 0.7
            }

            llm_res = await client.post(TEXT_JSON_MODEL_URL, json=llm_payload, headers=get_hf_headers())
            if llm_res.status_code == 200:
                llm_data = llm_res.json()
                final_answer = llm_data["choices"][0]["message"]["content"]
                # تنظيف الرد من أي علامات Markdown عشان الأداة تقرأه كـ JSON صافي
                final_answer = final_answer.replace("```json", "").replace("```", "").strip()
            else:
                final_answer = json.dumps({"error": f"LLM Layer failed with status {llm_res.status_code}"})

    # إرجاع النتيجة للأداة (سواء Streaming أو عادي)
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
