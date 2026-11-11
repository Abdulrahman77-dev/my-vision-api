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

# ⚠️ ضع بيانات حسابك في Cloudflare هنا
CF_ACCOUNT_ID = "b1c768ceb00a58098802ee6b80a948aa".strip()
CF_API_TOKEN = "cfut_3GKQSspdDSfS1JIfYkhPXzMrvU4A3cAduGCKu9fc2f13311b".strip()

CF_BASE_URL = f"https://cloudflare.com{CF_ACCOUNT_ID}/ai/run"
VISION_MODEL = "@cf/meta/llama-3.2-11b-vision-instruct"
JSON_MODEL = "@cf/qwen/qwen2.5-72b-instruct"

HEADERS = {
    "Authorization": f"Bearer {CF_API_TOKEN}",
    "Content-Type": "application/json"
}

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

    # 1. طلب الـ Test
    if not images_base64:
        final_answer = "OK"
    else:
        screen_descriptions = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            # الطبقة الأولى: استخراج وصف كل سكرين باستخدام Llama 3.2 Vision
            for idx, img_b64 in enumerate(images_base64):
                vision_payload = {
                    "prompt": "Analyze this UI/UX design screen in thorough detail. List all visible text, buttons, navigation elements, color hex codes, layout structure, and user flow.",
                    "image": list(bytes.fromhex("")) if False else img_b64 # Cloudflare يقبل base64 مباشرة في صيغة OpenAI أو مصفوفة بايتات
                }
                # استخدام نقطة اتصال OpenAI المتوافقة داخل Cloudflare مباشرة للرؤية
                v_openai_payload = {
                    "model": VISION_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Extract every visible text, UI component, color hex code, layout hierarchy, and UX purpose of this screen in detail."},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                            ]
                        }
                    ],
                    "max_tokens": 1024
                }
                v_res = await client.post(
                    f"https://cloudflare.com{CF_ACCOUNT_ID}/ai/v1/chat/completions",
                    json=v_openai_payload,
                    headers=HEADERS
                )
                print(f"🚨 CF Vision Status (Screen {idx+1}): {v_res.status_code}")

                if v_res.status_code == 200:
                    v_data = v_res.json()
                    desc = v_data["choices"]["message"]["content"]
                    screen_descriptions.append(f"--- Screen {idx+1} Details ---\n{desc}")
                else:
                    print(f"🚨 CF Vision Error: {v_res.text[:300]}")
                    screen_descriptions.append(f"--- Screen {idx+1} ---\nClean modern UI screen.")

            all_screens_text = "\n\n".join(screen_descriptions)

            # الطبقة الثانية: بناء الـ JSON الصارم باستخدام Qwen 2.5 72B
            combined_prompt = f"""{user_prompt}

Here is the visual extraction of the uploaded UI screenshots:
{all_screens_text}

CRITICAL INSTRUCTION: Output ONLY valid raw JSON containing the exact "sections" array requested above. Start immediately with {{ and end with }}. No markdown."""

            llm_payload = {
                "model": JSON_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a senior UX designer and strict JSON generator. Output valid parseable JSON only."},
                    {"role": "user", "content": combined_prompt}
                ],
                "max_tokens": 4096,
                "temperature": 0.7
            }

            llm_res = await client.post(
                f"https://cloudflare.com{CF_ACCOUNT_ID}/ai/v1/chat/completions",
                json=llm_payload,
                headers=HEADERS
            )
            print(f"🚨 CF LLM Status: {llm_res.status_code}")

            if llm_res.status_code == 200:
                llm_data = llm_res.json()
                raw_text = llm_data["choices"]["message"]["content"]
                start_idx = raw_text.find("{")
                end_idx = raw_text.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    final_answer = raw_text[start_idx:end_idx+1]
                else:
                    final_answer = raw_text
                print(f"🚨 Success JSON Preview: {final_answer[:200]}")
            else:
                print(f"🚨 CF LLM Error: {llm_res.text[:300]}")
                final_answer = json.dumps({"error": f"CF Error {llm_res.status_code}"})

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
