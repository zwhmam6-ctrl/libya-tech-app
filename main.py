from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import httpx
import os

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "qwen/qwen-2.5-7b-instruct"


class ChatRequest(BaseModel):
    message: str
    history: list = []


@app.post("/chat")
async def chat(req: ChatRequest):
    if not API_KEY:
        return {"reply": "خطأ: لم يتم العثور على مفتاح API. تأكد من ملف .env"}

    messages = req.history + [{"role": "user", "content": req.message}]

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "temperature": 0.4,
                "max_tokens": 700,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "أنت مساعد ذكي. اتبع هذه القواعد بصرامة: "
                            "1) رد حصراً باللغة العربية الفصحى أو العامية، ولا تستخدم أي حرف أو كلمة "
                            "من لغة أخرى (لا صينية، لا إنجليزية إلا للمصطلحات التقنية الضرورية). "
                            "2) اجعل ردودك واضحة ومباشرة ومختصرة قدر الإمكان دون إخلال بالمعنى. "
                            "3) لا تكرر نفس الفكرة بصياغات مختلفة. "
                            "كن ودوداً ومفيداً."
                        ),
                    }
                ] + messages,
            },
        )
        data = response.json()

    try:
        reply = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        reply = f"صار خطأ من الخادم: {data}"

    return {"reply": reply}


app.mount("/", StaticFiles(directory="static", html=True), name="static")