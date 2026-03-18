from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
import requests
import json
import time
import os
from functools import wraps
from datetime import datetime, timedelta
import hashlib
import threading
import urllib.parse
from dotenv import load_dotenv

# تحميل متغيرات البيئة من ملف .env (للتطوير المحلي)
load_dotenv()

# ========== إعدادات Supabase ==========
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    print("⚠️ Supabase not installed, using memory storage")
    SUPABASE_AVAILABLE = False
    create_client = None

# ========== إعدادات التطبيق ==========
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'minia_university_secret_key_2026')
app.debug = False
app.permanent_session_lifetime = 3600  # ساعة واحدة

# ========== إعدادات الجامعة ==========
BASE_URL = "http://credit.minia.edu.eg"
LOGIN_URL = f"{BASE_URL}/studentLogin"
DATA_URL = f"{BASE_URL}/getJCI"

# ========== بيانات الأدمن والمطور ==========
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
DEV_TELEGRAM = "𓆩⋆ ׅᎯ𝔹Ꮇ ׅ⋆𓆪"
DEV_TELEGRAM_LINK = "https://t.me/BO_R0"

# ========== حسابات الجلسات الدائمة ==========
SESSION_ACCOUNTS = [
    {"username": "81691006", "password": "iOUy651!", "active": True},
]

# ========== التخزين المؤقت في الذاكرة (احتياطي) ==========
MEMORY_STORAGE = {
    "student_codes": {},
    "banned_users": set(),
    "banned_student_codes": [],
    "access_codes": {},
    "settings": {
        "maintenance_mode": False,
        "show_transcript": True,
        "transcript_only": False
    },
    "whitelist": [],
    "cookies": {},
    "sessions": {},
    "student_whitelist": set(),
    "whitelist_mode": {"enabled": False, "filename": "student_whitelist.txt"},
    "auto_login_settings": {
        "enabled": False,
        "refresh_interval": 50,
        "last_run": None
    },
    "session_manager_sessions": {}
}

# ========== كلاس Supabase Storage ==========
class SupabaseStorage:
    def __init__(self):
        self.available = False
        self.client = None
        
        # محاولة الاتصال بـ Supabase
        supabase_url = os.environ.get('SUPABASE_URL')
        supabase_key = os.environ.get('SUPABASE_KEY')
        
        if supabase_url and supabase_key and SUPABASE_AVAILABLE:
            try:
                self.client = create_client(supabase_url, supabase_key)
                self.available = True
                print("✅ Connected to Supabase successfully")
                self.create_tables_if_not_exist()
            except Exception as e:
                print(f"⚠️ Failed to connect to Supabase: {e}")
    
    def create_tables_if_not_exist(self):
        """محاولة إنشاء الجداول إذا لم تكن موجودة"""
        try:
            # التحقق من وجود الجداول عن طريق محاولة الاستعلام
            self.client.table('users').select('*').limit(1).execute()
        except:
            print("⚠️ Tables might not exist. Please create them manually in Supabase SQL editor")
    
    # ===== المستخدمين =====
    def get_user_data(self, user_id):
        if not self.available:
            return MEMORY_STORAGE.get("student_codes", {}).get(str(user_id), {})
        try:
            result = self.client.table('users').select('*').eq('user_id', str(user_id)).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            return {}
        except Exception as e:
            print(f"Error in get_user_data: {e}")
            return {}
    
    def set_user_data(self, user_id, student_code, password=None, ip_address=None):
        if not self.available:
            data = MEMORY_STORAGE.setdefault("student_codes", {}).get(str(user_id), {})
            if not data:
                data = {}
            data['student_code'] = student_code
            if password:
                data['password'] = password
            if ip_address:
                data['last_ip'] = ip_address
                data['last_seen'] = datetime.now().isoformat()
                ips = data.get('ips', [])
                if isinstance(ips, list) and ip_address not in ips:
                    ips.append(ip_address)
                data['ips'] = ips
            data['updated_at'] = datetime.now().isoformat()
            MEMORY_STORAGE["student_codes"][str(user_id)] = data
            return True
        
        try:
            current = self.get_user_data(user_id)
            data = {
                'user_id': str(user_id),
                'student_code': student_code,
                'updated_at': datetime.now().isoformat()
            }
            if password:
                data['password'] = password
            if ip_address:
                data['last_ip'] = ip_address
                data['last_seen'] = datetime.now().isoformat()
                ips = current.get('ips', [])
                if isinstance(ips, list) and ip_address not in ips:
                    ips.append(ip_address)
                data['ips'] = ips
            self.client.table('users').upsert(data, on_conflict='user_id').execute()
            return True
        except Exception as e:
            print(f"Error in set_user_data: {e}")
            return False
    
    # ===== المحظورين =====
    def is_banned(self, user_id):
        if not self.available:
            return str(user_id) in MEMORY_STORAGE.get("banned_users", set())
        try:
            result = self.client.table('banned_users').select('*').eq('user_id', str(user_id)).execute()
            return len(result.data) > 0
        except:
            return False
    
    def ban_user(self, user_id):
        if not self.available:
            MEMORY_STORAGE.setdefault("banned_users", set()).add(str(user_id))
            return True
        try:
            self.client.table('banned_users').insert({'user_id': str(user_id)}).execute()
            return True
        except:
            return False
    
    def unban_user(self, user_id):
        if not self.available:
            banned = MEMORY_STORAGE.get("banned_users", set())
            if str(user_id) in banned:
                banned.remove(str(user_id))
            return True
        try:
            self.client.table('banned_users').delete().eq('user_id', str(user_id)).execute()
            return True
        except:
            return False
    
    def get_banned_users(self):
        if not self.available:
            return list(MEMORY_STORAGE.get("banned_users", set()))
        try:
            result = self.client.table('banned_users').select('*').execute()
            return [item['user_id'] for item in result.data]
        except:
            return []
    
    # ===== أكواد الطلاب المحظورة =====
    def is_banned_student_code(self, code):
        if not self.available:
            return code in MEMORY_STORAGE.get("banned_student_codes", [])
        try:
            result = self.client.table('banned_student_codes').select('*').eq('code', str(code)).execute()
            return len(result.data) > 0
        except:
            return False
    
    def add_banned_student_code(self, code):
        if not self.available:
            codes = MEMORY_STORAGE.setdefault("banned_student_codes", [])
            if code not in codes:
                codes.append(code)
            return True
        try:
            self.client.table('banned_student_codes').insert({'code': str(code)}).execute()
            return True
        except:
            return False
    
    def remove_banned_student_code(self, code):
        if not self.available:
            codes = MEMORY_STORAGE.get("banned_student_codes", [])
            if code in codes:
                codes.remove(code)
            return True
        try:
            self.client.table('banned_student_codes').delete().eq('code', str(code)).execute()
            return True
        except:
            return False
    
    def get_banned_student_codes(self):
        if not self.available:
            return MEMORY_STORAGE.get("banned_student_codes", [])
        try:
            result = self.client.table('banned_student_codes').select('*').execute()
            return [item['code'] for item in result.data]
        except:
            return []
    
    # ===== أكواد الوصول =====
    def get_access_codes(self):
        if not self.available:
            return MEMORY_STORAGE.get("access_codes", {})
        try:
            result = self.client.table('access_codes').select('*').execute()
            codes = {}
            for item in result.data:
                codes[item['code']] = item['data']
            return codes
        except:
            return {}
    
    def save_access_code(self, code, data):
        if not self.available:
            MEMORY_STORAGE.setdefault("access_codes", {})[code] = data
            return True
        try:
            self.client.table('access_codes').upsert({
                'code': code,
                'data': data
            }, on_conflict='code').execute()
            return True
        except:
            return False
    
    # ===== الإعدادات =====
    def get_settings(self):
        if not self.available:
            return MEMORY_STORAGE.get("settings", {
                "maintenance_mode": False,
                "show_transcript": True,
                "transcript_only": False
            })
        try:
            result = self.client.table('settings').select('*').eq('key', 'settings').execute()
            if result.data and len(result.data) > 0:
                return result.data[0]['value']
            return {"maintenance_mode": False, "show_transcript": True, "transcript_only": False}
        except:
            return {"maintenance_mode": False, "show_transcript": True, "transcript_only": False}
    
    def save_settings(self, settings):
        if not self.available:
            MEMORY_STORAGE["settings"] = settings
            return True
        try:
            self.client.table('settings').upsert({
                'key': 'settings',
                'value': settings
            }, on_conflict='key').execute()
            return True
        except:
            return False
    
    # ===== وضع القائمة البيضاء =====
    def get_whitelist_mode(self):
        if not self.available:
            return MEMORY_STORAGE.get("whitelist_mode", {"enabled": False, "filename": "student_whitelist.txt"})
        try:
            result = self.client.table('settings').select('*').eq('key', 'whitelist_mode').execute()
            if result.data and len(result.data) > 0:
                return result.data[0]['value']
            return {"enabled": False, "filename": "student_whitelist.txt"}
        except:
            return {"enabled": False, "filename": "student_whitelist.txt"}
    
    def save_whitelist_mode(self, mode):
        if not self.available:
            MEMORY_STORAGE["whitelist_mode"] = mode
            return True
        try:
            self.client.table('settings').upsert({
                'key': 'whitelist_mode',
                'value': mode
            }, on_conflict='key').execute()
            return True
        except:
            return False
    
    # ===== قائمة الطلاب البيضاء =====
    def get_student_whitelist(self):
        if not self.available:
            return MEMORY_STORAGE.get("student_whitelist", set())
        try:
            result = self.client.table('student_whitelist').select('*').execute()
            return {item['student_code'] for item in result.data}
        except:
            return set()
    
    def add_to_student_whitelist(self, student_code):
        if not self.available:
            MEMORY_STORAGE.setdefault("student_whitelist", set()).add(str(student_code))
            return True
        try:
            self.client.table('student_whitelist').insert({'student_code': str(student_code)}).execute()
            return True
        except:
            return False
    
    def remove_from_student_whitelist(self, student_code):
        if not self.available:
            whitelist = MEMORY_STORAGE.get("student_whitelist", set())
            if str(student_code) in whitelist:
                whitelist.remove(str(student_code))
            return True
        try:
            self.client.table('student_whitelist').delete().eq('student_code', str(student_code)).execute()
            return True
        except:
            return False
    
    def clear_student_whitelist(self):
        if not self.available:
            MEMORY_STORAGE["student_whitelist"] = set()
            return True
        try:
            self.client.table('student_whitelist').delete().gt('student_code', '').execute()
            return True
        except:
            return False
    
    # ===== الكوكيز =====
    def get_cookies(self):
        if not self.available:
            return MEMORY_STORAGE.get("cookies", {})
        try:
            result = self.client.table('cookies').select('*').execute()
            cookies = {}
            for item in result.data:
                cookies[item['id']] = item['data']
            return cookies
        except:
            return {}
    
    def save_cookie(self, cookie_id, data):
        if not self.available:
            MEMORY_STORAGE.setdefault("cookies", {})[cookie_id] = data
            return True
        try:
            self.client.table('cookies').upsert({
                'id': cookie_id,
                'data': data
            }, on_conflict='id').execute()
            return True
        except:
            return False
    
    def delete_cookie(self, cookie_id):
        if not self.available:
            cookies = MEMORY_STORAGE.get("cookies", {})
            if cookie_id in cookies:
                del cookies[cookie_id]
            return True
        try:
            self.client.table('cookies').delete().eq('id', cookie_id).execute()
            return True
        except:
            return False
    
    # ===== إعدادات التسجيل التلقائي =====
    def get_auto_login_settings(self):
        if not self.available:
            return MEMORY_STORAGE.get("auto_login_settings", {
                "enabled": False, "refresh_interval": 50, "last_run": None
            })
        try:
            result = self.client.table('settings').select('*').eq('key', 'auto_login_settings').execute()
            if result.data and len(result.data) > 0:
                return result.data[0]['value']
            return {"enabled": False, "refresh_interval": 50, "last_run": None}
        except:
            return {"enabled": False, "refresh_interval": 50, "last_run": None}
    
    def save_auto_login_settings(self, settings):
        if not self.available:
            MEMORY_STORAGE["auto_login_settings"] = settings
            return True
        try:
            self.client.table('settings').upsert({
                'key': 'auto_login_settings',
                'value': settings
            }, on_conflict='key').execute()
            return True
        except:
            return False

# ========== تهيئة قاعدة البيانات ==========
db = SupabaseStorage()

# ========== دوال الوصول للبيانات ==========
def get_user_data(user_id):
    return db.get_user_data(user_id)

def set_user_data(user_id, student_code, password=None, ip_address=None):
    db.set_user_data(user_id, student_code, password, ip_address)

def get_user_ip(request):
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr or '0.0.0.0'

def load_access_codes():
    return db.get_access_codes()

def save_access_codes(codes):
    for code, data in codes.items():
        db.save_access_code(code, data)

def load_settings():
    return db.get_settings()

def save_settings(settings):
    db.save_settings(settings)

def load_whitelist_mode():
    return db.get_whitelist_mode()

def save_whitelist_mode(mode):
    db.save_whitelist_mode(mode)

def load_student_whitelist():
    return db.get_student_whitelist()

def save_student_whitelist(students_set, filename=None):
    db.clear_student_whitelist()
    for code in students_set:
        db.add_to_student_whitelist(code)

def add_to_student_whitelist(student_code):
    db.add_to_student_whitelist(student_code)

def remove_from_student_whitelist(student_code):
    db.remove_from_student_whitelist(student_code)

def is_student_whitelisted(student_code):
    mode = load_whitelist_mode()
    if not mode.get("enabled", False):
        return True
    whitelist = load_student_whitelist()
    return str(student_code) in whitelist

def is_banned(user_id):
    return db.is_banned(user_id)

def save_banned_user(user_id):
    db.ban_user(user_id)

def load_banned_student_codes():
    return db.get_banned_student_codes()

def save_banned_student_codes(codes):
    for code in codes:
        db.add_banned_student_code(code)

def is_banned_student_code(student_code):
    return db.is_banned_student_code(student_code)

def add_banned_student_code(code):
    db.add_banned_student_code(code)

def remove_banned_student_code(code):
    db.remove_banned_student_code(code)

def load_auto_login_settings():
    return db.get_auto_login_settings()

def save_auto_login_settings(settings):
    db.save_auto_login_settings(settings)

def load_cookies():
    return db.get_cookies()

def save_cookies(cookies_data):
    for cid, data in cookies_data.items():
        db.save_cookie(cid, data)

def load_whitelist():
    return MEMORY_STORAGE.get("whitelist", [])

def save_whitelist(whitelist):
    MEMORY_STORAGE["whitelist"] = whitelist

def is_whitelisted(user_id):
    return str(user_id) in load_whitelist()

def load_student_codes():
    return MEMORY_STORAGE.get("student_codes", {})

def save_student_codes(codes):
    MEMORY_STORAGE["student_codes"] = codes

def load_banned_users():
    return list(MEMORY_STORAGE.get("banned_users", set()))

def check_and_ban_user(user_id, student_code, password=None, ip_address=None):
    if is_whitelisted(str(user_id)):
        return False, "whitelist_bypass"
    
    user_data = get_user_data(user_id)
    
    if not isinstance(user_data, dict):
        user_data = {}
    
    saved_code = user_data.get("student_code")
    saved_password = user_data.get("password")
    
    if not saved_code:
        set_user_data(user_id, student_code, password, ip_address)
        return False, "new_user"
    
    set_user_data(user_id, saved_code, None, ip_address)
    
    if password and saved_password != password:
        set_user_data(user_id, student_code, password, ip_address)
        return False, "password_updated"
    
    return False, "code_match"

def mark_code_as_used(code, user_id, ip_address=None):
    codes = load_access_codes()
    if code in codes and isinstance(codes[code], dict):
        codes[code]["used"] = True
        codes[code]["used_by"] = user_id
        codes[code]["used_ip"] = ip_address
        codes[code]["used_at"] = datetime.now().isoformat()
        save_access_codes(codes)
        return True
    return False

# ========== نظام إدارة الجلسات (Session Manager) ==========
class SessionManager:
    def __init__(self):
        self.sessions = MEMORY_STORAGE.get("session_manager_sessions", {})
        self.last_refresh = {}
        self.refresh_interval = 50
        self.lock = threading.Lock()
        self.auto_login_enabled = False
        self.refresh_thread = None
        self.stop_refresh = False
    
    def load_sessions(self):
        self.sessions = MEMORY_STORAGE.get("session_manager_sessions", {})
    
    def save_sessions(self):
        MEMORY_STORAGE["session_manager_sessions"] = self.sessions
    
    def login_account(self, username, password):
        try:
            session_req = requests.Session()
            
            login_data = {
                'UserName': username,
                'Password': password,
                'sysID': '313',
                'UserLang': 'A',
                'userType': '2'
            }
            
            response = session_req.post(
                LOGIN_URL,
                data=login_data,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                except Exception:
                    result = {}

                cookies = session_req.cookies.get_dict()
                user_id = cookies.get("userID", "")
                session_dt = cookies.get("sessionDateTime", "")

                if session_dt:
                    cookie_string = f"userID={user_id};sessionDateTime={session_dt}"

                    row = result.get("rows", [{}])[0].get("row", {})
                    login_ok = row.get("LoginOK")

                    if login_ok == "True":
                        print(f"✅ تم تسجيل الدخول بنجاح للحساب {username}")
                    else:
                        print(f"⚠️ تسجيل دخول غير واضح لكن الجلسة صالحة {username}")

                    return {
                        'success': True,
                        'cookies': cookies,
                        'cookie_string': cookie_string,
                        'session': session_req,
                        'username': username
                    }

                print(f"❌ فشل تسجيل الدخول - لم يتم استلام sessionDateTime")
                return {'success': False, 'error': 'لم يتم استلام sessionDateTime'}

            else:
                return {'success': False, 'error': f'HTTP Error: {response.status_code}'}
                
        except requests.Timeout:
            return {'success': False, 'error': 'timeout'}
        except requests.RequestException as e:
            return {'success': False, 'error': f'Network Error: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def refresh_all_sessions(self):
        if not self.auto_login_enabled:
            return
        
        with self.lock:
            for i, account in enumerate(SESSION_ACCOUNTS):
                if account.get('active', False):
                    account_id = f"account_{i}"
                    
                    print(f"🔄 جاري تحديث جلسة الحساب {account['username']}...")
                    
                    result = self.login_account(account['username'], account['password'])
                    if result['success']:
                        self.sessions[account_id] = {
                            'username': account['username'],
                            'cookies': result['cookies'],
                            'cookie_string': result['cookie_string'],
                            'last_refresh': datetime.now().isoformat(),
                            'active': True,
                            'usage_count': self.sessions.get(account_id, {}).get('usage_count', 0)
                        }
                        self.last_refresh[account_id] = datetime.now()
                        
                        add_cookie(result['cookie_string'], f"جلسة تلقائية - {account['username']}")
                        
                        print(f"✅ تم تحديث جلسة الحساب {account['username']}")
                    else:
                        print(f"❌ فشل تحديث جلسة الحساب {account['username']}: {result.get('error')}")
            
            self.save_sessions()
            auto_settings = load_auto_login_settings()
            auto_settings["last_run"] = datetime.now().isoformat()
            save_auto_login_settings(auto_settings)
    
    def set_auto_login_state(self, enabled):
        self.auto_login_enabled = enabled
        auto_settings = load_auto_login_settings()
        auto_settings["enabled"] = enabled
        save_auto_login_settings(auto_settings)
        
        if enabled:
            threading.Thread(target=self.refresh_all_sessions, daemon=True).start()
    
    def get_best_session(self):
        with self.lock:
            active_sessions = []
            for account_id, session_data in self.sessions.items():
                if session_data.get('active', False):
                    last_refresh = datetime.fromisoformat(session_data.get('last_refresh', datetime.now().isoformat()))
                    if (datetime.now() - last_refresh).total_seconds() < self.refresh_interval * 60:
                        active_sessions.append({
                            'id': account_id,
                            'cookies': session_data['cookies'],
                            'cookie_string': session_data['cookie_string'],
                            'usage_count': session_data.get('usage_count', 0),
                            'username': session_data.get('username', '')
                        })
            
            if not active_sessions:
                return None
            
            best_session = min(active_sessions, key=lambda x: x['usage_count'])
            
            if best_session['id'] in self.sessions:
                self.sessions[best_session['id']]['usage_count'] = self.sessions[best_session['id']].get('usage_count', 0) + 1
            
            return best_session

session_manager = SessionManager()
session_manager.load_sessions()
auto_settings = load_auto_login_settings()
session_manager.set_auto_login_state(auto_settings.get("enabled", False))

# ========== نظام الكوكيز المحسن ==========
def add_cookie(cookie_value, description=""):
    cookies = load_cookies()
    
    cookie_id = hashlib.md5(f"{cookie_value}{time.time()}".encode()).hexdigest()[:8]
    
    user_id_value = extract_user_id_from_cookie(cookie_value)
    
    cookies[cookie_id] = {
        "value": cookie_value,
        "user_id": user_id_value,
        "description": description,
        "added_at": datetime.now().isoformat(),
        "is_active": True,
        "usage_count": 0,
        "last_used": None,
        "error_count": 0,
        "is_valid": True
    }
    save_cookies(cookies)
    return cookie_id

def extract_user_id_from_cookie(cookie_string):
    try:
        if not isinstance(cookie_string, str):
            return "unknown"
        parts = cookie_string.split(';')
        for part in parts:
            if 'userID=' in part:
                return part.split('userID=')[1].strip()
    except:
        pass
    return "unknown"

def get_active_cookies():
    cookies = load_cookies()
    active = []
    for cid, data in cookies.items():
        if isinstance(data, dict) and data.get("is_active", True) and data.get("is_valid", True):
            active.append({
                "id": cid, 
                "value": data["value"], 
                "description": data.get("description", ""),
                "usage_count": data.get("usage_count", 0)
            })
    return active

def get_best_cookie():
    best_session = session_manager.get_best_session()
    if best_session:
        return best_session['cookie_string']
    
    active = get_active_cookies()
    if not active:
        return None
    
    best_cookie = min(active, key=lambda x: x['usage_count'])
    return best_cookie['value']

def get_cookie_for_request():
    best_session = session_manager.get_best_session()
    if best_session:
        return best_session['cookies']
    
    active = get_active_cookies()
    if not active:
        return None
    
    best_cookie_data = min(active, key=lambda x: x['usage_count'])
    
    cookie_value = best_cookie_data['value']
    cookies_dict = {}
    if isinstance(cookie_value, str):
        parts = cookie_value.split(';')
        for part in parts:
            if '=' in part:
                key, value = part.strip().split('=', 1)
                cookies_dict[key.strip()] = value.strip()
    
    return cookies_dict

def increment_cookie_usage(cookie_value, success=True):
    cookies = load_cookies()
    
    if isinstance(cookie_value, dict):
        cookie_parts = []
        for key, value in cookie_value.items():
            cookie_parts.append(f"{key}={value}")
        cookie_string = ';'.join(cookie_parts)
    else:
        cookie_string = cookie_value
    
    for cid, data in cookies.items():
        if isinstance(data, dict):
            stored_value = data.get("value", "")
            if stored_value == cookie_string:
                data["usage_count"] = data.get("usage_count", 0) + 1
                data["last_used"] = datetime.now().isoformat()
                
                if not success:
                    data["error_count"] = data.get("error_count", 0) + 1
                    if data.get("error_count", 0) >= 3:
                        data["is_valid"] = False
                else:
                    data["error_count"] = 0
                
                save_cookies(cookies)
                break

# ========== دوال جلب البيانات من الجامعة ==========
def get_student_transcript_with_cookies(student_id, cookies_dict):
    try:
        session_req = requests.Session()
        if cookies_dict:
            session_req.cookies.update(cookies_dict)
        
        param2 = {'InstID': student_id}
        response = session_req.get(DATA_URL, params={
            'param0': 'Reports.RegisterCert',
            'param1': 'getTranscript',
            'param2': json.dumps(param2)
        }, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*; q=0.01'
        }, timeout=30)
        
        if response.status_code == 200:
            try:
                data = response.json()
                return data, None
            except:
                return None, "خطأ في تحليل بيانات السجل الأكاديمي"
        else:
            return None, f"HTTP Error: {response.status_code}"
    except Exception as e:
        return None, str(e)

def get_student_grades_with_cookies(student_id, cookies_dict):
    try:
        session_req = requests.Session()
        if cookies_dict:
            session_req.cookies.update(cookies_dict)
        
        param2 = {
            'ScopeID': '179.11.',
            'ScopeProgID': '12.',
            'StudentCurrentID': student_id,
            'silang': 'A'
        }
        response = session_req.get(DATA_URL, params={
            'param0': 'Reports.StudentData',
            'param1': 'getStudentCourse',
            'param2': json.dumps(param2)
        }, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*; q=0.01'
        }, timeout=30)
        
        if response.status_code == 200:
            try:
                data = response.json()
                return data, None
            except:
                return None, "خطأ في تحليل البيانات"
        else:
            return None, f"HTTP Error: {response.status_code}"
    except Exception as e:
        return None, str(e)

def get_both_results_with_cookies(student_id, cookies_dict):
    transcript_data, transcript_error = get_student_transcript_with_cookies(student_id, cookies_dict)
    grades_data, grades_error = get_student_grades_with_cookies(student_id, cookies_dict)
    
    if transcript_data or grades_data:
        increment_cookie_usage(cookies_dict, success=True)
    else:
        increment_cookie_usage(cookies_dict, success=False)
    
    return {
        'grades': grades_data,
        'grades_error': grades_error,
        'transcript': transcript_data,
        'transcript_error': transcript_error,
        'success': (transcript_data is not None) or (grades_data is not None)
    }

def login_to_university(student_id, password):
    session_req = requests.Session()
    login_data = {
        'UserName': student_id,
        'Password': password,
        'sysID': '313',
        'UserLang': 'A',
        'userType': '2'
    }
    try:
        response = session_req.post(LOGIN_URL, data=login_data, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        }, timeout=30)
        
        if response.status_code == 200:
            try:
                result = response.json()
                if result.get('success') or 'true' in response.text.lower():
                    return session_req, "SUCCESS"
                else:
                    return None, "LOGIN_FAILED"
            except:
                if 'true' in response.text.lower() or 'success' in response.text.lower():
                    return session_req, "SUCCESS"
                else:
                    return None, "LOGIN_FAILED"
        else:
            return None, f"HTTP_ERROR: {response.status_code}"
    except requests.Timeout:
        return None, "TIMEOUT"
    except requests.RequestException as e:
        return None, f"NETWORK_ERROR: {str(e)}"
    except Exception as e:
        return None, f"UNKNOWN_ERROR: {str(e)}"

# ========== دوال الترجمة والتنسيق ==========
def grade_translation(grade):
    translations = {
        'A+': ('أ+', 'امتياز مرتفع', '#2ecc71'),
        'A': ('أ', 'امتياز', '#27ae60'),
        'A-': ('أ-', 'امتياز منخفض', '#2ecc71'),
        'B+': ('ب+', 'جيد جداً مرتفع', '#3498db'),
        'B': ('ب', 'جيد جداً', '#2980b9'),
        'B-': ('ب-', 'جيد جداً منخفض', '#3498db'),
        'C+': ('ج+', 'جيد مرتفع', '#f39c12'),
        'C': ('ج', 'جيد', '#e67e22'),
        'C-': ('ج-', 'جيد منخفض', '#f39c12'),
        'D+': ('د+', 'مقبول مرتفع', '#f1c40f'),
        'D': ('د', 'مقبول', '#f39c12'),
        'F': ('هـ', 'راسب', '#e74c3c'),
        'IP': ('جاري', 'جاري', '#95a5a6'),
        'W': ('منسحب', 'منسحب', '#7f8c8d'),
        'P': ('ناجح', 'ناجح', '#2ecc71'),
        'Fr': ('تأجيل', 'تأجيل', '#95a5a6')
    }
    return translations.get(grade, (grade, grade, '#ffffff'))

def create_course_detail_page(course_data):
    grade_fields = [
        ('CourseWorkDegree', 'CourseWorkMaxDegree', 'أعمال سنة'),
        ('PractDegree', 'PractMaxDegree', 'العملي'),
        ('OralDegree', 'OralMaxDegree', 'الشفوي'),
        ('MidtermDegree', 'MidtermMaxDegree', 'الامتحان النصفي'),
        ('FinaltermDegree', 'FinaltermMaxDegree', 'النهائي'),
        ('ClinicDegree', 'ClinicMaxDegree', 'أعمال سنة'),
        ('Midterm1Degree', 'Midterm1MaxDegree', 'الامتحان النصفي الأول'),
        ('Midterm2Degree', 'Midterm2MaxDegree', 'الامتحان النصفي الثاني'),
        ('ReportsDegree', 'ReportsMaxDegree', 'الفاينال'),
        ('MCQDegree', 'MCQMaxDegree', 'اختيار من متعدد'),
        ('OSCEDegree', 'OSCEMaxDegree', 'OSCE'),
        ('ESSAYDegree', 'ESSAYMaxDegree', 'مقالي'),
        ('ModelBDegree', 'ModelBMaxDegree', 'موديل B'),
        ('ModelCDegree', 'ModelCMaxDegree', 'موديل C'),
        ('ModelDDegree', 'ModelDMaxDegree', 'موديل D'),
        ('SkillsDegree', 'SkillsMaxDegree', 'المهارات'),
        ('AttitudeDegree', 'AttitudeMaxDegree', 'السلوك'),
        ('TeamworkDegree', 'TeamworkMaxDegree', 'العمل الجماعي'),
        ('OspeDegree', 'OspeMaxDegree', 'OSPE'),
        ('Ospe2Degree', 'Ospe2MaxDegree', 'OSPE 2'),
        ('SkillexamDegree', 'SkillexamMaxDegree', 'امتحان المهارات'),
        ('Skillexam2Degree', 'Skillexam2MaxDegree', 'امتحان المهارات 2'),
        ('FinalMCQDegree', 'FinalMCQMaxDegree', 'النهائي MCQ'),
        ('FinalEssayDegree', 'FinalEssayMaxDegree', 'النهائي مقالي'),
        ('SEQDegree', 'SEQMaxDegree', 'SEQ'),
        ('ContDegree', 'ContMaxDegree', 'المستمر'),
        ('ActivityDegree', 'ActivityMaxDegree', 'النشاط')
    ]
    
    course_name = course_data.get('CourseName', 'غير معروف').replace('|', ' ').strip()
    course_code = course_data.get('CourseCode', '')
    credit = course_data.get('CourseCredit', '0')
    grade = course_data.get('Grade', '')
    total_degree = course_data.get('Degree', '')
    course_type = course_data.get('courseType', '').replace('|', ' - ')
    
    translated = grade_translation(grade)
    grade_ar = translated[0] if translated else grade
    grade_desc = translated[1] if len(translated) > 1 else ''
    grade_color = translated[2] if len(translated) > 2 else '#ffffff'
    
    available_grades = []
    total_percentage = 0
    total_count = 0
    
    for degree_field, max_field, label in grade_fields:
        degree_value = course_data.get(degree_field)
        max_value = course_data.get(max_field)
        
        if degree_value is not None and degree_value != '' and degree_value != 'غ' and str(degree_value).strip():
            try:
                degree_float = float(degree_value) if degree_value not in ['غ', ''] else None
                max_float = float(max_value) if max_value and max_value not in ['غ', ''] else None
                
                if degree_float is not None:
                    if max_float is not None and max_float > 0:
                        percentage = (degree_float / max_float) * 100
                        color = '#2ecc71' if percentage >= 60 else '#e74c3c' if percentage < 50 else '#f39c12'
                    else:
                        color = '#3498db'
                        percentage = 0
                    
                    available_grades.append({
                        'label': label,
                        'value': degree_value,
                        'max': max_value if max_value else '—',
                        'color': color,
                        'percentage': percentage
                    })
                    
                    if max_float and max_float > 0:
                        total_percentage += percentage
                        total_count += 1
            except (ValueError, TypeError):
                available_grades.append({
                    'label': label,
                    'value': degree_value,
                    'max': max_value if max_value else '—',
                    'color': '#95a5a6',
                    'percentage': 0
                })
    
    avg_percentage = total_percentage / total_count if total_count > 0 else 0
    
    try:
        total_degree_float = float(total_degree) if total_degree else 0
        total_percentage_value = (total_degree_float / 100) * 100 if total_degree_float else 0
        total_color = '#2ecc71' if total_percentage_value >= 60 else '#e74c3c' if total_percentage_value < 50 else '#f39c12'
    except (ValueError, TypeError):
        total_percentage_value = 0
        total_color = '#95a5a6'
    
    available_grades.sort(key=lambda x: x['percentage'], reverse=True)
    
    html = f'''<!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
        <title>تفاصيل المقرر - {course_name}</title>
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600&family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 10px;
                font-family: 'Tajawal', 'Poppins', sans-serif;
            }}
            
            .container {{
                max-width: 800px;
                margin: 0 auto;
            }}
            
            .card {{
                background: white;
                border-radius: 20px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }}
            
            .header {{
                background: white;
                border-radius: 20px;
                padding: 20px;
                margin-bottom: 20px;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }}
            
            .header h1 {{
                color: #667eea;
                font-size: clamp(18px, 5vw, 24px);
                word-break: break-word;
            }}
            
            .back-btn {{
                background: #6c757d;
                color: white;
                padding: 10px 20px;
                border-radius: 10px;
                text-decoration: none;
                display: inline-block;
                text-align: center;
                font-weight: 500;
                align-self: flex-start;
            }}
            
            .back-btn:hover {{
                background: #5a6268;
            }}
            
            .course-info {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 15px;
                margin-bottom: 20px;
            }}
            
            .info-row {{
                display: flex;
                flex-direction: column;
                padding: 8px 0;
                border-bottom: 1px solid rgba(255,255,255,0.2);
            }}
            
            .info-row:last-child {{
                border-bottom: none;
            }}
            
            .info-label {{
                font-weight: 600;
                font-size: 14px;
                opacity: 0.9;
                margin-bottom: 3px;
            }}
            
            .info-value {{
                font-size: 16px;
                font-weight: 500;
                word-break: break-word;
            }}
            
            .grade-badge {{
                display: inline-block;
                padding: 5px 15px;
                border-radius: 20px;
                font-weight: bold;
                background: rgba(255,255,255,0.2);
            }}
            
            .total-grade {{
                background: white;
                border-radius: 15px;
                padding: 15px;
                margin-bottom: 20px;
                display: flex;
                flex-direction: column;
                align-items: center;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }}
            
            .total-label {{
                color: #666;
                font-size: 14px;
                margin-bottom: 5px;
            }}
            
            .total-value {{
                font-size: 32px;
                font-weight: bold;
                color: {total_color};
            }}
            
            .total-percentage {{
                font-size: 14px;
                color: #666;
                margin-top: 5px;
            }}
            
            .grades-grid {{
                display: grid;
                grid-template-columns: 1fr;
                gap: 10px;
            }}
            
            .grade-item {{
                background: #f8f9fa;
                border-radius: 12px;
                padding: 15px;
                display: flex;
                flex-direction: column;
                gap: 8px;
                border-right: 5px solid {total_color};
            }}
            
            .grade-label {{
                font-weight: 600;
                color: #333;
                font-size: 16px;
            }}
            
            .grade-values {{
                display: flex;
                flex-direction: row;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 10px;
            }}
            
            .grade-score {{
                font-size: 18px;
                font-weight: bold;
                color: {total_color};
            }}
            
            .grade-max {{
                color: #666;
                font-size: 14px;
            }}
            
            .grade-progress {{
                width: 100%;
                height: 8px;
                background: #e0e0e0;
                border-radius: 4px;
                overflow: hidden;
            }}
            
            .progress-bar {{
                height: 100%;
                background: {total_color};
                border-radius: 4px;
                transition: width 0.3s ease;
            }}
            
            .stats-summary {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
                margin-top: 20px;
            }}
            
            .stat-box {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 12px;
                text-align: center;
            }}
            
            .stat-number {{
                font-size: 20px;
                font-weight: bold;
                color: #667eea;
            }}
            
            .stat-label {{
                font-size: 12px;
                color: #666;
                margin-top: 5px;
            }}
            
            @media (min-width: 600px) {{
                .grades-grid {{
                    grid-template-columns: repeat(2, 1fr);
                }}
                
                .info-row {{
                    flex-direction: row;
                    align-items: center;
                }}
                
                .info-label {{
                    min-width: 150px;
                    margin-bottom: 0;
                }}
                
                .header {{
                    flex-direction: row;
                    justify-content: space-between;
                    align-items: center;
                }}
                
                .back-btn {{
                    align-self: auto;
                }}
            }}
            
            @media (min-width: 900px) {{
                .grades-grid {{
                    grid-template-columns: repeat(3, 1fr);
                }}
            }}
            
            .no-data {{
                text-align: center;
                padding: 30px;
                color: #666;
                font-size: 16px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📚 تفاصيل المقرر</h1>
                <a href="javascript:history.back()" class="back-btn">🔙 رجوع</a>
            </div>
            
            <div class="card">
                <div class="course-info">
                    <div class="info-row">
                        <span class="info-label">اسم المقرر:</span>
                        <span class="info-value">{course_name}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">كود المقرر:</span>
                        <span class="info-value">{course_code}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">الساعات المعتمدة:</span>
                        <span class="info-value">{credit}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">نوع المقرر:</span>
                        <span class="info-value">{course_type}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">التقدير:</span>
                        <span class="info-value">
                            <span class="grade-badge" style="background: {grade_color}; color: white;">
                                {grade_ar} {grade_desc}
                            </span>
                        </span>
                    </div>
                </div>
                
                <div class="total-grade">
                    <div class="total-label">الدرجة الكلية</div>
                    <div class="total-value">{total_degree}%</div>
                    <div class="total-percentage">من 100 درجة</div>
                </div>
                
                <h3 style="margin-bottom: 15px; color: #333;">📊 تفاصيل الدرجات</h3>
                
                <div class="grades-grid">
    '''
    
    if available_grades:
        for grade in available_grades:
            html += f'''
                    <div class="grade-item" style="border-right-color: {grade['color']};">
                        <div class="grade-label">{grade['label']}</div>
                        <div class="grade-values">
                            <span class="grade-score" style="color: {grade['color']};">{grade['value']}</span>
                            <span class="grade-max">/ {grade['max']}</span>
                        </div>
                        <div class="grade-progress">
                            <div class="progress-bar" style="width: {grade['percentage']}%; background: {grade['color']};"></div>
                        </div>
                    </div>
            '''
    else:
        html += '''
                    <div class="no-data">
                        لا توجد درجات تفصيلية متاحة لهذا المقرر
                    </div>
        '''
    
    html += f'''
                </div>
                
                <div class="stats-summary">
                    <div class="stat-box">
                        <div class="stat-number">{len(available_grades)}</div>
                        <div class="stat-label">عدد التقييمات</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{avg_percentage:.1f}%</div>
                        <div class="stat-label">متوسط الأداء</div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
        window.onpageshow = function(event) {{
            if (event.persisted) {{
                window.location.reload();
            }}
        }};
        </script>
    </body>
    </html>
    '''
    
    return html

def format_transcript_data(transcript_data):
    if not transcript_data or not isinstance(transcript_data, dict):
        return "<div class='error-message'>لا توجد بيانات سجل أكاديمي متاحة</div>"
    
    html = ""
    
    try:
        total_quality_points = float(transcript_data.get("total66QualityPoints", 0) or 0)
        total_actual_hours = float(transcript_data.get("sem663TotalActualHours", 0) or 0)
        overall_cumulative_gpa = total_quality_points / total_actual_hours if total_actual_hours > 0 else 0
        
        stu_name = transcript_data.get('stuName', 'غير معروف')
        stu_id = transcript_data.get('StuID', 'غير معروف')
        level = transcript_data.get('level', 'غير معروف')
        
        if "|" in level:
            level = level.split("|")[0].strip()
        
        html += f"""
        <div class="student-info-card">
            <div class="info-row">
                <div class="info-label">👤 اسم الطالب:</div>
                <div class="info-value">{stu_name}</div>
            </div>
            <div class="info-row">
                <div class="info-label">🆔 رقم الطالب:</div>
                <div class="info-value">{stu_id}</div>
            </div>
            <div class="info-row">
                <div class="info-label">📊 المستوى:</div>
                <div class="info-value">{level}</div>
            </div>
        </div>
        
        <div class="gpa-summary">
            <div class="gpa-card total">
                <div class="gpa-label">المعدل التراكمي الكلي</div>
                <div class="gpa-value">{overall_cumulative_gpa:.2f}</div>
            </div>
            <div class="gpa-card hours">
                <div class="gpa-label">الساعات الكلية</div>
                <div class="gpa-value">{total_actual_hours:.0f}</div>
            </div>
            <div class="gpa-card points">
                <div class="gpa-label">النقاط التراكمية</div>
                <div class="gpa-value">{total_quality_points:.2f}</div>
            </div>
        </div>
        """
        
        if 'StuSemesterData' in transcript_data:
            for year_data in transcript_data['StuSemesterData']:
                acad_year = year_data.get('AcadYearName', 'سنة غير معروفة')
                
                for semester in year_data.get('Semesters', []):
                    sem_name = semester.get('SemesterName', 'فصل غير معروف')
                    full_name = f"{acad_year} - {sem_name}"
                    
                    courses = semester.get('Courses', [])
                    
                    html += f"""
                    <div class="semester-card">
                        <div class="semester-header">
                            <div class="semester-title">{full_name}</div>
                        </div>
                        
                        <div class="table-responsive">
                            <table class="courses-table-detailed">
                                <thead>
                                    <tr>
                                        <th>المادة</th>
                                        <th>الساعات</th>
                                        <th>التقدير</th>
                                        <th>الدرجة</th>
                                    </tr>
                                </thead>
                                <tbody>
                    """
                    
                    for course in courses:
                        course_name = course.get('CourseName', '').replace('|', ' ').strip()
                        credit = course.get('CourseCredit', '0')
                        grade = course.get('Grade', '')
                        degree = course.get('Degree', '')
                        course_code = course.get('CourseCode', '')
                        
                        translated = grade_translation(grade)
                        grade_display = translated[0] if translated else grade
                        grade_color = translated[2] if len(translated) > 2 else '#ffffff'
                        
                        course_data_encoded = urllib.parse.quote(json.dumps(course))
                        
                        html += f"""
                                    <tr onclick="window.location.href='/course_details/{course_data_encoded}'" style="cursor: pointer;">
                                        <td class="course-name">
                                            <div class="course-name-container">
                                                <span class="course-name-text">{course_name}</span>
                                                <small class="course-code">{course_code}</small>
                                            </div>
                                        </td>
                                        <td class="course-credit">{credit}</td>
                                        <td class="course-grade" style="color: {grade_color};">{grade_display}</td>
                                        <td class="course-degree">{degree}</td>
                                    </tr>
                        """
                    
                    html += """
                                </tbody>
                            </table>
                        </div>
                    </div>
                    """
        
    except Exception as e:
        html += f"<div class='error-message'>خطأ في تنسيق البيانات: {str(e)}</div>"
    
    return html

def format_grades_data(grades_data):
    if not grades_data or not isinstance(grades_data, dict) or 'data' not in grades_data:
        return ""
    
    html = ""
    try:
        first = grades_data['data'][0] if grades_data['data'] else {}
        
        html += f"""
        <div class="info">
            <div class="info-row">
                <div class="info-label">👤 اسم الطالب</div>
                <div class="info-value">{first.get('StuName', 'غير متوفر')}</div>
            </div>
            <div class="info-row">
                <div class="info-label">🆔 رقم الطالب</div>
                <div class="info-value">{first.get('studentID', first.get('Code', 'غير متوفر'))}</div>
            </div>
            <div class="info-row">
                <div class="info-label">🏫 الكلية</div>
                <div class="info-value">{(first.get('faculty', 'غير متوفر')).replace('|',' - ')}</div>
            </div>
            <div class="info-row">
                <div class="info-label">🎓 المستوى</div>
                <div class="info-value">{(first.get('lvl', 'غير متوفر')).replace('|',' - ')}</div>
            </div>
            <div class="info-row">
                <div class="info-label">📚 البرنامج</div>
                <div class="info-value">{(first.get('prog', 'غير متوفر')).replace('|',' - ')}</div>
            </div>
        </div>
        
        <div class="stats-row">
            <div class="stat-box">
                <div class="stat-icon">📊</div>
                <div class="stat-content">
                    <div class="stat-label">المعدل التراكمي</div>
                    <div class="stat-value">{first.get('stuGPA', '0.00')}</div>
                </div>
            </div>
            <div class="stat-box">
                <div class="stat-icon">⏱️</div>
                <div class="stat-content">
                    <div class="stat-label">الساعات المكتسبة</div>
                    <div class="stat-value">{first.get('stuEarnedHours', '0')}</div>
                </div>
            </div>
        </div>
        
        <style>
        .stats-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin: 20px 0;
            width: 100%;
        }}
        
        .stat-box {{
            background: linear-gradient(135deg, #d4af37, #1e3a8a);
            color: white;
            padding: 12px 8px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 5px 15px rgba(212, 175, 55, 0.3);
            min-width: 0;
        }}
        
        .stat-icon {{
            font-size: 22px;
            min-width: 30px;
            text-align: center;
        }}
        
        .stat-content {{
            flex: 1;
            min-width: 0;
        }}
        
        .stat-label {{
            font-size: 11px;
            opacity: 0.9;
            margin-bottom: 2px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .stat-value {{
            font-size: 16px;
            font-weight: bold;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        @media (max-width: 320px) {{
            .stat-box {{
                padding: 10px 5px;
                gap: 5px;
            }}
            
            .stat-icon {{
                font-size: 18px;
                min-width: 25px;
            }}
            
            .stat-label {{
                font-size: 10px;
            }}
            
            .stat-value {{
                font-size: 14px;
            }}
        }}
        
        @media (min-width: 768px) {{
            .stats-row {{
                gap: 15px;
            }}
            
            .stat-box {{
                padding: 15px 12px;
            }}
            
            .stat-icon {{
                font-size: 26px;
                min-width: 35px;
            }}
            
            .stat-label {{
                font-size: 13px;
            }}
            
            .stat-value {{
                font-size: 18px;
            }}
        }}
        </style>
        """
    except Exception as e:
        html = f"<div class='error-message'>خطأ في تنسيق البيانات: {str(e)}</div>"
    
    return html

# ========== صفحات HTML (مختصرة لتوفير المساحة - استخدمها من ملفك الأصلي) ==========
# ملاحظة: ضع هنا صفحات HTML من ملفك الأصلي (LOGIN_PAGE, RESULT_PAGE, ADMIN_PAGE, SETTINGS_PAGE, USERS_PAGE, BANNED_CODES_PAGE, COOKIES_PAGE, ACCESS_CODES_PAGE, USER_DETAILS_PAGE)
# لم أكتبها هنا لتوفير المساحة، ولكن انسخها من ملفك الأصلي newe (2).py

# ========== المسارات (Routes) ==========
@app.route('/')
def index():
    return render_template_string(LOGIN_PAGE, dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)

@app.route('/login', methods=['POST'])
def login():
    identifier = request.form.get('identifier')
    credential = request.form.get('credential')
    user_ip = get_user_ip(request)
    
    if not identifier or not credential:
        return render_template_string(LOGIN_PAGE, error="الرجاء إدخال جميع البيانات", dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)
    
    settings = load_settings()
    if settings.get("maintenance_mode", False) and identifier != ADMIN_USERNAME:
        return render_template_string(LOGIN_PAGE, error="🚧 النظام في وضع الصيانة، يرجى المحاولة لاحقاً", dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)
    
    if identifier == ADMIN_USERNAME and credential == ADMIN_PASSWORD:
        session['user_id'] = "admin"
        session['is_admin'] = True
        session.permanent = True
        set_user_data("admin", "admin", ADMIN_PASSWORD, user_ip)
        return redirect(url_for('admin_panel'))
    
    if not is_student_whitelisted(identifier):
        return render_template_string(LOGIN_PAGE, error="🚫 هذا الحساب غير مصرح له باستخدام النظام", dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)
    
    if is_banned_student_code(identifier):
        return render_template_string(LOGIN_PAGE, error="🚫 هذا الكود محظور ولا يمكن استخدامه", dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)
    
    access_codes = load_access_codes()
    if credential in access_codes:
        student_id = identifier
        access_code = credential
        
        code_data = access_codes[access_code]
        
        if not isinstance(code_data, dict):
            code_data = {}
        
        if code_data.get("single_use", False) and code_data.get("used", False):
            return render_template_string(LOGIN_PAGE, error="❌ هذا الكود مستخدم بالفعل", dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)
        
        cookies_dict = get_cookie_for_request()
        if not cookies_dict:
            return render_template_string(LOGIN_PAGE, error="⚠️ لا توجد كوكيز متاحة - الرجاء إضافة كوكيز أولاً", dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)
        
        if code_data.get("single_use", False):
            mark_code_as_used(access_code, student_id, user_ip)
        
        results = get_both_results_with_cookies(student_id, cookies_dict)
        
        if not results.get('success'):
            return render_template_string(LOGIN_PAGE, error="فشل في جلب النتيجة", dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)
        
        set_user_data(f"access_{student_id}_{int(time.time())}", student_id, None, user_ip)
        
        transcript_html = ""
        grades_html = ""
        
        if settings.get('transcript_only', False):
            transcript_html = format_transcript_data(results.get('transcript'))
        else:
            transcript_html = format_transcript_data(results.get('transcript')) if settings.get('show_transcript', True) and not results.get('transcript_error') else ""
            grades_html = format_grades_data(results.get('grades'))
        
        return render_template_string(RESULT_PAGE, 
                                     data=results['grades'], 
                                     transcript_html=transcript_html,
                                     grades_html=grades_html,
                                     show_transcript=settings.get('show_transcript', True),
                                     transcript_only=settings.get('transcript_only', False),
                                     now=datetime.now(), 
                                     dev_link=DEV_TELEGRAM_LINK, 
                                     dev_name=DEV_TELEGRAM)
    
    student_id = identifier
    password = credential
    
    if is_banned(student_id):
        return render_template_string(LOGIN_PAGE, error="🚫 تم حظر هذا الحساب", dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)
    
    session_req, status = login_to_university(student_id, password)
    
    if status != "SUCCESS":
        return render_template_string(LOGIN_PAGE, error="❌ بيانات دخول غير صحيحة", dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)
    
    ban_result, ban_reason = check_and_ban_user(student_id, student_id, password, user_ip)
    if ban_result:
        return render_template_string(LOGIN_PAGE, error="🚫 تم حظر هذا الحساب", dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)
    
    session['user_id'] = student_id
    session['student_id'] = student_id
    session.permanent = True
    
    cookies_dict = get_cookie_for_request()
    results = get_both_results_with_cookies(student_id, cookies_dict)
    
    if results.get('grades_error'):
        return render_template_string(RESULT_PAGE, error=results['grades_error'], dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)
    
    transcript_html = ""
    grades_html = ""
    
    if settings.get('transcript_only', False):
        transcript_html = format_transcript_data(results.get('transcript')) if not results.get('transcript_error') else ""
    else:
        transcript_html = format_transcript_data(results.get('transcript')) if settings.get('show_transcript', True) and not results.get('transcript_error') else ""
        grades_html = format_grades_data(results.get('grades'))
    
    return render_template_string(RESULT_PAGE, 
                                 data=results['grades'], 
                                 transcript_html=transcript_html,
                                 grades_html=grades_html,
                                 show_transcript=settings.get('show_transcript', True),
                                 transcript_only=settings.get('transcript_only', False),
                                 now=datetime.now(), 
                                 dev_link=DEV_TELEGRAM_LINK, 
                                 dev_name=DEV_TELEGRAM)

@app.route('/course_details/<path:course_data>')
def course_details(course_data):
    try:
        course_data_decoded = urllib.parse.unquote(course_data)
        course_info = json.loads(course_data_decoded)
        html = create_course_detail_page(course_info)
        return html
    except Exception as e:
        return f"<div style='color: red; padding: 20px;'>خطأ في عرض تفاصيل المقرر: {str(e)}</div>"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin')
def admin_panel():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    return render_template_string(ADMIN_PAGE, dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)

@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        settings = {
            "maintenance_mode": request.form.get('maintenance') == 'on',
            "show_transcript": request.form.get('show_transcript') == 'on',
            "transcript_only": request.form.get('transcript_only') == 'on'
        }
        save_settings(settings)
        return redirect(url_for('admin_panel'))
    
    settings = load_settings()
    whitelist_mode = load_whitelist_mode()
    student_whitelist = load_student_whitelist()
    auto_login_settings = load_auto_login_settings()
    
    return render_template_string(SETTINGS_PAGE, 
                                 settings=settings,
                                 whitelist_mode=whitelist_mode,
                                 student_whitelist=student_whitelist,
                                 auto_login_settings=auto_login_settings,
                                 dev_link=DEV_TELEGRAM_LINK, 
                                 dev_name=DEV_TELEGRAM)

@app.route('/admin/toggle_auto_login', methods=['POST'])
def toggle_auto_login_route():
    if 'is_admin' not in session:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    enabled = data.get('enabled')
    
    new_state = toggle_auto_login_state(enabled)
    session_manager.set_auto_login_state(new_state)
    
    return jsonify({
        'success': True, 
        'enabled': new_state,
        'message': 'تم تشغيل التسجيل التلقائي' if new_state else 'تم إيقاف التسجيل التلقائي'
    })

def toggle_auto_login_state(enabled=None):
    settings = load_auto_login_settings()
    if enabled is not None:
        settings["enabled"] = enabled
    else:
        settings["enabled"] = not settings.get("enabled", False)
    settings["last_updated"] = datetime.now().isoformat()
    save_auto_login_settings(settings)
    return settings["enabled"]

@app.route('/admin/toggle_whitelist_mode', methods=['POST'])
def toggle_whitelist_mode_route():
    if 'is_admin' not in session:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    mode = load_whitelist_mode()
    mode['enabled'] = data.get('enabled', False)
    save_whitelist_mode(mode)
    return jsonify({'success': True})

@app.route('/admin/upload_student_whitelist', methods=['POST'])
def upload_student_whitelist():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    if 'whitelist_file' not in request.files:
        return redirect(url_for('admin_settings'))
    
    file = request.files['whitelist_file']
    if file.filename == '':
        return redirect(url_for('admin_settings'))
    
    if file and file.filename.endswith('.txt'):
        content = file.read().decode('utf-8')
        students = set()
        for line in content.splitlines():
            line = line.strip()
            if line and line.isdigit():
                students.add(line)
        save_student_whitelist(students)
    
    return redirect(url_for('admin_settings'))

@app.route('/admin/add_student_to_whitelist', methods=['POST'])
def add_student_to_whitelist():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    student_code = request.form.get('student_code')
    if student_code and student_code.isdigit():
        add_to_student_whitelist(student_code)
    
    return redirect(url_for('admin_settings'))

@app.route('/admin/remove_student_from_whitelist', methods=['POST'])
def remove_student_from_whitelist():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    student_code = request.form.get('student_code')
    remove_from_student_whitelist(student_code)
    
    return redirect(url_for('admin_settings'))

@app.route('/admin/download_student_whitelist')
def download_student_whitelist():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    whitelist = load_student_whitelist()
    content = '\n'.join(sorted(whitelist))
    
    response = app.response_class(
        response=content,
        status=200,
        mimetype='text/plain'
    )
    response.headers["Content-Disposition"] = "attachment; filename=student_whitelist.txt"
    return response

@app.route('/admin/users')
def admin_users():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    student_codes = load_student_codes()
    banned_users = load_banned_users()
    whitelist = load_whitelist()
    
    return render_template_string(USERS_PAGE,
                                 student_codes=student_codes,
                                 banned_users=banned_users,
                                 whitelist=whitelist,
                                 dev_link=DEV_TELEGRAM_LINK,
                                 dev_name=DEV_TELEGRAM)

@app.route('/admin/banned_codes', methods=['GET', 'POST'])
def admin_banned_codes():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        code = request.form.get('code')
        
        if action == 'add':
            add_banned_student_code(code)
        elif action == 'remove':
            remove_banned_student_code(code)
        
        return redirect(url_for('admin_banned_codes'))
    
    banned_codes = load_banned_student_codes()
    return render_template_string(BANNED_CODES_PAGE, banned_codes=banned_codes, dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)

@app.route('/admin/cookies', methods=['GET', 'POST'])
def admin_cookies():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            cookie_value = request.form.get('cookie_value')
            description = request.form.get('description', '')
            add_cookie(cookie_value, description)
        elif action == 'delete':
            cookie_id = request.form.get('cookie_id')
            cookies = load_cookies()
            if cookie_id in cookies:
                del cookies[cookie_id]
                save_cookies(cookies)
        elif action == 'toggle':
            cookie_id = request.form.get('cookie_id')
            cookies = load_cookies()
            if cookie_id in cookies and isinstance(cookies[cookie_id], dict):
                cookies[cookie_id]['is_active'] = not cookies[cookie_id].get('is_active', True)
                save_cookies(cookies)
        
        return redirect(url_for('admin_cookies'))
    
    cookies = load_cookies()
    session_info = []
    for account_id, session_data in session_manager.sessions.items():
        session_info.append({
            'id': account_id,
            'username': session_data.get('username', ''),
            'last_refresh': session_data.get('last_refresh', ''),
            'usage_count': session_data.get('usage_count', 0),
            'active': session_data.get('active', False)
        })
    
    auto_login_settings = load_auto_login_settings()
    
    return render_template_string(COOKIES_PAGE, 
                                 cookies=cookies, 
                                 sessions=session_info,
                                 auto_login_settings=auto_login_settings,
                                 dev_link=DEV_TELEGRAM_LINK, 
                                 dev_name=DEV_TELEGRAM)

@app.route('/admin/sessions', methods=['POST'])
def admin_sessions():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    action = request.form.get('action')
    
    if action == 'refresh_now':
        threading.Thread(target=session_manager.refresh_all_sessions, daemon=True).start()
    
    return redirect(url_for('admin_cookies'))

@app.route('/admin/access_codes', methods=['GET', 'POST'])
def admin_access_codes():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        code = request.form.get('code')
        code_type = request.form.get('type')
        
        codes = load_access_codes()
        codes[code] = {
            "single_use": code_type == "single_use",
            "used": False,
            "created_at": datetime.now().isoformat(),
            "created_by": session.get('user_id', 'admin')
        }
        save_access_codes(codes)
        return redirect(url_for('admin_access_codes'))
    
    codes = load_access_codes()
    return render_template_string(ACCESS_CODES_PAGE, codes=codes, dev_link=DEV_TELEGRAM_LINK, dev_name=DEV_TELEGRAM)

@app.route('/admin/whitelist', methods=['POST'])
def admin_whitelist():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    action = request.form.get('action')
    user_id = request.form.get('user_id')
    
    whitelist = load_whitelist()
    
    if action == 'add' and user_id not in whitelist:
        whitelist.append(user_id)
    elif action == 'remove' and user_id in whitelist:
        whitelist.remove(user_id)
    
    save_whitelist(whitelist)
    return redirect(url_for('admin_users'))

@app.route('/admin/unban', methods=['POST'])
def admin_unban():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    user_id = request.form.get('user_id')
    
    db.unban_user(user_id)
    
    return redirect(url_for('admin_users'))

@app.route('/admin/export_users')
def admin_export_users():
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    student_codes = load_student_codes()
    
    export_data = []
    for user_id, data in student_codes.items():
        if user_id != 'admin' and isinstance(data, dict):
            export_data.append({
                'user_id': user_id,
                'student_code': data.get('student_code', ''),
                'password': data.get('password', ''),
                'last_ip': data.get('last_ip', ''),
                'ips': data.get('ips', []),
                'last_seen': data.get('last_seen', ''),
                'updated_at': data.get('updated_at', '')
            })
    
    response = app.response_class(
        response=json.dumps(export_data, indent=4, ensure_ascii=False),
        status=200,
        mimetype='application/json'
    )
    response.headers["Content-Disposition"] = "attachment; filename=users_export.json"
    return response

@app.route('/admin/user_details/<user_id>')
def admin_user_details(user_id):
    if 'is_admin' not in session:
        return redirect(url_for('index'))
    
    user_data = get_user_data(user_id)
    
    return render_template_string(USER_DETAILS_PAGE, 
                                 user_id=user_id, 
                                 user_data=user_data,
                                 dev_link=DEV_TELEGRAM_LINK, 
                                 dev_name=DEV_TELEGRAM)

@app.route('/debug')
def debug():
    return {
        'supabase_connected': db.available,
        'supabase_url_set': bool(os.environ.get('SUPABASE_URL')),
        'supabase_key_set': bool(os.environ.get('SUPABASE_KEY')),
        'memory_fallback': not db.available,
        'environment': os.environ.get('RAILWAY_ENVIRONMENT', 'local')
    }
# ========== صفحات HTML ==========
# (جميع صفحات HTML موجودة هنا مرة واحدة فقط)

LOGIN_PAGE = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Minia University | Login</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600&family=Cinzel:wght@500;700&display=swap" rel="stylesheet">
<style>
*{
    margin:0;
    padding:0;
    box-sizing:border-box;
}

html,body{
    width:100%;
    height:100%;
    overflow-x:hidden;
}

body{
    display:flex;
    align-items:center;
    justify-content:center;
    background:
        linear-gradient(rgba(7,22,48,.78), rgba(7,22,48,.78)),
        url('https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTD-YOcG5h8n4ORykqy3vEllQBl9EVVVm_Y5a4nNoh00BD3l9J1Utdwp_Q&s=10');
    background-size:cover;
    background-position:center;
    font-family:'Poppins',sans-serif;
    padding:16px;
}

.login-box{
    width:100%;
    max-width:420px;
    background:rgba(255,255,255,.09);
    backdrop-filter:blur(16px);
    border-radius:20px;
    padding:clamp(28px,5vw,45px);
    box-shadow:0 30px 90px rgba(0,0,0,.55);
    border:1px solid rgba(212,175,55,.25);
}

.logo{
    text-align:center;
    margin-bottom:26px;
}

.logo img{
    width:clamp(70px,20vw,95px);
    margin-bottom:12px;
}

.logo h1{
    font-family:'Cinzel',serif;
    font-size:clamp(20px,5vw,26px);
    color:#d4af37;
    letter-spacing:1px;
}

.logo p{
    font-size:clamp(12px,3.5vw,14px);
    color:#cfd9ff;
}

.input-group{
    margin-bottom:18px;
}

.input-group label{
    color:#e6ecff;
    font-size:clamp(13px,3.5vw,14px);
    margin-bottom:6px;
    display:block;
}

.input-group input{
    width:100%;
    padding:14px;
    border-radius:12px;
    border:1px solid rgba(255,255,255,.25);
    background:rgba(255,255,255,.12);
    color:#fff;
    font-size:16px;
}

.input-group input::placeholder{
    color:rgba(255,255,255,.65);
}

.input-group input:focus{
    outline:none;
    border-color:#d4af37;
    box-shadow:0 0 0 2px rgba(212,175,55,.3);
}

.login-btn{
    width:100%;
    padding:15px;
    border-radius:14px;
    border:none;
    background:linear-gradient(135deg,#d4af37,#1e3a8a);
    color:#fff;
    font-size:clamp(15px,4vw,17px);
    font-weight:600;
    cursor:pointer;
    transition:.3s ease;
}

.login-btn:hover{
    transform:translateY(-2px);
    box-shadow:0 12px 35px rgba(212,175,55,.4);
}

.error{
    background:rgba(220,38,38,.25);
    color:#ffdcdc;
    padding:12px;
    border-radius:10px;
    text-align:center;
    margin-bottom:18px;
    font-size:14px;
}

.footer{
    text-align:center;
    margin-top:22px;
    font-size:13px;
}

.footer a{
    color:#d4af37;
    text-decoration:none;
}

.footer a:hover{
    text-decoration:underline;
}

@media(max-width:360px){
    .login-box{
        padding:22px;
    }
}

@media(min-width:1200px){
    .login-box{
        max-width:460px;
    }
}
</style>
</head>

<body>
<div class="login-box">
    <div class="logo">
        <img src="https://www.minia.edu.eg/minia/images/newlogo2026.png">
        <h1>Minia University</h1>
        <p>Ibn Al-Haytham Credit Hour System</p>
    </div>

    {% if error %}
    <div class="error">{{ error }}</div>
    {% endif %}

    <form method="POST" action="/login">
        <div class="input-group">
            <label>Username</label>
            <input type="text" name="identifier" placeholder="Enter your username" required>
        </div>

        <div class="input-group">
            <label>Password</label>
            <input type="password" name="credential" placeholder="Enter your password" required>
        </div>

        <button class="login-btn" type="submit">Sign In</button>
    </form>

    <div class="footer">
        <a href="{{ dev_link }}" target="_blank">{{ dev_name }}</a>
    </div>
</div>
</body>
</html>
'''

RESULT_PAGE = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<title>النتيجة | جامعة المنيا</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600&family=Cinzel:wght@500;700&family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
<style>
*{
    margin:0;
    padding:0;
    box-sizing:border-box;
}

html,body{
    width:100%;
    background:
        linear-gradient(rgba(7,22,48,.95), rgba(7,22,48,.95)),
        url('https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTD-YOcG5h8n4ORykqy3vEllQBl9EVVVm_Y5a4nNoh00BD3l9J1Utdwp_Q&s=10');
    background-size:cover;
    background-position:center;
    background-attachment: fixed;
    font-family:'Tajawal', 'Poppins', sans-serif;
    padding:8px;
    min-height:100vh;
}

.container{
    max-width:1200px;
    margin:0 auto;
    width:100%;
}

.result-box{
    width:100%;
    background:rgba(255,255,255,.08);
    backdrop-filter:blur(15px);
    border-radius:20px;
    padding:15px;
    box-shadow:0 20px 40px rgba(0,0,0,.5);
    border:1px solid rgba(212,175,55,.3);
    margin-bottom:15px;
}

.header{
    text-align:center;
    margin-bottom:15px;
}

.header img{
    width:55px;
    margin-bottom:5px;
}

.header h2{
    font-family:'Cinzel',serif;
    font-size:18px;
    color:#d4af37;
    letter-spacing:1px;
}

.header p{
    font-size:12px;
    color:#cfd9ff;
}

.info{
    background:rgba(255,255,255,.05);
    border-radius:15px;
    padding:12px;
    border:1px solid rgba(255,255,255,.1);
    margin-bottom:15px;
}

.info-row{
    display:flex;
    flex-direction:column;
    margin-bottom:10px;
    padding-bottom:8px;
    border-bottom:1px solid rgba(255,255,255,.1);
}

.info-row:last-child{
    border-bottom:none;
    margin-bottom:0;
    padding-bottom:0;
}

.info-label{
    color:#d4af37;
    font-weight:600;
    font-size:13px;
    margin-bottom:2px;
}

.info-value{
    color:#fff;
    font-size:14px;
    word-break:break-word;
    line-height:1.4;
}

.stats{
    display:flex;
    flex-direction:column;
    gap:8px;
    margin:15px 0;
}

.stat{
    background:linear-gradient(135deg,#d4af37,#1e3a8a);
    color:#fff;
    padding:12px;
    border-radius:12px;
    text-align:center;
    box-shadow:0 5px 15px rgba(212,175,55,.3);
    font-size:14px;
    display:flex;
    align-items:center;
    justify-content:center;
    gap:8px;
}

.stat .icon{
    font-size:18px;
}

.actions{
    text-align:center;
    margin-top:15px;
}

.btn{
    display:inline-block;
    padding:12px 25px;
    border-radius:12px;
    background:linear-gradient(135deg,#d4af37,#1e3a8a);
    color:#fff;
    text-decoration:none;
    font-weight:600;
    transition:.3s;
    margin:5px;
    width:100%;
    text-align:center;
    font-size:14px;
}

.btn:hover{
    transform:translateY(-2px);
    box-shadow:0 8px 25px rgba(212,175,55,.4);
}

.error{
    background:rgba(220,38,38,.2);
    color:#ffdcdc;
    padding:15px;
    border-radius:12px;
    text-align:center;
    font-size:14px;
    margin:15px 0;
}

.footer{
    text-align:center;
    margin-top:15px;
    font-size:12px;
}

.footer a{
    color:#d4af37;
    text-decoration:none;
}

.student-info-card {
    background: linear-gradient(135deg, rgba(212,175,55,0.1), rgba(30,58,138,0.1));
    border-radius: 15px;
    padding: 12px;
    margin-bottom: 15px;
    border: 1px solid rgba(212,175,55,0.3);
}

.student-info-card .info-row {
    display: flex;
    flex-direction: column;
    padding: 6px 0;
    border-bottom: 1px solid rgba(212,175,55,0.15);
}

.student-info-card .info-label {
    color: #d4af37;
    font-weight: 600;
    font-size: 12px;
    margin-bottom: 2px;
}

.student-info-card .info-value {
    color: #fff;
    font-size: 13px;
}

.gpa-summary {
    display: flex;
    flex-direction: row;
    flex-wrap: wrap;
    gap: 8px;
    margin: 15px 0;
}

.gpa-card {
    flex: 1 1 calc(33.333% - 8px);
    min-width: 100px;
    padding: 10px;
    border-radius: 12px;
    text-align: center;
    box-shadow: 0 3px 10px rgba(0,0,0,0.2);
}

.gpa-card.total {
    background: linear-gradient(135deg, #d4af37, #b8860b);
}

.gpa-card.hours {
    background: linear-gradient(135deg, #1e3a8a, #152b5e);
}

.gpa-card.points {
    background: linear-gradient(135deg, #2ecc71, #27ae60);
}

.gpa-label {
    color: rgba(255,255,255,0.9);
    font-size: 11px;
    margin-bottom: 3px;
    white-space: nowrap;
}

.gpa-value {
    color: white;
    font-size: 16px;
    font-weight: bold;
}

.semester-card {
    background: rgba(0,0,0,0.3);
    border-radius: 15px;
    padding: 12px;
    margin-bottom: 15px;
    border: 1px solid rgba(212,175,55,0.2);
}

.semester-header {
    margin-bottom: 12px;
}

.semester-title {
    color: #d4af37;
    font-size: 16px;
    font-weight: bold;
    margin-bottom: 8px;
    padding-bottom: 5px;
    border-bottom: 2px solid rgba(212,175,55,0.3);
    text-align: center;
}

.semester-stats {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
    margin: 8px 0;
    background: rgba(0,0,0,0.2);
    padding: 8px;
    border-radius: 10px;
}

.stat-badge {
    background: rgba(212,175,55,0.1);
    color: #cfd9ff;
    padding: 6px 8px;
    border-radius: 6px;
    font-size: 11px;
    border: 1px solid rgba(212,175,55,0.15);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    text-align: center;
}

.stat-badge strong {
    color: #d4af37;
    font-size: 12px;
    margin-right: 0;
    display: block;
}

.table-responsive {
    width: 100%;
    margin: 10px 0;
    border-radius: 10px;
    overflow: hidden;
}

.courses-table-detailed {
    width: 100%;
    border-collapse: collapse;
    background: rgba(0,0,0,0.2);
    border-radius: 10px;
    font-size: 13px;
    table-layout: fixed;
}

.courses-table-detailed th:nth-child(1) { width: 35%; }
.courses-table-detailed th:nth-child(2) { width: 10%; }
.courses-table-detailed th:nth-child(3) { width: 15%; }
.courses-table-detailed th:nth-child(4) { width: 40%; }

.courses-table-detailed th {
    background: rgba(212,175,55,0.2);
    color: #d4af37;
    padding: 10px 5px;
    font-weight: 600;
    font-size: 13px;
    text-align: center;
    white-space: normal;
    word-wrap: break-word;
}

.courses-table-detailed td {
    padding: 10px 5px;
    color: #fff;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    text-align: center;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

.courses-table-detailed tr:last-child td {
    border-bottom: none;
}

.courses-table-detailed tr:hover {
    background: rgba(212,175,55,0.15);
    cursor: pointer;
}

.course-name {
    text-align: right;
    font-weight: 500;
}

.course-name-container {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.course-name-text {
    font-weight: 600;
    color: #d4af37;
    font-size: 12px;
    line-height: 1.3;
}

.course-code {
    font-size: 10px;
    color: rgba(255,255,255,0.5);
}

.course-grade {
    font-weight: bold;
}

.course-degree {
    font-weight: 500;
}

.click-hint {
    text-align: center;
    margin: 10px 0 15px;
    font-size: 12px;
    color: rgba(212,175,55,0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    background: rgba(212,175,55,0.1);
    padding: 8px;
    border-radius: 30px;
}

.click-hint span {
    font-size: 13px;
}

.courses-table-detailed tr:hover::after {
    content: "انقر لعرض التفاصيل الكاملة";
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(0,0,0,0.9);
    color: #d4af37;
    padding: 5px 10px;
    border-radius: 20px;
    font-size: 11px;
    white-space: nowrap;
    z-index: 1000;
    margin-bottom: 5px;
    border: 1px solid #d4af37;
}

@media(min-width:600px){
    body {
        padding: 15px;
    }
    
    .result-box {
        padding: 20px;
    }
    
    .info-row{
        flex-direction:row;
        align-items:center;
    }
    
    .info-label{
        min-width:150px;
        margin-bottom:0;
        font-size:14px;
    }
    
    .info-value{
        font-size:15px;
    }
    
    .stats{
        flex-direction:row;
        justify-content:center;
    }
    
    .stat{
        flex:1;
        padding:15px;
        font-size:16px;
    }
    
    .btn{
        width:auto;
        font-size:16px;
    }
    
    .gpa-summary{
        flex-direction:row;
    }
    
    .gpa-card{
        flex:1;
    }
    
    .gpa-label {
        font-size: 12px;
    }
    
    .gpa-value {
        font-size: 18px;
    }
    
    .semester-stats{
        grid-template-columns: repeat(3, 1fr);
    }
    
    .stat-badge {
        font-size: 12px;
    }
    
    .stat-badge strong {
        font-size: 14px;
    }
    
    .courses-table-detailed {
        font-size: 14px;
    }
    
    .course-name-text {
        font-size: 13px;
    }
}

@media(min-width:900px){
    .semester-stats {
        grid-template-columns: repeat(6, 1fr);
    }
    
    .courses-table-detailed th:nth-child(1) { width: 40%; }
    .courses-table-detailed th:nth-child(2) { width: 10%; }
    .courses-table-detailed th:nth-child(3) { width: 15%; }
    .courses-table-detailed th:nth-child(4) { width: 35%; }
    
    .course-name-text {
        font-size: 14px;
    }
}

@media(max-width:400px){
    .courses-table-detailed {
        font-size: 11px;
    }
    
    .courses-table-detailed th {
        padding: 8px 3px;
        font-size: 11px;
    }
    
    .courses-table-detailed td {
        padding: 8px 3px;
    }
    
    .course-name-text {
        font-size: 11px;
    }
    
    .course-code {
        font-size: 9px;
    }
    
    .click-hint {
        font-size: 11px;
    }
}

.course-grade[style*="color: #2ecc71"] {
    text-shadow: 0 0 5px rgba(46,204,113,0.3);
}

.course-grade[style*="color: #e74c3c"] {
    text-shadow: 0 0 5px rgba(231,76,60,0.3);
}

.course-grade[style*="color: #f39c12"] {
    text-shadow: 0 0 5px rgba(243,156,18,0.3);
}
</style>
</head>

<body>
<div class="container">
    <div class="result-box">
        <div class="header">
            <img src="https://www.minia.edu.eg/minia/images/newlogo2026.png" alt="Minia University Logo">
            <h2>Minia University</h2>
            <p>Ibn Al-Haytham Credit Hour System</p>
        </div>

        {% if error %}
            <div class="error">
                ❌ {{ error }} <br><br>
                <a href="/" class="btn">عودة للصفحة الرئيسية</a>
            </div>

        {% else %}
            
            {% if transcript_only %}
                {% if transcript_html %}
                    <div class="transcript-section">
                        {{ transcript_html|safe }}
                    </div>
                {% else %}
                    <div class="error">
                        لا توجد بيانات سجل أكاديمي متاحة
                    </div>
                {% endif %}
                
            {% else %}
                {% if grades_html %}
                    {{ grades_html|safe }}
                {% endif %}
                
                {% if show_transcript and transcript_html %}
                    <div class="transcript-section">
                        <h3 style="color:#d4af37; text-align:center; margin:15px 0; font-size:16px;">📋 السجل الأكاديمي التفصيلي</h3>
                        
                        <div class="click-hint">
                            <span>👆 انقر على المادة لعرض التفاصيل الكاملة</span>
                        </div>
                        
                        {{ transcript_html|safe }}
                    </div>
                {% endif %}
            {% endif %}

            <div class="actions">
                <a href="/" class="btn">استعلام جديد</a>
            </div>

        {% endif %}

        <div class="footer">
            <a href="{{ dev_link }}" target="_blank">{{ dev_name }}</a>
        </div>
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', function() {
    var tableRows = document.querySelectorAll('.courses-table-detailed tr');
    
    tableRows.forEach(function(row) {
        if (row.querySelector('th')) return;
        
        row.addEventListener('touchstart', function() {
            this.style.backgroundColor = 'rgba(212,175,55,0.2)';
        });
        
        row.addEventListener('touchend', function() {
            this.style.backgroundColor = '';
        });
        
        row.addEventListener('touchcancel', function() {
            this.style.backgroundColor = '';
        });
    });
    
    console.log('تم تحميل صفحة النتائج بنجاح');
});
</script>
</body>
</html>
'''

ADMIN_PAGE = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة الأدمن - جامعة المنيا</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 15px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px; 
            display: flex; 
            flex-direction: column;
            gap: 15px;
        }
        .header h1 { color: #667eea; }
        .logout-btn { 
            background: #dc3545; 
            color: white; 
            padding: 8px 16px; 
            border-radius: 8px; 
            text-decoration: none;
            align-self: flex-start;
        }
        .menu-grid { 
            display: grid; 
            grid-template-columns: 1fr; 
            gap: 15px; 
        }
        .menu-card { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            text-align: center; 
            text-decoration: none; 
            color: #333; 
            transition: 0.3s; 
            display: block;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .menu-card:hover { 
            transform: translateY(-3px); 
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
        }
        .menu-icon { font-size: 35px; margin-bottom: 8px; }
        .menu-card h3 { margin-bottom: 5px; color: #667eea; }
        .menu-card p { color: #666; font-size: 13px; }
        .dev-footer {
            text-align: center;
            margin-top: 20px;
            color: rgba(255,255,255,0.8);
        }
        .dev-footer a {
            color: white;
            text-decoration: none;
            font-weight: bold;
        }
        @media(min-width:600px){
            .menu-grid{
                grid-template-columns: repeat(2, 1fr);
            }
        }
        @media(min-width:900px){
            .menu-grid{
                grid-template-columns: repeat(3, 1fr);
            }
            .header{
                flex-direction:row;
                justify-content:space-between;
                align-items:center;
            }
            .logout-btn{
                align-self:auto;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔧 لوحة تحكم الأدمن</h1>
            <a href="/logout" class="logout-btn">🚪 خروج</a>
        </div>
        
        <div class="menu-grid">
            <a href="/admin/settings" class="menu-card">
                <div class="menu-icon">⚙️</div>
                <h3>الإعدادات</h3>
                <p>تخصيص إعدادات النظام</p>
            </a>
            
            <a href="/admin/users" class="menu-card">
                <div class="menu-icon">👥</div>
                <h3>المستخدمين</h3>
                <p>إدارة المستخدمين والمحظورين</p>
            </a>
            
            <a href="/admin/banned_codes" class="menu-card">
                <div class="menu-icon">🚫</div>
                <h3>أكواد محظورة</h3>
                <p>إدارة أكواد الطلاب المحظورة</p>
            </a>
            
            <a href="/admin/cookies" class="menu-card">
                <div class="menu-icon">🍪</div>
                <h3>الكوكيز والجلسات</h3>
                <p>إدارة الكوكيز والجلسات التلقائية</p>
            </a>
            
            <a href="/admin/access_codes" class="menu-card">
                <div class="menu-icon">🔑</div>
                <h3>أكواد الوصول</h3>
                <p>إدارة أكواد الوصول</p>
            </a>
            
            <a href="/admin/export_users" class="menu-card">
                <div class="menu-icon">📥</div>
                <h3>تصدير البيانات</h3>
                <p>تصدير بيانات المستخدمين</p>
            </a>
            
            <a href="/" class="menu-card">
                <div class="menu-icon">🏠</div>
                <h3>الصفحة الرئيسية</h3>
                <p>العودة لصفحة الاستعلام</p>
            </a>
        </div>
        
        <div class="dev-footer">
            <a href="{{ dev_link }}" target="_blank">👨‍💻 {{ dev_name }}</a>
        </div>
    </div>
</body>
</html>
'''

SETTINGS_PAGE = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>الإعدادات - جامعة المنيا</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 15px; }
        .container { max-width: 600px; margin: 0 auto; }
        .header { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px; 
            display: flex; 
            flex-direction: column;
            gap: 15px;
        }
        .header h1 { color: #667eea; }
        .back-btn { 
            background: #6c757d; 
            color: white; 
            padding: 8px 16px; 
            border-radius: 8px; 
            text-decoration: none;
            align-self: flex-start;
        }
        .card { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .setting-item { 
            display: flex; 
            flex-direction: column;
            gap: 10px;
            padding: 15px 0; 
            border-bottom: 1px solid #eee; 
        }
        .setting-item:last-child { border-bottom: none; }
        .setting-info h3 { color: #333; margin-bottom: 5px; font-size: 16px; }
        .setting-info p { color: #666; font-size: 13px; }
        .toggle-switch { position: relative; width: 60px; height: 34px; }
        .toggle-switch input { opacity: 0; width: 0; height: 0; }
        .slider { 
            position: absolute; 
            cursor: pointer; 
            top: 0; 
            left: 0; 
            right: 0; 
            bottom: 0; 
            background-color: #ccc; 
            transition: .4s; 
            border-radius: 34px; 
        }
        .slider:before { 
            position: absolute; 
            content: ""; 
            height: 26px; 
            width: 26px; 
            left: 4px; 
            bottom: 4px; 
            background-color: white; 
            transition: .4s; 
            border-radius: 50%; 
        }
        input:checked + .slider { background-color: #667eea; }
        input:checked + .slider:before { transform: translateX(26px); }
        .save-btn { 
            background: #28a745; 
            color: white; 
            border: none; 
            padding: 14px; 
            border-radius: 8px; 
            font-size: 16px; 
            font-weight: bold; 
            cursor: pointer; 
            width: 100%; 
            margin-top: 20px; 
        }
        .save-btn:hover { background: #218838; }
        
        .whitelist-section {
            margin-top: 15px;
        }
        .btn-primary, .btn-danger, .btn-success {
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 13px;
            margin: 2px;
        }
        .btn-primary { background: #667eea; }
        .btn-success { background: #28a745; }
        .btn-danger { background: #dc3545; }
        
        .file-input-group {
            display: flex;
            gap: 10px;
            margin: 10px 0;
            flex-wrap: wrap;
        }
        .file-input-group input[type="file"] {
            flex: 1;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 5px;
            min-width: 200px;
        }
        .single-code-input {
            display: flex;
            gap: 10px;
            margin: 15px 0;
            flex-wrap: wrap;
        }
        .single-code-input input {
            flex: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            min-width: 200px;
        }
        table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-top: 15px;
            font-size: 13px;
        }
        th { 
            background: #667eea; 
            color: white; 
            padding: 8px; 
        }
        td { 
            padding: 6px; 
            border-bottom: 1px solid #dee2e6; 
            text-align: center; 
        }
        tr:hover { background-color: #f5f5f5; }
        
        .dev-footer {
            text-align: center;
            margin-top: 20px;
            color: rgba(255,255,255,0.8);
        }
        .dev-footer a {
            color: white;
            text-decoration: none;
            font-weight: bold;
        }
        .alert-info {
            background: #d1ecf1;
            color: #0c5460;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            font-size: 13px;
        }
        
        @media(min-width:600px){
            .setting-item{
                flex-direction:row;
                align-items:center;
                justify-content:space-between;
            }
            .header{
                flex-direction:row;
                justify-content:space-between;
                align-items:center;
            }
            .back-btn{
                align-self:auto;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚙️ الإعدادات</h1>
            <a href="/admin" class="back-btn">رجوع</a>
        </div>
        
        <div class="card">
            <form method="POST">
                <div class="setting-item">
                    <div class="setting-info">
                        <h3>وضع الصيانة</h3>
                        <p>تعطيل جميع الخدمات مؤقتاً</p>
                    </div>
                    <label class="toggle-switch">
                        <input type="checkbox" name="maintenance" {% if settings.maintenance_mode %}checked{% endif %}>
                        <span class="slider"></span>
                    </label>
                </div>
                
                <div class="setting-item">
                    <div class="setting-info">
                        <h3>عرض السجل الأكاديمي</h3>
                        <p>إظهار الدرجات التفصيلية للمواد</p>
                    </div>
                    <label class="toggle-switch">
                        <input type="checkbox" name="show_transcript" {% if settings.show_transcript %}checked{% endif %}>
                        <span class="slider"></span>
                    </label>
                </div>
                
                <div class="setting-item">
                    <div class="setting-info">
                        <h3>السجل الأكاديمي فقط</h3>
                        <p>عرض السجل الأكاديمي فقط دون الدرجات الأساسية</p>
                    </div>
                    <label class="toggle-switch">
                        <input type="checkbox" name="transcript_only" {% if settings.transcript_only %}checked{% endif %}>
                        <span class="slider"></span>
                    </label>
                </div>
                
                <button type="submit" class="save-btn">💾 حفظ الإعدادات</button>
            </form>
        </div>
        
        <div class="card">
            <h2 style="color: #667eea; margin-bottom: 15px;">🔒 قائمة الطلاب المسموح لهم</h2>
            
            <div class="setting-item">
                <div class="setting-info">
                    <h3>تفعيل وضع القائمة البيضاء</h3>
                    <p>عند التفعيل، سيتمكن فقط الطلاب المدرجين في القائمة من استخدام النظام</p>
                </div>
                <label class="toggle-switch">
                    <input type="checkbox" id="whitelist_mode" {% if whitelist_mode.enabled %}checked{% endif %} onchange="toggleWhitelistMode(this.checked)">
                    <span class="slider"></span>
                </label>
            </div>
            
            <div class="whitelist-section" id="whitelistSection" style="{% if not whitelist_mode.enabled %}display: none;{% endif %}">
                <div class="alert-info">
                    📁 يمكنك رفع ملف txt يحتوي على أرقام الطلاب (كل رقم في سطر منفصل)
                </div>
                
                <form method="POST" action="/admin/upload_student_whitelist" enctype="multipart/form-data" class="file-input-group">
                    <input type="file" name="whitelist_file" accept=".txt" required>
                    <button type="submit" class="btn-success">📤 رفع الملف</button>
                </form>
                
                <div style="text-align: center; margin: 10px 0; color: #666;">أو</div>
                
                <form method="POST" action="/admin/add_student_to_whitelist" class="single-code-input">
                    <input type="text" name="student_code" placeholder="أدخل كود الطالب" required pattern="[0-9]+" title="أرقام فقط">
                    <button type="submit" class="btn-primary">➕ إضافة كود</button>
                </form>
                
                <h3 style="margin: 15px 0 10px;">📋 الطلاب المسموح لهم ({{ student_whitelist|length }})</h3>
                
                {% if student_whitelist %}
                <table>
                    <thead>
                        <tr>
                            <th>كود الطالب</th>
                            <th>إجراء</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for code in student_whitelist|sort %}
                        <tr>
                            <td>{{ code }}</td>
                            <td>
                                <form method="POST" action="/admin/remove_student_from_whitelist" style="display:inline;">
                                    <input type="hidden" name="student_code" value="{{ code }}">
                                    <button type="submit" class="btn-danger" onclick="return confirm('هل أنت متأكد من حذف هذا الكود؟')">❌ حذف</button>
                                </form>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p style="text-align: center; color: #666; padding: 20px;">لا يوجد طلاب في القائمة البيضاء</p>
                {% endif %}
                
                <div style="text-align: center; margin-top: 15px;">
                    <a href="/admin/download_student_whitelist" class="btn-primary" style="text-decoration: none;">📥 تحميل الملف الحالي</a>
                </div>
            </div>
        </div>
        
        <div class="dev-footer">
            <a href="{{ dev_link }}" target="_blank">👨‍💻 {{ dev_name }}</a>
        </div>
    </div>
    
    <script>
    function toggleWhitelistMode(enabled) {
        var section = document.getElementById('whitelistSection');
        if (section) {
            section.style.display = enabled ? 'block' : 'none';
        }
        
        fetch('/admin/toggle_whitelist_mode', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({enabled: enabled})
        });
    }
    </script>
</body>
</html>
'''

USERS_PAGE = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>إدارة المستخدمين - جامعة المنيا</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 15px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px; 
            display: flex; 
            flex-direction: column;
            gap: 15px;
        }
        .header h1 { color: #667eea; }
        .header-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .back-btn, .export-btn { 
            padding: 8px 16px; 
            border-radius: 8px; 
            text-decoration: none;
            color: white;
            text-align: center;
            display: inline-block;
        }
        .back-btn { background: #6c757d; }
        .export-btn { background: #28a745; }
        .card { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            overflow-x: auto;
        }
        .card h2 { color: #667eea; margin-bottom: 15px; font-size: 18px; }
        table { 
            width: 100%; 
            border-collapse: collapse; 
            font-size: 12px;
            min-width: 500px;
        }
        th { 
            background: #667eea; 
            color: white; 
            padding: 8px; 
        }
        td { 
            padding: 6px; 
            border-bottom: 1px solid #dee2e6; 
            text-align: center; 
        }
        tr:hover { background-color: #f5f5f5; }
        .btn-success, .btn-danger, .btn-info { 
            color: white; 
            border: none; 
            padding: 4px 6px; 
            border-radius: 3px; 
            cursor: pointer; 
            text-decoration: none;
            font-size: 11px;
            display: inline-block;
            margin: 2px;
        }
        .btn-success { background: #28a745; }
        .btn-danger { background: #dc3545; }
        .btn-info { background: #17a2b8; }
        .input-group { 
            display: flex; 
            gap: 10px; 
            margin-bottom: 20px; 
            flex-wrap: wrap;
        }
        .input-group input { 
            flex: 1; 
            min-width: 200px;
            padding: 10px; 
            border: 1px solid #ddd; 
            border-radius: 5px; 
        }
        .password-mask {
            font-family: monospace;
            background: #f0f0f0;
            padding: 2px 5px;
            border-radius: 3px;
        }
        .ip-address {
            font-family: monospace;
            color: #17a2b8;
        }
        .search-box {
            width: 100%;
            padding: 10px;
            margin-bottom: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        .dev-footer {
            text-align: center;
            margin-top: 20px;
            color: rgba(255,255,255,0.8);
        }
        .dev-footer a {
            color: white;
            text-decoration: none;
            font-weight: bold;
        }
        @media(min-width:600px){
            .header{
                flex-direction:row;
                justify-content:space-between;
                align-items:center;
            }
            table{
                font-size:14px;
            }
            .btn-success, .btn-danger, .btn-info{
                padding:5px 8px;
                font-size:12px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>👥 إدارة المستخدمين</h1>
            <div class="header-buttons">
                <a href="/admin/export_users" class="export-btn" target="_blank">📥 تصدير JSON</a>
                <a href="/admin" class="back-btn">رجوع</a>
            </div>
        </div>
        
        <div class="card">
            <h2>➕ إضافة إلى قائمة البيض</h2>
            <form method="POST" action="/admin/whitelist" class="input-group">
                <input type="hidden" name="action" value="add">
                <input type="text" name="user_id" placeholder="معرف المستخدم" required>
                <button type="submit" class="btn-success">إضافة</button>
            </form>
            
            <h2>📋 قائمة البيض</h2>
            <table>
                <thead>
                    <tr><th>معرف المستخدم</th><th>إجراء</th></tr>
                </thead>
                <tbody>
                    {% for user in whitelist %}
                    <tr>
                        <td>{{ user }}</td>
                        <td>
                            <form method="POST" action="/admin/whitelist" style="display:inline;">
                                <input type="hidden" name="action" value="remove">
                                <input type="hidden" name="user_id" value="{{ user }}">
                                <button type="submit" class="btn-danger">حذف</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h2>🚫 المستخدمين المحظورين</h2>
            <table>
                <thead>
                    <tr><th>معرف المستخدم</th><th>إجراء</th></tr>
                </thead>
                <tbody>
                    {% for user in banned_users %}
                    <tr>
                        <td>{{ user }}</td>
                        <td>
                            <form method="POST" action="/admin/unban" style="display:inline;">
                                <input type="hidden" name="user_id" value="{{ user }}">
                                <button type="submit" class="btn-success">رفع الحظر</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h2>📊 المستخدمين المسجلين</h2>
            
            <input type="text" id="searchInput" class="search-box" placeholder="🔍 بحث في المستخدمين..." onkeyup="searchTable()">
            
            <div style="margin-bottom: 10px; color: #667eea;">
                إجمالي المستخدمين: {{ student_codes|length }}
            </div>
            
            <table id="usersTable">
                <thead>
                    <tr>
                        <th>معرف المستخدم</th>
                        <th>كود الطالب</th>
                        <th>كلمة المرور</th>
                        <th>آخر IP</th>
                        <th>آخر ظهور</th>
                        <th>الإجراءات</th>
                    </tr>
                </thead>
                <tbody>
                    {% for user, data in student_codes.items() %}
                    {% if user != 'admin' %}
                    <tr>
                        <td>{{ user }}</td>
                        <td>{{ data.student_code if data.student_code else '—' }}</td>
                        <td><span class="password-mask">●●●●●●</span></td>
                        <td class="ip-address">{{ data.last_ip if data.last_ip else '—' }}</td>
                        <td>{{ data.last_seen[:16] if data.last_seen else '—' }}</td>
                        <td>
                            <a href="/admin/user_details/{{ user }}" class="btn-info" target="_blank">عرض</a>
                        </td>
                    </tr>
                    {% endif %}
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="dev-footer">
            <a href="{{ dev_link }}" target="_blank">👨‍💻 {{ dev_name }}</a>
        </div>
    </div>
    
    <script>
    function searchTable() {
        var input, filter, table, tr, td, i, j, txtValue;
        input = document.getElementById("searchInput");
        filter = input.value.toUpperCase();
        table = document.getElementById("usersTable");
        tr = table.getElementsByTagName("tr");
        
        for (i = 1; i < tr.length; i++) {
            tr[i].style.display = "none";
            td = tr[i].getElementsByTagName("td");
            for (j = 0; j < td.length; j++) {
                if (td[j]) {
                    txtValue = td[j].textContent || td[j].innerText;
                    if (txtValue.toUpperCase().indexOf(filter) > -1) {
                        tr[i].style.display = "";
                        break;
                    }
                }
            }
        }
    }
    </script>
</body>
</html>
'''

BANNED_CODES_PAGE = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>أكواد الطلاب المحظورة - جامعة المنيا</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 15px; }
        .container { max-width: 800px; margin: 0 auto; }
        .header { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px; 
            display: flex; 
            flex-direction: column;
            gap: 15px;
        }
        .header h1 { color: #667eea; }
        .back-btn { 
            background: #6c757d; 
            color: white; 
            padding: 8px 16px; 
            border-radius: 8px; 
            text-decoration: none;
            align-self: flex-start;
        }
        .card { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .card h2 { color: #667eea; margin-bottom: 15px; }
        .input-group { 
            display: flex; 
            gap: 10px; 
            margin-bottom: 20px; 
            flex-wrap: wrap;
        }
        .input-group input { 
            flex: 1; 
            min-width: 200px;
            padding: 10px; 
            border: 1px solid #ddd; 
            border-radius: 5px; 
        }
        .btn-danger, .btn-success { 
            color: white; 
            border: none; 
            padding: 10px 20px; 
            border-radius: 5px; 
            cursor: pointer; 
        }
        .btn-danger { background: #dc3545; }
        .btn-success { background: #28a745; }
        table { 
            width: 100%; 
            border-collapse: collapse; 
        }
        th { 
            background: #667eea; 
            color: white; 
            padding: 10px; 
        }
        td { 
            padding: 8px; 
            border-bottom: 1px solid #dee2e6; 
            text-align: center; 
        }
        .dev-footer {
            text-align: center;
            margin-top: 20px;
            color: rgba(255,255,255,0.8);
        }
        .dev-footer a {
            color: white;
            text-decoration: none;
            font-weight: bold;
        }
        @media(min-width:600px){
            .header{
                flex-direction:row;
                justify-content:space-between;
                align-items:center;
            }
            .back-btn{
                align-self:auto;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚫 أكواد الطلاب المحظورة</h1>
            <a href="/admin" class="back-btn">رجوع</a>
        </div>
        
        <div class="card">
            <h2>➕ إضافة كود محظور</h2>
            <form method="POST" class="input-group">
                <input type="hidden" name="action" value="add">
                <input type="text" name="code" placeholder="أدخل كود الطالب" required>
                <button type="submit" class="btn-danger">إضافة</button>
            </form>
        </div>
        
        <div class="card">
            <h2>📋 الأكواد المحظورة</h2>
            <table>
                <thead>
                    <tr>
                        <th>كود الطالب</th>
                        <th>إجراء</th>
                    </tr>
                </thead>
                <tbody>
                    {% for code in banned_codes %}
                    <tr>
                        <td>{{ code }}</td>
                        <td>
                            <form method="POST" style="display:inline;">
                                <input type="hidden" name="action" value="remove">
                                <input type="hidden" name="code" value="{{ code }}">
                                <button type="submit" class="btn-success">إزالة</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="dev-footer">
            <a href="{{ dev_link }}" target="_blank">👨‍💻 {{ dev_name }}</a>
        </div>
    </div>
</body>
</html>
'''

COOKIES_PAGE = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>إدارة الكوكيز والجلسات - جامعة المنيا</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 15px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px; 
            display: flex; 
            flex-direction: column;
            gap: 15px;
        }
        .header h1 { color: #667eea; }
        .back-btn { 
            background: #6c757d; 
            color: white; 
            padding: 8px 16px; 
            border-radius: 8px; 
            text-decoration: none;
            align-self: flex-start;
        }
        .card { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            overflow-x: auto;
        }
        .card h2 { color: #667eea; margin-bottom: 15px; }
        .input-group { 
            display: flex; 
            flex-direction: column;
            gap: 10px; 
            margin-bottom: 20px; 
        }
        .input-group input, .input-group textarea { 
            width: 100%;
            padding: 10px; 
            border: 1px solid #ddd; 
            border-radius: 5px; 
        }
        .input-group textarea {
            min-height: 80px;
            resize: vertical;
        }
        .btn-primary, .btn-success, .btn-danger, .btn-warning, .btn-info { 
            color: white; 
            border: none; 
            padding: 8px 12px; 
            border-radius: 5px; 
            cursor: pointer; 
            font-size: 12px;
            margin: 2px;
        }
        .btn-primary { background: #667eea; }
        .btn-success { background: #28a745; }
        .btn-danger { background: #dc3545; }
        .btn-warning { background: #ffc107; color: #333; }
        .btn-info { background: #17a2b8; }
        table { 
            width: 100%; 
            border-collapse: collapse; 
            font-size: 12px;
            min-width: 600px;
        }
        th { 
            background: #667eea; 
            color: white; 
            padding: 8px; 
        }
        td { 
            padding: 6px; 
            border-bottom: 1px solid #dee2e6; 
            text-align: center; 
        }
        .active { color: #28a745; font-weight: bold; }
        .inactive { color: #dc3545; font-weight: bold; }
        .cookie-value {
            max-width: 150px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .session-info {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .auto-login-control {
            background: #e8f4fd;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        .auto-login-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 15px;
        }
        .auto-login-title {
            font-size: 18px;
            font-weight: bold;
            color: #1e3a8a;
        }
        .auto-login-status {
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: bold;
        }
        .status-enabled {
            background: #d4edda;
            color: #155724;
        }
        .status-disabled {
            background: #f8d7da;
            color: #721c24;
        }
        .auto-login-toggle {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .toggle-btn {
            padding: 10px 25px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: 0.3s;
        }
        .toggle-btn.on {
            background: #28a745;
            color: white;
        }
        .toggle-btn.on:hover {
            background: #218838;
        }
        .toggle-btn.off {
            background: #dc3545;
            color: white;
        }
        .toggle-btn.off:hover {
            background: #c82333;
        }
        .auto-login-info {
            background: white;
            padding: 10px;
            border-radius: 8px;
            font-size: 13px;
            color: #333;
        }
        .dev-footer {
            text-align: center;
            margin-top: 20px;
            color: rgba(255,255,255,0.8);
        }
        .dev-footer a {
            color: white;
            text-decoration: none;
            font-weight: bold;
        }
        @media(min-width:600px){
            .header{
                flex-direction:row;
                justify-content:space-between;
                align-items:center;
            }
            .back-btn{
                align-self:auto;
            }
            .input-group{
                flex-direction:row;
                align-items:center;
            }
            .btn-primary{
                width:auto;
            }
            .auto-login-header {
                flex-direction: row;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🍪 إدارة الكوكيز والجلسات</h1>
            <a href="/admin" class="back-btn">رجوع</a>
        </div>
        
        <div class="auto-login-control">
            <div class="auto-login-header">
                <div>
                    <span class="auto-login-title">🤖 التسجيل التلقائي للجلسات</span>
                    <span class="auto-login-status {% if auto_login_settings.enabled %}status-enabled{% else %}status-disabled{% endif %}">
                        {% if auto_login_settings.enabled %}🟢 مفعل{% else %}🔴 معطل{% endif %}
                    </span>
                </div>
                <div class="auto-login-toggle">
                    {% if auto_login_settings.enabled %}
                        <button class="toggle-btn off" onclick="toggleAutoLogin(false)">⏸️ إيقاف</button>
                    {% else %}
                        <button class="toggle-btn on" onclick="toggleAutoLogin(true)">▶️ تشغيل</button>
                    {% endif %}
                </div>
            </div>
            <div class="auto-login-info">
                <div>🔄 يتم التحديث كل {{ auto_login_settings.refresh_interval }} دقيقة</div>
                {% if auto_login_settings.last_run %}
                <div>🕐 آخر تشغيل: {{ auto_login_settings.last_run[:16] }}</div>
                {% endif %}
            </div>
        </div>
        
        <div class="card">
            <h2>🤖 الجلسات التلقائية</h2>
            <div class="session-info">
                <form method="POST" action="/admin/sessions" style="display: inline;">
                    <input type="hidden" name="action" value="refresh_now">
                    <button type="submit" class="btn-primary" {% if not auto_login_settings.enabled %}disabled style="opacity:0.5"{% endif %}>🔄 تحديث جميع الجلسات الآن</button>
                </form>
                {% if not auto_login_settings.enabled %}
                <small style="color:#666; display:block; margin-top:5px;">⚠️ يجب تشغيل التسجيل التلقائي لتحديث الجلسات</small>
                {% endif %}
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>الحساب</th>
                        <th>آخر تحديث</th>
                        <th>عدد الاستخدامات</th>
                        <th>الحالة</th>
                    </tr>
                </thead>
                <tbody>
                    {% for session in sessions %}
                    <tr>
                        <td>{{ session.username }}</td>
                        <td>{{ session.last_refresh[:16] if session.last_refresh else '—' }}</td>
                        <td>{{ session.usage_count }}</td>
                        <td class="{{ 'active' if session.active else 'inactive' }}">
                            {{ 'نشط' if session.active else 'غير نشط' }}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h2>➕ إضافة كوكيز جديدة</h2>
            <form method="POST" class="input-group">
                <input type="hidden" name="action" value="add">
                <textarea name="cookie_value" placeholder="userID=xxx;sessionDateTime=yyy" required></textarea>
                <input type="text" name="description" placeholder="وصف">
                <button type="submit" class="btn-primary">إضافة</button>
            </form>
        </div>
        
        <div class="card">
            <h2>📋 قائمة الكوكيز</h2>
            <table>
                <thead>
                    <tr>
                        <th>الوصف</th>
                        <th>userID</th>
                        <th>القيمة</th>
                        <th>الحالة</th>
                        <th>الاستخدام</th>
                        <th>الإجراءات</th>
                    </tr>
                </thead>
                <tbody>
                    {% for id, data in cookies.items() %}
                    <tr>
                        <td>{{ data.description or '—' }}</td>
                        <td>{{ data.user_id or '—' }}</td>
                        <td class="cookie-value" title="{{ data.value }}">{{ data.value[:20] }}...</td>
                        <td class="{{ 'active' if data.is_active else 'inactive' }}">
                            {{ 'نشط' if data.is_active else 'غير نشط' }}
                        </td>
                        <td>{{ data.usage_count or 0 }}</td>
                        <td>
                            <form method="POST" style="display:inline;">
                                <input type="hidden" name="action" value="toggle">
                                <input type="hidden" name="cookie_id" value="{{ id }}">
                                <button type="submit" class="btn-warning">تبديل</button>
                            </form>
                            <form method="POST" style="display:inline;">
                                <input type="hidden" name="action" value="delete">
                                <input type="hidden" name="cookie_id" value="{{ id }}">
                                <button type="submit" class="btn-danger" onclick="return confirm('هل أنت متأكد؟')">حذف</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="dev-footer">
            <a href="{{ dev_link }}" target="_blank">👨‍💻 {{ dev_name }}</a>
        </div>
    </div>
    
    <script>
    function toggleAutoLogin(enabled) {
        fetch('/admin/toggle_auto_login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({enabled: enabled})
        })
        .then(response => response.json())
        .then(data => {
            if(data.success) {
                alert(data.message);
                location.reload();
            }
        });
    }
    </script>
</body>
</html>
'''

ACCESS_CODES_PAGE = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>أكواد الوصول - جامعة المنيا</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 15px; }
        .container { max-width: 800px; margin: 0 auto; }
        .header { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px; 
            display: flex; 
            flex-direction: column;
            gap: 15px;
        }
        .header h1 { color: #667eea; }
        .back-btn { 
            background: #6c757d; 
            color: white; 
            padding: 8px 16px; 
            border-radius: 8px; 
            text-decoration: none;
            align-self: flex-start;
        }
        .card { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            overflow-x: auto;
        }
        .card h2 { color: #667eea; margin-bottom: 15px; }
        .input-group { 
            display: flex; 
            gap: 10px; 
            margin-bottom: 20px; 
            flex-wrap: wrap;
        }
        .input-group input, .input-group select { 
            padding: 10px; 
            border: 1px solid #ddd; 
            border-radius: 5px; 
        }
        .input-group input { flex: 2; min-width: 200px; }
        .input-group select { flex: 1; min-width: 120px; }
        .btn-primary { 
            background: #667eea; 
            color: white; 
            border: none; 
            padding: 10px 20px; 
            border-radius: 5px; 
            cursor: pointer; 
        }
        table { 
            width: 100%; 
            border-collapse: collapse; 
            min-width: 500px;
        }
        th { 
            background: #667eea; 
            color: white; 
            padding: 10px; 
        }
        td { 
            padding: 8px; 
            border-bottom: 1px solid #dee2e6; 
            text-align: center; 
        }
        .used { color: #dc3545; }
        .available { color: #28a745; }
        .dev-footer {
            text-align: center;
            margin-top: 20px;
            color: rgba(255,255,255,0.8);
        }
        .dev-footer a {
            color: white;
            text-decoration: none;
            font-weight: bold;
        }
        @media(min-width:600px){
            .header{
                flex-direction:row;
                justify-content:space-between;
                align-items:center;
            }
            .back-btn{
                align-self:auto;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 أكواد الوصول</h1>
            <a href="/admin" class="back-btn">رجوع</a>
        </div>
        
        <div class="card">
            <h2>➕ إضافة كود جديد</h2>
            <form method="POST" class="input-group">
                <input type="text" name="code" placeholder="أدخل الكود" required>
                <select name="type">
                    <option value="single_use">مرة واحدة</option>
                    <option value="permanent">دائم</option>
                </select>
                <button type="submit" class="btn-primary">إضافة</button>
            </form>
        </div>
        
        <div class="card">
            <h2>📋 الأكواد الحالية</h2>
            <table>
                <thead>
                    <tr>
                        <th>الكود</th>
                        <th>النوع</th>
                        <th>الحالة</th>
                        <th>تاريخ الإنشاء</th>
                        <th>المستخدم</th>
                    </tr>
                </thead>
                <tbody>
                    {% for code, data in codes.items() %}
                    <tr>
                        <td>{{ code }}</td>
                        <td>{{ 'مرة واحدة' if data.single_use else 'دائم' }}</td>
                        <td class="{{ 'used' if data.used else 'available' }}">
                            {{ 'مستخدم' if data.used else 'متاح' }}
                        </td>
                        <td>{{ data.created_at[:10] if data.created_at else '—' }}</td>
                        <td>{{ data.used_by if data.used_by else '—' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="dev-footer">
            <a href="{{ dev_link }}" target="_blank">👨‍💻 {{ dev_name }}</a>
        </div>
    </div>
</body>
</html>
'''

USER_DETAILS_PAGE = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تفاصيل المستخدم - جامعة المنيا</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 15px; }
        .container { max-width: 800px; margin: 0 auto; }
        .header { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            margin-bottom: 20px; 
            display: flex; 
            flex-direction: column;
            gap: 15px;
        }
        .header h1 { color: #667eea; word-break: break-word; font-size: 20px; }
        .back-btn { 
            background: #6c757d; 
            color: white; 
            padding: 8px 16px; 
            border-radius: 8px; 
            text-decoration: none;
            align-self: flex-start;
        }
        .card { 
            background: white; 
            border-radius: 15px; 
            padding: 20px; 
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .info-row {
            display: flex;
            flex-direction: column;
            padding: 12px 0;
            border-bottom: 1px solid #eee;
        }
        .info-label {
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }
        .info-value {
            color: #333;
            word-break: break-word;
        }
        .password-value {
            font-family: monospace;
            background: #f0f0f0;
            padding: 5px 10px;
            border-radius: 5px;
            display: inline-block;
        }
        .ip-list {
            list-style: none;
        }
        .ip-list li {
            font-family: monospace;
            background: #f8f9fa;
            padding: 5px 10px;
            margin: 5px 0;
            border-radius: 5px;
        }
        .dev-footer {
            text-align: center;
            margin-top: 20px;
            color: rgba(255,255,255,0.8);
        }
        .dev-footer a {
            color: white;
            text-decoration: none;
            font-weight: bold;
        }
        @media(min-width:600px){
            .header{
                flex-direction:row;
                justify-content:space-between;
                align-items:center;
            }
            .back-btn{
                align-self:auto;
            }
            .info-row{
                flex-direction:row;
            }
            .info-label{
                min-width:150px;
                margin-bottom:0;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 تفاصيل المستخدم: {{ user_id }}</h1>
            <a href="/admin/users" class="back-btn">رجوع</a>
        </div>
        
        <div class="card">
            <div class="info-row">
                <div class="info-label">معرف المستخدم:</div>
                <div class="info-value">{{ user_id }}</div>
            </div>
            
            <div class="info-row">
                <div class="info-label">كود الطالب:</div>
                <div class="info-value">{{ user_data.student_code or '—' }}</div>
            </div>
            
            <div class="info-row">
                <div class="info-label">كلمة المرور:</div>
                <div class="info-value">
                    <span class="password-value">{{ user_data.password or '—' }}</span>
                </div>
            </div>
            
            <div class="info-row">
                <div class="info-label">آخر IP:</div>
                <div class="info-value">{{ user_data.last_ip or '—' }}</div>
            </div>
            
            <div class="info-row">
                <div class="info-label">آخر ظهور:</div>
                <div class="info-value">{{ user_data.last_seen or '—' }}</div>
            </div>
            
            <div class="info-row">
                <div class="info-label">آخر تحديث:</div>
                <div class="info-value">{{ user_data.updated_at or '—' }}</div>
            </div>
            
            <div class="info-row">
                <div class="info-label">جميع عناوين IP:</div>
                <div class="info-value">
                    {% if user_data.ips and user_data.ips is iterable %}
                        <ul class="ip-list">
                        {% for ip in user_data.ips %}
                            <li>{{ ip }}</li>
                        {% endfor %}
                        </ul>
                    {% else %}
                        لا توجد عناوين IP مسجلة
                    {% endif %}
                </div>
            </div>
        </div>
        
        <div class="dev-footer">
            <a href="{{ dev_link }}" target="_blank">👨‍💻 {{ dev_name }}</a>
        </div>
    </div>
</body>
</html>
'''

# ========== تشغيل التطبيق ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
