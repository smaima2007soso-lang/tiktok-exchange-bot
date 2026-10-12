#!/usr/bin/env python3
# Simple TikTok task-exchange Telegram bot using only Python standard library.
# Configure BOT_TOKEN below. Never share your token publicly.
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

ADMIN_ID = 7682058663
BOT_TOKEN = "PUT_YOUR_NEW_BOT_TOKEN_HERE"  # استبدله بتوكنك الجديد
API_BASE = "https://api.telegram.org/bot{}/{}"
DATA_FILE = Path(__file__).with_name("tiktok_bot_data.json")

DEFAULT_DATA = {
    "tasks": [],
    "users": {},
    "waiting_proof": {},
    "pending": {},
    "next_task_id": 1,
    "next_proof_id": 1,
}

def load_data():
    if DATA_FILE.exists():
        try:
            with DATA_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in DEFAULT_DATA.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_DATA))

def save_data():
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def api(method, params=None, timeout=40):
    params = params or {}
    url = API_BASE.format(BOT_TOKEN, method)
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=body)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram API error"))
    return result["result"]

def send(chat_id, text, reply_markup=None):
    params = {"chat_id": chat_id, "text": text}
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    return api("sendMessage", params)

def answer_callback(callback_id, text=""):
    try:
        api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})
    except Exception:
        pass

def main_menu(user_id):
    rows = [
        [{"text": "📋 المهام المتاحة", "callback_data": "tasks"}],
        [{"text": "👤 حسابي", "callback_data": "account"}],
    ]
    if user_id == ADMIN_ID:
        rows += [
            [{"text": "➕ إضافة مهمة", "callback_data": "addtask"}],
            [{"text": "🕒 الإثباتات المعلقة", "callback_data": "pending"}],
        ]
    return {"inline_keyboard": rows}

data = load_data()

def ensure_user(user):
    uid = str(user["id"])
    data["users"].setdefault(uid, {
        "points": 0,
        "name": user.get("first_name", "مستخدم"),
        "username": user.get("username", ""),
        "done": [],
    })
    data["users"][uid]["name"] = user.get("first_name", data["users"][uid]["name"])
    data["users"][uid]["username"] = user.get("username", data["users"][uid]["username"])
    return data["users"][uid]

def show_tasks(chat_id, user_id):
    available = [t for t in data["tasks"] if t.get("active", True)
                 and str(user_id) not in t.get("completed_by", [])]
    if not available:
        send(chat_id, "لا توجد مهام متاحة حاليًا.")
        return
    for task in available[:20]:
        kb = {"inline_keyboard": [[{"text": "📩 إرسال الإثبات", "callback_data": f"proof:{task['id']}"}]]}
        send(chat_id, f"المهمة #{task['id']}\n{task['description']}\nالنقاط: {task['points']}\nنفّذ المهمة ثم اضغط إرسال الإثبات.", kb)

def add_task_prompt(chat_id):
    send(chat_id, "أرسل المهمة بهذا الشكل:\nوصف المهمة | النقاط\n\nمثال:\nتابع حساب تيك توك @example | 5\n\nأرسل /cancel للإلغاء.")

def process_message(message):
    chat = message.get("chat", {})
    user = message.get("from", {})
    if not chat or not user:
        return
    chat_id = chat["id"]
    user_id = user["id"]
    uid = str(user_id)
    udata = ensure_user(user)
    text = message.get("text", "").strip()
    photos = message.get("photo", [])
    photo_id = photos[-1]["file_id"] if photos else None

    if text == "/start":
        save_data()
        send(chat_id, "أهلًا بك في بوت تبادل مهام تيك توك.\nنفّذ المهام وأرسل إثباتًا ليُراجَع من الإدارة.", main_menu(user_id))
        return
    if text == "/cancel":
        data["waiting_proof"].pop(uid, None)
        data.pop("admin_waiting_task", None) if user_id == ADMIN_ID else None
        save_data()
        send(chat_id, "تم الإلغاء.")
        return

    if user_id == ADMIN_ID and data.get("admin_waiting_task"):
        parts = text.rsplit("|", 1)
        if len(parts) != 2:
            send(chat_id, "الصيغة غير صحيحة. أرسل: وصف المهمة | النقاط")
            return
        try:
            points = int(parts[1].strip())
            if points < 1:
                raise ValueError
        except ValueError:
            send(chat_id, "النقاط يجب أن تكون عددًا صحيحًا أكبر من صفر.")
            return
        task_id = data["next_task_id"]
        data["next_task_id"] += 1
        data["tasks"].append({"id": task_id, "description": parts[0].strip(), "points": points, "active": True, "completed_by": []})
        data["admin_waiting_task"] = False
        save_data()
        send(chat_id, f"تمت إضافة المهمة #{task_id} بنجاح.")
        return

    if uid in data["waiting_proof"]:
        task_id = data["waiting_proof"].pop(uid)
        task = next((t for t in data["tasks"] if t["id"] == task_id), None)
        if not task:
            save_data()
            send(chat_id, "المهمة غير موجودة.")
            return
        proof_id = str(data["next_proof_id"])
        data["next_proof_id"] += 1
        data["pending"][proof_id] = {"user_id": user_id, "task_id": task_id, "proof": text or ("صورة إثبات" if photo_id else "(إثبات فارغ)"), "photo_id": photo_id, "points": task["points"]}
        save_data()
        kb = {"inline_keyboard": [[
            {"text": "✅ قبول", "callback_data": f"approve:{proof_id}"},
            {"text": "❌ رفض", "callback_data": f"reject:{proof_id}"}
        ]]}
        caption = f"إثبات جديد #{proof_id}\nالمستخدم: {user.get('first_name','')}\nالمعرف: {user_id}\nالمهمة: #{task_id}\nالنقاط: {task['points']}\nالإثبات: {text or ('صورة مرفقة' if photo_id else '(فارغ)')}"
        try:
            if photo_id:
                api("sendPhoto", {"chat_id": ADMIN_ID, "photo": photo_id, "caption": caption, "reply_markup": json.dumps(kb, ensure_ascii=False)})
            else:
                send(ADMIN_ID, caption, kb)
        except Exception:
            pass
        send(chat_id, "وصل إثباتك إلى الإدارة للمراجعة.")
        return

    if text.startswith("/"):
        send(chat_id, "استخدم /start لعرض القائمة.")
        return
    send(chat_id, "افتح القائمة من /start، ثم اختر المهام المتاحة أو حسابي.")

def process_callback(query):
    user = query.get("from", {})
    chat_id = query.get("message", {}).get("chat", {}).get("id")
    user_id = user.get("id")
    uid = str(user_id)
    ensure_user(user)
    action = query.get("data", "")
    cbid = query.get("id", "")

    if action == "tasks":
        answer_callback(cbid)
        show_tasks(chat_id, user_id)
    elif action == "account":
        answer_callback(cbid)
        u = data["users"][uid]
        send(chat_id, f"حسابك\nالاسم: {u.get('name','')}\nالنقاط: {u.get('points',0)}\nالمهام المقبولة: {len(u.get('done', []))}")
    elif action == "addtask" and user_id == ADMIN_ID:
        answer_callback(cbid)
        data["admin_waiting_task"] = True
        add_task_prompt(chat_id)
    elif action == "pending" and user_id == ADMIN_ID:
        answer_callback(cbid)
        if not data["pending"]:
            send(chat_id, "لا توجد إثباتات معلقة.")
        else:
            for proof_id, item in list(data["pending"].items())[:20]:
                kb = {"inline_keyboard": [[
                    {"text": "✅ قبول", "callback_data": f"approve:{proof_id}"},
                    {"text": "❌ رفض", "callback_data": f"reject:{proof_id}"}
                ]]}
                caption = f"إثبات #{proof_id}\nالمستخدم: {item['user_id']}\nالمهمة: #{item['task_id']}\nالإثبات: {item['proof']}"
                if item.get("photo_id"):
                    api("sendPhoto", {"chat_id": chat_id, "photo": item["photo_id"], "caption": caption, "reply_markup": json.dumps(kb, ensure_ascii=False)})
                else:
                    send(chat_id, caption, kb)
    elif action.startswith("proof:"):
        try:
            task_id = int(action.split(":", 1)[1])
        except ValueError:
            answer_callback(cbid, "طلب غير صالح")
            return
        task = next((t for t in data["tasks"] if t["id"] == task_id and t.get("active", True)), None)
        if not task:
            answer_callback(cbid, "المهمة غير متاحة")
            return
        if uid in task.get("completed_by", []):
            answer_callback(cbid, "أكملت هذه المهمة سابقًا")
            return
        data["waiting_proof"][uid] = task_id
        save_data()
        answer_callback(cbid)
        send(chat_id, f"أرسل الآن رابط حساب تيك توك أو وصف الإثبات للمهمة #{task_id}. أرسل /cancel للإلغاء.")
    elif action.startswith("approve:") and user_id == ADMIN_ID:
        proof_id = action.split(":", 1)[1]
        item = data["pending"].pop(proof_id, None)
        if not item:
            answer_callback(cbid, "تمت مراجعة الإثبات أو لم يعد موجودًا")
            return
        task = next((t for t in data["tasks"] if t["id"] == item["task_id"]), None)
        u = data["users"].setdefault(str(item["user_id"]), {"points": 0, "name": "", "username": "", "done": []})
        u["points"] = u.get("points", 0) + item["points"]
        if task:
            task.setdefault("completed_by", []).append(str(item["user_id"]))
        save_data()
        answer_callback(cbid, "تم القبول وإضافة النقاط")
        send(chat_id, f"تم قبول الإثبات #{proof_id} وإضافة {item['points']} نقطة.")
        try:
            send(item["user_id"], f"✅ تم قبول إثباتك للمهمة #{item['task_id']} وإضافة {item['points']} نقطة إلى حسابك.")
        except Exception:
            pass
    elif action.startswith("reject:") and user_id == ADMIN_ID:
        proof_id = action.split(":", 1)[1]
        item = data["pending"].pop(proof_id, None)
        if not item:
            answer_callback(cbid, "تمت مراجعة الإثبات أو لم يعد موجودًا")
            return
        save_data()
        answer_callback(cbid, "تم رفض الإثبات")
        send(chat_id, f"تم رفض الإثبات #{proof_id}.")
        try:
            send(item["user_id"], f"❌ تم رفض إثباتك للمهمة #{item['task_id']}. يمكنك المحاولة مجددًا من قائمة المهام.")
        except Exception:
            pass
    else:
        answer_callback(cbid, "غير مسموح")

def main():
    global BOT_TOKEN
    if not BOT_TOKEN:
        BOT_TOKEN = input("ألصق رمز البوت الجديد من BotFather (لن يظهر على الشاشة): ").strip()
    if not BOT_TOKEN or ":" not in BOT_TOKEN or any(c.isspace() for c in BOT_TOKEN):
        print("الرمز غير صالح. افتح @BotFather وأنشئ رمزًا جديدًا ثم شغّل البرنامج مجددًا.")
        return
    print("جارٍ الاتصال بتليغرام... اترك Termux مفتوحًا.")
    try:
        me = api("getMe")
        print("تم الاتصال بنجاح بالبوت @" + me.get("username", ""))
    except Exception as e:
        print("فشل الاتصال. تأكد من صحة الرمز والإنترنت. التفاصيل:", e)
        return
    offset = None
    while True:
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset
            updates = api("getUpdates", params, timeout=40)
            for update in updates:
                offset = update["update_id"] + 1
                if "message" in update:
                    process_message(update["message"])
                elif "callback_query" in update:
                    process_callback(update["callback_query"])
        except KeyboardInterrupt:
            print("\nتم إيقاف البوت.")
            break
        except Exception as e:
            print("خطأ مؤقت:", e)
            time.sleep(3)

if __name__ == "__main__":
    main()
