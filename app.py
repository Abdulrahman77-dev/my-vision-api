from fastapi import FastAPI, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
import moondream as md
from PIL import Image
import io
import base64
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

class ImageData(BaseModel):
    image_base64: str
    prompt: str

@app.post("/analyze")
async def analyze(data: ImageData, api_key: str = Security(get_api_key)):
    try:
        image_bytes = base64.b64decode(data.image_base64)
        image = Image.open(io.BytesIO(image_bytes))
        encoded_image = model.encode_image(image)
        answer = model.query(encoded_image, data.prompt)["answer"]
        return {"result": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
