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

import urllib.parse
import random

SYSTEM_PROMPT_GENERAL = (
    "أنت 'صاحبك الليبي' 🇱🇾 — صديق رفيق وودود جداً يتحدث باللهجة الليبية العامية الأصيلة والمحبوبة.\n"
    "قواعد جازمة وخاصة بيك:\n"
    "1) ممنوع منعاً باتاً استخدام عبارات الاعتذار الرسمية أو التهرب مثل: 'أعتذر، لكن يمكنني مساعدتك إذا وضعت...' أو أي أسلوب جامد.\n"
    "2) لما يقولك المستخدم أي تحية أو استفسار عام مثل (شن الامور، شن الجو، قاعد، كيف حالك، شنو الأخبار)، جاوبه فوراً بروح دافئة ومرحة (مثال: 'أهلاً يا غالي! مية مية والحمد لله، شن صاير معاك؟ هدرزلي!').\n"
    "3) تكلم كـ صديق مقرب وحميم (صاحبك وتارسك). هدرز معاه في كل الموضوعات وبأسلوب ليبي طبيعي وسلس.\n"
    "4) استخدم كلمات ليبية دافئة مثل: (يا غالي، يا خوي، شن الجو، مية مية، باهي، هلبا، توا، راهو، صحيت)."
)

SYSTEM_PROMPT_CODE = (
    "أنت 'المبرمج الذكي' 💻 🇱🇾 — خبير متمرس في تطوير البرمجيات وكتابة الأكواد بجميع لغات البرمجة (Python, JavaScript, HTML/CSS, C++, SQL, Java... إلخ).\n"
    "قواعد الإجابة:\n"
    "1) اكتب دائماً الكود داخل كتل كود Markdown منسقة مع تحديد اسم اللغة (مثال: ```python أو ```javascript).\n"
    "2) اشرح الكود وطريقة عمله بأسلوب عربي/ليبي واضح ومبسط وصديق للمبرمجين.\n"
    "3) قدّم نصائح للمقابلة والتحسين وأداء الكود وإصلاح الأخطاء (Debugging) مع أمثلة عملية."
)

SYSTEM_PROMPT_WRITER = (
    "أنت 'كاتب المحتوى والترجمة' 📝 🇱🇾 — صانع محتوى محترف ومترجم دقيق وخبير في صياغة المقالات ورسائل البريد والتقارير.\n"
    "قواعد الإجابة:\n"
    "1) قدّم كتابة متقنة ومنسقة بعناية باستخدام العناوين القوائم والنقاط.\n"
    "2) ترجم النصوص بدقة وبراعة لغوية عالية بين العربي والإنجليزية واللغات الأخرى."
)

SYSTEM_PROMPT_LIBYA = (
    "أنت 'مستشار المعاملات والأسواق الليبية' 🇱🇾 💵 — خبير ودود ومتخصص في المعاملات الإدارية، المصرفية، والمالية في ليبيا.\n"
    "قواعد الإجابة:\n"
    "1) قدّم معلومات دقيقة ومبسطة حول الأوراق المطلوبة وخطوات المعاملات (السجل التجاري، الجوازات، رخص القيادة، المنظومات المصرفية).\n"
    "2) ساعد المستخدم في حسابات الدينار والعملة، البطاقات الإلكترونية، واستيراد البضائع الشائعة بأسلوب ليبي سهل ومفيد جداً."
)

SYSTEM_PROMPTS = {
    "general": SYSTEM_PROMPT_GENERAL,
    "code": SYSTEM_PROMPT_CODE,
    "writer": SYSTEM_PROMPT_WRITER,
    "libya_services": SYSTEM_PROMPT_LIBYA
}

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
    mode: Optional[str] = "general"

class ImageGenRequest(BaseModel):
    prompt: str

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

# --- Chat & Image Endpoints ---

@app.post("/generate-image")
async def generate_image(req: ImageGenRequest, user: dict = Depends(get_current_user)):
    user_prompt = req.prompt.strip()
    if not user_prompt:
        raise HTTPException(status_code=400, detail="الوصف مطلوب لتوليد الصورة")

    # Refine prompt using LLM if API_KEY exists
    english_prompt = user_prompt
    if API_KEY:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": MODEL,
                        "temperature": 0.5,
                        "messages": [
                            {"role": "system", "content": "Translate the user's image description to a detailed, high-quality English image generation prompt (be concise, max 30 words, vivid details, masterwork style). Return ONLY the translated English text, nothing else."},
                            {"role": "user", "content": user_prompt}
                        ]
                    }
                )
                data = resp.json()
                english_prompt = data["choices"][0]["message"]["content"].strip()
        except Exception:
            english_prompt = user_prompt

    encoded_prompt = urllib.parse.quote(english_prompt)
    seed = random.randint(1000, 99999)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed={seed}"
    return {"image_url": image_url, "prompt": user_prompt}


@app.post("/chat")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    if not API_KEY:
        return {"reply": "خطأ: لم يتم العثور على مفتاح API في ملف .env"}

    mode = req.mode or "general"
    user_msg = req.message.strip()

    conv_id = req.conversation_id
    if not conv_id:
        conv_id = "c_" + uuid.uuid4().hex[:12]
        title = user_msg[:30] + ("…" if len(user_msg) > 30 else "")
        db.create_conversation(conv_id, user["id"], title)
    else:
        past_msgs = db.get_conversation_messages(conv_id, user["id"])
        if len(past_msgs) == 0:
            title = user_msg[:30] + ("…" if len(user_msg) > 30 else "")
            db.update_conversation_title(conv_id, user["id"], title)

    # Save user message to database
    db.add_message(conv_id, "user", req.message)

    # Handle image mode or explicit image triggers
    is_image_req = mode == "image" or user_msg.startswith(("ارسم", "صمملي صورة", "توليد صورة", "صورة لـ", "/image", "صمملي"))
    if is_image_req:
        clean_prompt = user_msg
        for prefix in ["ارسم", "صمملي صورة", "توليد صورة", "صورة لـ", "/image", "صمملي"]:
            if clean_prompt.startswith(prefix):
                clean_prompt = clean_prompt[len(prefix):].strip()
        if not clean_prompt:
            clean_prompt = user_msg

        # Refine prompt into English for image generator
        english_prompt = clean_prompt
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": MODEL,
                        "temperature": 0.5,
                        "messages": [
                            {"role": "system", "content": "Translate the user's image description into a vivid, high-quality English image prompt (artistic, detailed, masterwork, 8k resolution). Return ONLY the prompt text in English."},
                            {"role": "user", "content": clean_prompt}
                        ]
                    }
                )
                data = resp.json()
                english_prompt = data["choices"][0]["message"]["content"].strip()
        except Exception:
            english_prompt = clean_prompt

        encoded = urllib.parse.quote(english_prompt)
        seed = random.randint(1000, 99999)
        img_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&seed={seed}"
        
        reply = f"![{clean_prompt}]({img_url})\n\nتفضل يا غالي! هذه الصورة المولدة بالذكاء الاصطناعي حسب طلبك: **\"{clean_prompt}\"** 🎨✨"
        
        db.add_message(conv_id, "assistant", reply)
        return {"reply": reply, "conversation_id": conv_id, "mode": "image", "image_url": img_url}

    # Select proper system prompt
    system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPT_GENERAL)

    # Get conversation history from DB
    past_msgs = db.get_conversation_messages(conv_id, user["id"])
    formatted_messages = [{"role": "system", "content": system_prompt}]
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
                "max_tokens": 1200 if mode == "code" else 700,
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

    return {"reply": reply, "conversation_id": conv_id, "mode": mode}


@app.get("/")
async def read_index():
    from fastapi.responses import FileResponse
    response = FileResponse("static/index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

PRIVACY_POLICY_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>سياسة الخصوصية — تقنية ليبية</title>
<style>
  body { font-family: 'Tajawal', sans-serif; background:#0b0e14; color:#eef0f4; padding:40px 20px; line-height:1.9; max-width:700px; margin:auto; }
  h1 { color:#d4a054; }
  h2 { color:#d4a054; margin-top:30px; font-size:18px; }
  p, li { color:#c5cad6; font-size:15px; }
</style>
</head>
<body>
<h1>سياسة الخصوصية</h1>
<p>آخر تحديث: 2026</p>

<h2>ما هي البيانات التي نجمعها؟</h2>
<p>تطبيق "تقنية ليبية" لا يخزّن محادثاتك على أي خادم أو قاعدة بيانات دائمة. الرسائل التي ترسلها تُعالج فوراً وتُرسل إلى مزوّد نموذج الذكاء الاصطناعي (Qwen عبر OpenRouter) للحصول على رد، ثم لا يتم الاحتفاظ بها.</p>

<h2>هل تُشارك بياناتي مع أطراف أخرى؟</h2>
<p>نعم، محتوى رسائلك يُرسل إلى مزوّد النموذج (OpenRouter / Qwen) لأغراض توليد الرد فقط، وفق سياسة الخصوصية الخاصة بهم.</p>

<h2>هل يتم تشفير الاتصال؟</h2>
<p>نعم، جميع الاتصالات بين التطبيق والخادم مشفّرة عبر HTTPS.</p>

<h2>حقوقك</h2>
<ul>
<li>يمكنك التوقف عن استخدام التطبيق في أي وقت دون أي التزام.</li>
<li>لا نطلب أي معلومات شخصية حساسة لاستخدام المحادثة الأساسية.</li>
</ul>

<h2>تواصل معنا</h2>
<p>لأي استفسار بخصوص الخصوصية، يمكنك التواصل عبر صفحة المشروع.</p>
</body>
</html>
"""

@app.get("/privacy")
async def privacy_policy():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=PRIVACY_POLICY_HTML)                                                                                                                                                                                                               
app.mount("/", StaticFiles(directory="static", html=True), name="static")