import os
from supabase import create_client, Client
from datetime import datetime
import json

class SupabaseStorage:
    def __init__(self):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise Exception("Supabase credentials not found in environment variables")
        self.supabase: Client = create_client(url, key)
    
    # ===== المستخدمين =====
    def get_user_data(self, user_id):
        try:
            result = self.supabase.table('users').select('*').eq('user_id', str(user_id)).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            return {}
        except Exception as e:
            print(f"Error in get_user_data: {e}")
            return {}
    
    def set_user_data(self, user_id, student_code, password=None, ip_address=None):
        try:
            # جلب البيانات الحالية
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
                
                # تحديث قائمة IPs
                ips = current.get('ips', [])
                if ip_address not in ips:
                    ips.append(ip_address)
                data['ips'] = ips
            
            # upsert
            self.supabase.table('users').upsert(data, on_conflict='user_id').execute()
            return True
        except Exception as e:
            print(f"Error in set_user_data: {e}")
            return False
    
    # ===== المحظورين =====
    def is_banned(self, user_id):
        try:
            result = self.supabase.table('banned_users').select('*').eq('user_id', str(user_id)).execute()
            return len(result.data) > 0
        except:
            return False
    
    def ban_user(self, user_id):
        try:
            self.supabase.table('banned_users').insert({'user_id': str(user_id)}).execute()
            return True
        except:
            return False
    
    def unban_user(self, user_id):
        try:
            self.supabase.table('banned_users').delete().eq('user_id', str(user_id)).execute()
            return True
        except:
            return False
    
    def get_banned_users(self):
        try:
            result = self.supabase.table('banned_users').select('*').execute()
            return [item['user_id'] for item in result.data]
        except:
            return []
    
    # ===== أكواد الطلاب المحظورة =====
    def is_banned_student_code(self, code):
        try:
            result = self.supabase.table('banned_student_codes').select('*').eq('code', str(code)).execute()
            return len(result.data) > 0
        except:
            return False
    
    def add_banned_student_code(self, code):
        try:
            self.supabase.table('banned_student_codes').insert({'code': str(code)}).execute()
            return True
        except:
            return False
    
    def remove_banned_student_code(self, code):
        try:
            self.supabase.table('banned_student_codes').delete().eq('code', str(code)).execute()
            return True
        except:
            return False
    
    def get_banned_student_codes(self):
        try:
            result = self.supabase.table('banned_student_codes').select('*').execute()
            return [item['code'] for item in result.data]
        except:
            return []
    
    # ===== أكواد الوصول =====
    def get_access_codes(self):
        try:
            result = self.supabase.table('access_codes').select('*').execute()
            codes = {}
            for item in result.data:
                codes[item['code']] = item['data']
            return codes
        except:
            return {}
    
    def save_access_code(self, code, data):
        try:
            self.supabase.table('access_codes').upsert({
                'code': code,
                'data': data
            }, on_conflict='code').execute()
            return True
        except:
            return False
    
    def delete_access_code(self, code):
        try:
            self.supabase.table('access_codes').delete().eq('code', code).execute()
            return True
        except:
            return False
    
    # ===== الإعدادات =====
    def get_settings(self):
        try:
            result = self.supabase.table('settings').select('*').eq('key', 'settings').execute()
            if result.data and len(result.data) > 0:
                return result.data[0]['value']
            return {"maintenance_mode": False, "show_transcript": True, "transcript_only": False}
        except:
            return {"maintenance_mode": False, "show_transcript": True, "transcript_only": False}
    
    def save_settings(self, settings):
        try:
            self.supabase.table('settings').upsert({
                'key': 'settings',
                'value': settings
            }, on_conflict='key').execute()
            return True
        except:
            return False
    
    # ===== وضع القائمة البيضاء =====
    def get_whitelist_mode(self):
        try:
            result = self.supabase.table('settings').select('*').eq('key', 'whitelist_mode').execute()
            if result.data and len(result.data) > 0:
                return result.data[0]['value']
            return {"enabled": False}
        except:
            return {"enabled": False}
    
    def save_whitelist_mode(self, mode):
        try:
            self.supabase.table('settings').upsert({
                'key': 'whitelist_mode',
                'value': mode
            }, on_conflict='key').execute()
            return True
        except:
            return False
    
    # ===== قائمة الطلاب البيضاء =====
    def get_student_whitelist(self):
        try:
            result = self.supabase.table('student_whitelist').select('*').execute()
            return {item['student_code'] for item in result.data}
        except:
            return set()
    
    def add_to_student_whitelist(self, student_code):
        try:
            self.supabase.table('student_whitelist').insert({'student_code': str(student_code)}).execute()
            return True
        except:
            return False
    
    def remove_from_student_whitelist(self, student_code):
        try:
            self.supabase.table('student_whitelist').delete().eq('student_code', str(student_code)).execute()
            return True
        except:
            return False
    
    def clear_student_whitelist(self):
        try:
            self.supabase.table('student_whitelist').delete().gt('student_code', '').execute()
            return True
        except:
            return False
    
    # ===== الكوكيز =====
    def get_cookies(self):
        try:
            result = self.supabase.table('cookies').select('*').execute()
            cookies = {}
            for item in result.data:
                cookies[item['id']] = item['data']
            return cookies
        except:
            return {}
    
    def save_cookie(self, cookie_id, data):
        try:
            self.supabase.table('cookies').upsert({
                'id': cookie_id,
                'data': data
            }, on_conflict='id').execute()
            return True
        except:
            return False
    
    def delete_cookie(self, cookie_id):
        try:
            self.supabase.table('cookies').delete().eq('id', cookie_id).execute()
            return True
        except:
            return False
    
    # ===== إعدادات التسجيل التلقائي =====
    def get_auto_login_settings(self):
        try:
            result = self.supabase.table('settings').select('*').eq('key', 'auto_login_settings').execute()
            if result.data and len(result.data) > 0:
                return result.data[0]['value']
            return {"enabled": False, "refresh_interval": 50, "last_run": None}
        except:
            return {"enabled": False, "refresh_interval": 50, "last_run": None}
    
    def save_auto_login_settings(self, settings):
        try:
            self.supabase.table('settings').upsert({
                'key': 'auto_login_settings',
                'value': settings
            }, on_conflict='key').execute()
            return True
        except:
            return False
