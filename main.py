from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import httpx
import os
import uuid
from typing import Optional, List

import database as db
import auth

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "openai/gpt-4o-mini"

SYSTEM_PROMPT = (
    "أنت 'صاحبك الليبي' 🇱🇾 — صديق رفيق وودود جداً يتحدث باللهجة الليبية العامية الأصيلة والمحبوبة.\n"
    "قواعد جازمة وخاصة بيك:\n"
    "1) ممنوع منعاً باتاً استخدام عبارات الاعتذار الرسمية أو التهرب مثل: 'أعتذر، لكن يمكنني مساعدتك إذا وضعت...' أو أي أسلوب جامد.\n"
    "2) لما يقولك المستخدم أي تحية أو استفسار عام مثل (شن الامور، شن الجو، قاعد، كيف حالك، شنو الأخبار)، جاوبه فوراً بروح دافئة ومرحة (مثال: 'أهلاً يا غالي! مية مية والحمد لله، شن صاير معاك؟ هدرزلي!').\n"
    "3) تكلم كـ صديق مقرب وحميم (صاحبك وتارسك). هدرز معاه في كل الموضوعات وبأسلوب ليبي طبيعي وسلس.\n"
    "4) استخدم كلمات ليبية دافئة مثل: (يا غالي، يا خوي، شن الجو، مية مية، باهي، هلبا، توا، راهو، صحيت)."
)

# --- Pydantic Models ---

class RegisterRequest(BaseModel):
    name: str
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class NewConvRequest(BaseModel):
    title: Optional[str] = "محادثة جديدة"

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

class GoogleLoginRequest(BaseModel):
    google_uid: str
    name: str
    email: str
    avatar: Optional[str] = ""

# --- Auth Helper Dependency ---

def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="يتطلب تسجيل الدخول")
    token = authorization.split(" ")[1]
    user_id = auth.decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="رمز الجلسة غير صالح أو منتهي الصلاحية")
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="المستخدم غير موجود")
    return user

# --- Auth Endpoints ---

@app.post("/register")
async def register(req: RegisterRequest):
    if len(req.username.strip()) < 3:
        return {"error": "اسم المستخدم يجب أن يكون 3 حروف على الأقل"}
    if len(req.password) < 4:
        return {"error": "كلمة المرور يجب أن تكون 4 خانات على الأقل"}

    existing = db.get_user_by_username(req.username)
    if existing:
        return {"error": "اسم المستخدم مستعمل بالفعل، اختر اسماً آخر"}

    pwd_hash = auth.hash_password(req.password)
    user = db.create_user(name=req.name.strip(), username=req.username, password_hash=pwd_hash)
    if not user:
        return {"error": "فشل إنشاء الحساب، حاول مجدداً"}

    token = auth.create_token(user["id"])
    return {"token": token, "user": user}


@app.post("/login")
async def login(req: LoginRequest):
    user = db.get_user_by_username(req.username)
    if not user or not auth.verify_password(req.password, user["password_hash"]):
        return {"error": "اسم المستخدم أو كلمة المرور غير صحيحة"}

    token = auth.create_token(user["id"])
    user_data = {"id": user["id"], "name": user["name"], "username": user["username"]}
    return {"token": token, "user": user_data}


@app.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {"user": user}


@app.post("/google-login")
async def google_login(req: GoogleLoginRequest):
    """تسجيل الدخول أو إنشاء حساب عبر Google Firebase"""
    if not req.google_uid or not req.email:
        return {"error": "بيانات Google غير مكتملة"}
    
    user = db.create_or_get_google_user(
        google_uid=req.google_uid,
        name=req.name or req.email.split("@")[0],
        email=req.email,
        avatar=req.avatar or ""
    )
    
    if not user:
        return {"error": "فشل تسجيل الدخول بحساب Google، حاول مجدداً"}
    
    token = auth.create_token(user["id"])
    user_data = {
        "id": user["id"],
        "name": user["name"],
        "username": user.get("username", ""),
        "email": user.get("email", ""),
        "avatar": user.get("avatar", "")
    }
    return {"token": token, "user": user_data}


# --- Conversations Endpoints ---

@app.get("/conversations")
async def list_conversations(user: dict = Depends(get_current_user)):
    convs = db.get_user_conversations(user["id"])
    return {"conversations": convs}


@app.post("/conversations")
async def create_conversation(req: NewConvRequest, user: dict = Depends(get_current_user)):
    conv_id = "c_" + uuid.uuid4().hex[:12]
    title = req.title or "محادثة جديدة"
    conv = db.create_conversation(conv_id, user["id"], title)
    return {"conversation": conv}


@app.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, user: dict = Depends(get_current_user)):
    success = db.delete_conversation(conv_id, user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="المحادثة غير موجودة")
    return {"success": True}


@app.get("/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, user: dict = Depends(get_current_user)):
    msgs = db.get_conversation_messages(conv_id, user["id"])
    return {"messages": msgs}

# --- Chat Endpoint ---

@app.post("/chat")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    if not API_KEY:
        return {"reply": "خطأ: لم يتم العثور على مفتاح API في ملف .env"}

    conv_id = req.conversation_id
    if not conv_id:
        conv_id = "c_" + uuid.uuid4().hex[:12]
        title = req.message[:30] + ("…" if len(req.message) > 30 else "")
        db.create_conversation(conv_id, user["id"], title)
    else:
        # Check if conversation exists, if first message update title
        past_msgs = db.get_conversation_messages(conv_id, user["id"])
        if len(past_msgs) == 0:
            title = req.message[:30] + ("…" if len(req.message) > 30 else "")
            db.update_conversation_title(conv_id, user["id"], title)

    # Save user message to database
    db.add_message(conv_id, "user", req.message)

    # Get conversation history from DB
    past_msgs = db.get_conversation_messages(conv_id, user["id"])
    formatted_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in past_msgs:
        formatted_messages.append({"role": m["role"], "content": m["content"]})

    # Query LLM
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "temperature": 0.7,
                "max_tokens": 700,
                "messages": formatted_messages,
            },
        )
        data = response.json()

    try:
        reply = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        reply = f"صار خطأ من الخادم: {data}"

    # Save assistant reply to database
    db.add_message(conv_id, "assistant", reply)

    return {"reply": reply, "conversation_id": conv_id}


@app.get("/")
async def read_index():
    from fastapi.responses import FileResponse
    response = FileResponse("static/index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

app.mount("/", StaticFiles(directory="static", html=True), name="static")