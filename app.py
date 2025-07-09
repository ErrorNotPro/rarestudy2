from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, abort, make_response, render_template_string
from datetime import timedelta, datetime
import requests
import re
import json
import asyncio
import aiohttp
import logging
import base64
import urllib3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import functools
from urllib.parse import urlparse
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from base64 import b64encode, b64decode
import os
import pickle

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = 'rarestudy'
app.permanent_session_lifetime = timedelta(days=7)

HEADERS_TEMPLATE = {
    'Host': 'api.penpencil.co',
    'client-id': '5eb393ee95fab7468a79d189',
    'client-version': '1910',
    'user-agent': 'Mozilla/5.0 (Linux; Android 12; M2101K6P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36',
    'randomid': '72012511-256c-4e1c-b4c7-29d67136af37',
    'client-type': 'ADMIN',
    'content-type': 'application/json; charset=utf-8',
}

BATCHES_FILE = 'mybatches.json'

# Optimized thread pool with proper limits
executor = ThreadPoolExecutor(max_workers=100)

def encrypt(url):
    key = "364hs33391682025".encode('utf-8')[:16]
    iv = "hsukna3643339168".encode('utf-8')[:16]
    padded_text = pad(url.encode('utf-8'), AES.block_size)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(padded_text)
    encrypt = b64encode(ciphertext).decode('utf-8')
    return encrypt

def decrypt(encrypted_url):
    try:
        key = "364hs33391682025".encode('utf-8')[:16]
        iv = "hsukna3643339168".encode('utf-8')[:16]
        ciphertext = b64decode(encrypted_url.encode('utf-8'))
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded_plaintext = cipher.decrypt(ciphertext)
        plaintext = unpad(padded_plaintext, AES.block_size)
        return plaintext.decode('utf-8')
    except:
        return None

def encode_params(batch_id, subject_id=None, chapter_id=None, url=None, parent_id=None, child_id=None):
    params = {'b': batch_id}
    if subject_id: params['s'] = subject_id
    if chapter_id: params['c'] = chapter_id
    if url: params['url'] = url
    if parent_id: params['parentId'] = parent_id
    if child_id: params['childId'] = child_id
    
    json_params = json.dumps(params)
    base64_params = base64.urlsafe_b64encode(json_params.encode()).decode().rstrip('=')
    encrypted_params = encrypt(base64_params)
    url_safe_encrypted = encrypted_params.replace('/', '_').replace('+', '-').replace('=', '')
    
    return url_safe_encrypted

def decode_params(encrypted_encoded):
    try:
        encrypted_encoded = encrypted_encoded.replace('_', '/').replace('-', '+')
        padding = 4 - len(encrypted_encoded) % 4
        if padding != 4:
            encrypted_encoded += '=' * padding
        
        decrypted_params = decrypt(encrypted_encoded)
        if decrypted_params is None:
            return {}
        
        padding = 4 - len(decrypted_params) % 4
        if padding != 4:
            decrypted_params += '=' * padding
        json_params = base64.urlsafe_b64decode(decrypted_params).decode()
        return json.loads(json_params)
    except Exception as e:
        logging.error(f"Error decoding parameters: {e}")
        return {}

def load_batches():
    try:
        with open(BATCHES_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def get_headers(token):
    headers = HEADERS_TEMPLATE.copy()
    headers['authorization'] = f"Bearer {token}"
    return headers

async def create_session():
    """Create optimized aiohttp session"""
    connector = aiohttp.TCPConnector(
        limit=100,
        limit_per_host=50,
        ttl_dns_cache=300,
        use_dns_cache=True,
        enable_cleanup_closed=True
    )
    return aiohttp.ClientSession(connector=connector)

async def fetch_data(session, url, headers, params=None, data=None, method='GET'):
    try:
        async with session.request(method, url, headers=headers, params=params, json=data) as response:
            if response.status == 200:
                return await response.json()
            else:
                logging.warning(f"HTTP {response.status} for {url}")
                return {"success": False, "data": {"message": "No Data Found"}}
    except Exception as e:
        logging.error(f"Error fetching {url}: {e}")
        return {"success": False, "data": {"message": "No Data Found"}}

def run_async_optimized(coro):
    """Simplified async runner without thread pool"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except Exception as e:
        logging.error(f"Error in async operation: {e}")
        return None

@app.context_processor
def utility_processor():
    return dict(encode_params=encode_params)

async def process_content(session, batch_id, subject_id, schedule_id, content_type, headers):
    url = f"https://api.penpencil.co/v1/batches/{batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
    data = await fetch_data(session, url, headers=headers)
    content = []

    if data and data.get("success") and data.get("data"):
        data_item = data["data"]

        if content_type in ("videos", "DppVideos"):
            video_details = data_item.get('videoDetails', {})
            if video_details:
                name = data_item.get('topic')
                childId = data_item.get('_id')
                if video_details.get('embedCode'):
                    videoUrl = video_details.get('embedCode')
                    
            #    elif video_details.get('videoUrl'):
                else:
                    encoded_params = encode_params(
                        batch_id=batch_id,
                        url=video_details.get('videoUrl') or 'https://d1d34p8vz63oiq.cloudfront.net/682749f7-eb81-47ff-8788-c25bf7afbbd9/master.mpd',
                        parent_id=batch_id,
                        child_id=childId
                    )
                    videoUrl = f"/media/{encoded_params}"
                
                if videoUrl:
                    content.append({
                        'type': 'video', 
                        'name': name, 
                        'videoUrl': videoUrl, 
                        'thumbnail': video_details.get('image'), 
                    })
                    
        elif content_type in ("notes", "DppNotes"):
            for homework in data_item.get('homeworkIds', []):
                for attachment in homework.get('attachmentIds', []):
                    url = attachment.get('baseUrl', '') + attachment.get('key', '')
                    if url:
                        content.append({'type': 'note', 'name': homework.get('topic', ''), 'url': url})

    return {content_type: content} if content else {}

async def fetch_schedule(session, chapter_id, batch_id, subject_id, content_type, headers):
    all_schedule = []
    page = 1
    while True:
        params = {'tag': chapter_id, 'contentType': content_type, 'page': page}
        url = f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{subject_id}/contents"
        data = await fetch_data(session, url, headers=headers, params=params)

        if data and data.get("success") and data.get("data"):
            for item in data["data"]:
                item['content_type'] = content_type
                all_schedule.append(item)
            page += 1
        else:
            break
    return all_schedule

async def process_chapters(session, chapter_id, batch_id, subject_id, content_type, headers):
    all_schedule = await fetch_schedule(session, chapter_id, batch_id, subject_id, content_type, headers)
    
    tasks = [process_content(session, batch_id, subject_id, item["_id"], item['content_type'], headers)
             for item in all_schedule]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    combined_content = []
    for result in results:
        if isinstance(result, dict) and result.get(content_type):
            combined_content.extend(result[content_type])
    return combined_content

async def fetch_chapter_content_async(batch_id, subject_id, chapter_id, section, token):
    headers = get_headers(token)
    async with await create_session() as session:
        return await process_chapters(session, chapter_id, batch_id, subject_id, section, headers)

async def fetch_subjects_async(batch_id, token):
    headers = get_headers(token)
    async with await create_session() as session:
        url = f'https://api.penpencil.co/v3/batches/{batch_id}/details'
        data = await fetch_data(session, url, headers, method='GET')
        if data and data.get("success"):
            return data.get('data', {}).get('subjects', [])
        return []

async def fetch_chapters_async(batch_id, subject_id, token):
    headers = get_headers(token)
    all_chapters = []
    page = 1
    async with await create_session() as session:
        while True:
            url = f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{subject_id}/topics?page={page}"
            data = await fetch_data(session, url, headers, method='GET')
            if data and data.get("success"):
                chapters = data.get("data", [])
                if chapters:
                    all_chapters.extend(chapters)
                    page += 1
                else:
                    break
            else:
                break
    return all_chapters

async def get_schedule_details(batch_id, token, subject_id, schedule_id):
    headers = get_headers(token)
    async with await create_session() as session:
        url = f"https://api.penpencil.co/v1/batches/{batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
        data = await fetch_data(session, url, headers, method='GET')
        content = []
    
        if data and data.get("success") and data.get("data"):
            data_item = data["data"]
            subject_name = data_item.get('subject', {}).get('name')
            name = data_item.get('topic')
            childId = data_item.get('_id')
            startTime = (datetime.fromisoformat(data_item.get('startTime').replace("Z", "+00:00")) + timedelta(hours=5, minutes=30)).strftime("%I:%M%p").lstrip("0")
            video_details = data_item.get('videoDetails', {})
        
            if video_details:
                if video_details.get('embedCode'):
                    videoUrl = video_details.get('embedCode')
                    
           #     elif video_details.get('videoUrl'):
                else:
                    encoded_params = encode_params(
                        batch_id=batch_id,
                        url=video_details.get('videoUrl') or 'https://d1d34p8vz63oiq.cloudfront.net/682749f7-eb81-47ff-8788-c25bf7afbbd9/master.mpd',
                        parent_id=batch_id,
                        child_id=childId
                    )
                    videoUrl = f"/media/{encoded_params}"
            
                if videoUrl:
                    content.append({
                        'type': 'video', 
                        'name': name, 
                        'videoUrl': videoUrl, 
                        'thumbnail': video_details.get('image'), 
                        'subject_name': subject_name,
                        'startTime': startTime
                    })
            else:
                url = data_item.get('url') or 'https://d1d34p8vz63oiq.cloudfront.net/682749f7-eb81-47ff-8788-c25bf7afbbd9/master.mpd'
                if url:
                    encoded_params = encode_params(
                        batch_id=batch_id,
                        url=url,
                        parent_id=batch_id,
                        child_id=childId
                    )
                    videoUrl = f"/media/{encoded_params}"
            
                    if videoUrl:
                        content.append({
                            'type': 'video', 
                            'name': name, 
                            'videoUrl': videoUrl, 
                            'thumbnail': '', 
                            'subject_name': subject_name,
                            'startTime': startTime
                        })
        
            for homework in data_item.get('homeworkIds', []):
                for attachment in homework.get('attachmentIds', []):
                    url = attachment.get('baseUrl') + attachment.get('key')
                    if url:
                        content.append({'type': 'note', 'name': homework.get('topic'), 'url': url, 'subject_name': subject_name})
        
            dpp = data_item.get('dpp')
            if dpp:
                for homework in dpp.get('homeworkIds', []):
                    for attachment in homework.get('attachmentIds', []):
                        url = attachment.get('baseUrl') + attachment.get('key')
                        if url:
                            content.append({'type': 'note', 'name': homework.get('topic'), 'url': url, 'subject_name': subject_name})
        return content

async def get_todays_schedule(batch_id, token):
    headers = get_headers(token)
    async with await create_session() as session:
        url = f"https://api.penpencil.co/v1/batches/{batch_id}/todays-schedule"
        data = await fetch_data(session, url, headers, method='GET')
        all_content = []

        if data and data.get("success") and data.get("data"):
            tasks = []
            for item in data['data']:
                schedule_id = item.get('_id')
                subject_id = item.get('batchSubjectId')
                tasks.append(get_schedule_details(batch_id, token, subject_id, schedule_id))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    all_content.extend(result)
    return all_content
    

@app.before_request
def ensure_token():
    """Ensure user has a valid token before processing requests"""
    public_endpoints = ['static', 'key_generate', 'key_login_success', 'verify_access']
    
    if request.endpoint in public_endpoints:
        return
    
    token = session.get('token')
    
    # If no token in session or token is invalid, get a new one
    if not token or not validate_token(token):
        try:
            response = requests.get("https://pwlogintoken-b99dfabfaab6.herokuapp.com/update-login-token", timeout=50)
            if response.status_code == 200:
                data = response.json()
                new_token = data.get('access_token')
                if new_token:
                    session.permanent = True
                    session['token'] = new_token
                else:
                    return redirect('/keygenerate')
            else:
                return redirect('/keygenerate')
        except:
            return redirect('/keygenerate')
    
    # Quick fingerprint check without blocking
    fingerprint = get_user_fingerprint_from_request()
    try:
        response = requests.get(
            f"https://sessionn-579e1179aa8e.herokuapp.com/get/login-session={fingerprint}",
            timeout=50
        )
        if response.status_code == 200:
            data = response.json()
            if not (data.get('primaryKeySuccess', False) and data.get('secondaryKeySuccess', False)):
                return redirect('/keygenerate')
        else:
            return redirect('/keygenerate')
    except:
        return redirect('/keygenerate')

def validate_token(token):
    """Simple token validation with timeout"""
    try:
        headers = get_headers(token)
        
        response = requests.post(
        "https://api.penpencil.co/v3/oauth/verify-token",
        headers=headers,
        timeout=30)
        
        return response.status_code == 200
    except:
        return False

def get_user_fingerprint_from_request():
    """Extract fingerprint from request headers/user agent"""
    token = session.get('token')
    user_agent = request.headers.get('User-Agent', '')
    accept_language = request.headers.get('Accept-Language', '')
    accept_encoding = request.headers.get('Accept-Encoding', '')
    
    fingerprint_data = f"{token}|{user_agent}|{accept_language}|{accept_encoding}"
    
    hash_value = 0
    for char in fingerprint_data:
        hash_value = ((hash_value << 5) - hash_value) + ord(char)
        hash_value = hash_value & hash_value
    
    return str(abs(hash_value))

def has_both_keys(fingerprint):
    """Check if user has both keys with timeout"""
    try:
        response = requests.get(
            f"https://sessionn-579e1179aa8e.herokuapp.com/get/login-session={fingerprint}",
            timeout=50
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get('primaryKeySuccess', False) and data.get('secondaryKeySuccess', False)
        return False
    except:
        return False

def get_user_status(fingerprint):
    """Get user key status with referrers"""
    try:
        response = requests.get(
            f"https://sessionn-579e1179aa8e.herokuapp.com/get/login-session={fingerprint}",
            timeout=50
        )
        
        if response.status_code == 200:
            data = response.json()
            return {
                'primary': data.get('primaryKeySuccess', False),
                'secondary': data.get('secondaryKeySuccess', False),
                'primary_referrer': data.get('primaryReferrer', ''),
                'secondary_referrer': data.get('secondaryReferrer', '')
            }
        return {'primary': False, 'secondary': False, 'primary_referrer': '', 'secondary_referrer': ''}
    except:
        return {'primary': False, 'secondary': False, 'primary_referrer': '', 'secondary_referrer': ''}

def update_key_status(fingerprint, primary=False, secondary=False, primary_referrer='', secondary_referrer=''):
    """Update key status with referrers"""
    try:
        current = get_user_status(fingerprint)
        
        data = {
            'fingerprint': fingerprint,
            'primaryKeySuccess': primary or current['primary'],
            'secondaryKeySuccess': secondary or current['secondary'],
            # Only update referrer if explicitly provided
            'primaryReferrer': primary_referrer if primary_referrer else current['primary_referrer'],
            'secondaryReferrer': secondary_referrer if secondary_referrer else current['secondary_referrer']
        }
        
        response = requests.post(
            "https://sessionn-579e1179aa8e.herokuapp.com/add-session",
            json=data,
            timeout=50
        )
        
        return response.status_code in [200, 201]
    except Exception as e:
        logging.error(f"Failed to update key status: {e}")
        return False

# Configuration
PRIMARY_URL = 'https://shortner.in/cpNcJg'
SECONDARY_URL = 'https://adrinolinks.com/aQAU5zCk'
HOW_TO_GENERATE_URL = 'https://t.me/rarestudy/28'

# HTML Templates with Dark Theme
KEY_GENERATE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Generate Keys - RareStudy</title>
    <link rel="icon" type="image/png" href="/static/rarestudylogo.png">
    <style>
        *{margin:0;padding:0;box-sizing:border-box;outline:none;-webkit-tap-highlight-color:transparent;user-select:none}
        body,html{height:100%;font-family:Inter,sans-serif;background:#0f172a;color:#e2e8f0;overflow:hidden}
        
        .header{position:fixed;top:0;left:0;right:0;height:50px;background:rgba(15,23,42,0.95);backdrop-filter:blur(15px);display:flex;align-items:center;z-index:1400;border-bottom:1px solid rgba(30,41,59,0.5);box-shadow:0 4px 20px rgba(0,0,0,0.3);padding:0 15px;justify-content:center}
        
        .site-brand{font-weight:700;font-size:18px;color:#6366f1;letter-spacing:0.3px;background:rgba(79,70,229,0.15);padding:6px 14px;border-radius:10px;border:1px solid rgba(79,70,229,0.3);box-shadow:0 2px 8px rgba(79,70,229,0.2)}
        
        .container{
            position:absolute;
            top:50%;
            left:50%;
            transform:translate(-50%,-50%);
            background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);
            border-radius:20px;
            padding:40px;
            text-align:center;
            max-width:450px;
            width:90%;
            box-shadow:0 20px 60px rgba(0,0,0,0.6);
            border:2px solid rgba(99,102,241,0.3);
            backdrop-filter:blur(10px);
        }
        
        h1{font-size:2.2em;margin-bottom:20px;color:#e2e8f0;font-weight:800;letter-spacing:0.5px}
        
        .key-button{
            display:block;
            background:linear-gradient(135deg,#6366f1 0%,#4f46e5 100%);
            color:white;
            padding:16px 32px;
            text-decoration:none;
            border-radius:15px;
            font-weight:700;
            margin:20px 0;
            transition:all 0.3s ease;
            border:none;
            cursor:pointer;
            font-size:16px;
            letter-spacing:0.5px;
            box-shadow:0 8px 25px rgba(99,102,241,0.3);
            position:relative;
            overflow:hidden;
        }
        
        .key-button:hover{
            transform:translateY(-3px);
            box-shadow:0 12px 35px rgba(99,102,241,0.4);
        }
        
        .key-button:active{
            transform:translateY(-1px);
        }
        
        .secondary{
            background:linear-gradient(135deg,#10b981 0%,#059669 100%) !important;
            box-shadow:0 8px 25px rgba(16,185,129,0.3) !important;
        }
        
        .secondary:hover{
            box-shadow:0 12px 35px rgba(16,185,129,0.4) !important;
        }
        
        .how-to-button{
            background:linear-gradient(135deg,#f59e0b 0%,#d97706 100%) !important;
            box-shadow:0 8px 25px rgba(245,158,11,0.3) !important;
            margin-top:30px !important;
        }
        
        .how-to-button:hover{
            box-shadow:0 12px 35px rgba(245,158,11,0.4) !important;
        }
        
        .step{
            font-size:1.3em;
            margin:15px 0;
            color:#94a3b8;
            font-weight:600;
        }
        
        .step-number{
            background:#6366f1;
            color:white;
            width:30px;
            height:30px;
            border-radius:50%;
            display:inline-flex;
            align-items:center;
            justify-content:center;
            font-weight:700;
            margin-right:10px;
            font-size:0.9em;
        }
        
        .user-id{
            margin-top:30px;
            font-size:0.9em;
            color:#64748b;
            background:rgba(30,41,59,0.5);
            padding:10px 20px;
            border-radius:10px;
            border:1px solid #334155;
        }
        
        .instruction{
            font-size:0.95em;
            color:#94a3b8;
            margin:20px 0;
            line-height:1.5;
            background:rgba(30,41,59,0.3);
            padding:15px;
            border-radius:10px;
            border-left:4px solid #6366f1;
        }
        
        @media (max-width:480px){
            .container{padding:30px 25px}
            h1{font-size:1.8em}
            .site-brand{font-size:16px;padding:5px 12px}
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="site-brand">rarestudy.site</div>
    </div>
    
    <div class="container">
        <h1>🔑 Generate Access Keys</h1>
        
        {% if step == 'primary' %}
            <div class="step">
                <span class="step-number">1</span>
                Generate Primary Key
            </div>
            <div class="instruction">
                Click the button below to generate your primary access key. This will redirect you to a verification page.
            </div>
            <a href="{{ primary_url }}" class="key-button">Generate Primary Key</a>
        {% else %}
            <div class="step">
                <span class="step-number">2</span>
                Generate Secondary Key
            </div>
            <div class="instruction">
                Now generate your secondary key to complete the verification process and gain full access.
            </div>
            <a href="{{ secondary_url }}" class="key-button secondary">Generate Secondary Key</a>
        {% endif %}
        
        <a href="{{ how_to_generate_url }}" target="_blank" class="key-button how-to-button">
            📹 How to Generate Keys
        </a>
        
        <div class="user-id">
            User ID: {{ fingerprint|int % 1000000 }}
        </div>
    </div>
</body>
</html>
"""

SUCCESS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Success - RareStudy</title>
    <link rel="icon" type="image/png" href="/static/rarestudylogo.png">
    <style>
        *{margin:0;padding:0;box-sizing:border-box;outline:none;-webkit-tap-highlight-color:transparent;user-select:none}
        body,html{height:100%;font-family:Inter,sans-serif;background:#0f172a;color:#e2e8f0;overflow:hidden}
        
        .header{position:fixed;top:0;left:0;right:0;height:50px;background:rgba(15,23,42,0.95);backdrop-filter:blur(15px);display:flex;align-items:center;z-index:1400;border-bottom:1px solid rgba(30,41,59,0.5);box-shadow:0 4px 20px rgba(0,0,0,0.3);padding:0 15px;justify-content:center}
        
        .site-brand{font-weight:700;font-size:18px;color:#6366f1;letter-spacing:0.3px;background:rgba(79,70,229,0.15);padding:6px 14px;border-radius:10px;border:1px solid rgba(79,70,229,0.3);box-shadow:0 2px 8px rgba(79,70,229,0.2)}
        
        .container{
            position:absolute;
            top:50%;
            left:50%;
            transform:translate(-50%,-50%);
            background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);
            border-radius:20px;
            padding:40px;
            text-align:center;
            max-width:450px;
            width:90%;
            box-shadow:0 20px 60px rgba(0,0,0,0.6);
            border:2px solid rgba(99,102,241,0.3);
            backdrop-filter:blur(10px);
        }
        
        h1{font-size:2.2em;margin-bottom:20px;color:#e2e8f0;font-weight:800;letter-spacing:0.5px}
        
        .success-icon{
            font-size:4em;
            margin:20px 0;
            animation:bounce 2s infinite;
        }
        
        @keyframes bounce{
            0%,20%,50%,80%,100%{transform:translateY(0)}
            40%{transform:translateY(-10px)}
            60%{transform:translateY(-5px)}
        }
        
        .next-button{
            display:inline-block;
            background:linear-gradient(135deg,#10b981 0%,#059669 100%);
            color:white;
            padding:16px 32px;
            text-decoration:none;
            border-radius:15px;
            font-weight:700;
            margin:20px 0;
            transition:all 0.3s ease;
            border:none;
            cursor:pointer;
            font-size:16px;
            letter-spacing:0.5px;
            box-shadow:0 8px 25px rgba(16,185,129,0.3);
        }
        
        .next-button:hover{
            transform:translateY(-3px);
            box-shadow:0 12px 35px rgba(16,185,129,0.4);
        }
        
        .access-button{
            background:linear-gradient(135deg,#6366f1 0%,#4f46e5 100%) !important;
            box-shadow:0 8px 25px rgba(99,102,241,0.3) !important;
        }
        
        .access-button:hover{
            box-shadow:0 12px 35px rgba(99,102,241,0.4) !important;
        }
        
        .success-message{
            font-size:1.1em;
            color:#94a3b8;
            margin:20px 0;
            line-height:1.6;
            background:rgba(30,41,59,0.3);
            padding:20px;
            border-radius:10px;
            border-left:4px solid #10b981;
        }
        
        .celebrate{
            background:rgba(16,185,129,0.1);
            border-left-color:#10b981;
        }
        
        .progress-bar{
            background:rgba(30,41,59,0.5);
            border-radius:10px;
            height:8px;
            margin:20px 0;
            overflow:hidden;
            border:1px solid #334155;
        }
        
        .progress-fill{
            height:100%;
            background:linear-gradient(90deg,#6366f1,#10b981);
            border-radius:10px;
            transition:width 2s ease;
        }
        
        .primary-progress{width:50%}
        .secondary-progress{width:100%}
        
        @media (max-width:480px){
            .container{padding:30px 25px}
            h1{font-size:1.8em}
            .site-brand{font-size:16px;padding:5px 12px}
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="site-brand">rarestudy.site</div>
    </div>
    
    <div class="container">
        {% if key_type == 'primary' %}
            <div class="success-icon">✅</div>
            <h1>Primary Key Generated!</h1>
            <div class="progress-bar">
                <div class="progress-fill primary-progress"></div>
            </div>
            <div class="success-message">
                Great! Your primary key has been successfully generated. Now you need to generate your secondary key to complete the verification process.
            </div>
            <a href="/keygenerate" class="next-button">Generate Secondary Key</a>
        {% else %}
            <div class="success-icon">🎉</div>
            <h1>Access Granted!</h1>
            <div class="progress-bar">
                <div class="progress-fill secondary-progress"></div>
            </div>
            <div class="success-message celebrate">
                Congratulations! Both keys have been generated successfully. You now have full access to RareStudy for the next 24 hours. Enjoy your studies!
            </div>
            <a href="/batches" class="next-button access-button">Access RareStudy</a>
        {% endif %}
    </div>
</body>
</html>
"""

# Update the route to include the new URL
@app.route('/keygenerate')
def key_generate():
    """Generate keys page"""
    fingerprint = get_user_fingerprint_from_request()
    status = get_user_status(fingerprint)
    
    if status['primary'] and status['secondary']:
        return redirect('/batches')
    
    step = 'secondary' if status['primary'] else 'primary'
    
    return render_template_string(
        KEY_GENERATE_HTML,
        step=step,
        primary_url=PRIMARY_URL,
        secondary_url=SECONDARY_URL,
        how_to_generate_url=HOW_TO_GENERATE_URL,
        fingerprint=fingerprint
    )

@app.route('/keyloginsuccess')
def key_login_success():
    """Handle successful key generation with API-based referrer validation"""
    
    blocked_referrers = [
        't.me', 'telegram.org', 'whatsapp.com', 'facebook.com', 'instagram.com',
        'twitter.com', 'x.com', 'discord.com', 'reddit.com', 'youtube.com'
    ]
    
    suspicious_agents = [
        'telegram', 'whatsapp', 'bot', 'crawler', 'curl', 'wget', 'python'
    ]
    
    referrer = request.referrer
    user_agent = request.headers.get('User-Agent', '').lower()
    
    # Basic validation
    if not referrer or request.host in referrer:
        return redirect(url_for('key_generate'))
    
    # Block known platforms and suspicious agents
    for blocked in blocked_referrers:
        if blocked in referrer.lower():
            return redirect(url_for('key_generate'))
    
    for suspicious in suspicious_agents:
        if suspicious in user_agent:
            return redirect(url_for('key_generate'))
    
    fingerprint = get_user_fingerprint_from_request()
    status = get_user_status(fingerprint)
    
    # Already has both keys
    if status['primary'] and status['secondary']:
        return redirect('/batches')
    
    # Handle primary key generation
    if not status['primary']:
        # Try to update primary key status with multiple retries
        max_retries = 3
        for attempt in range(max_retries):
            success = update_key_status(
                fingerprint, 
                primary=True, 
                primary_referrer=referrer
            )
            
            if success:
                # Verify the data was actually saved by checking again
                verification_status = get_user_status(fingerprint)
                if verification_status['primary']:
                    logging.info(f"Primary key successfully saved for user {fingerprint}")
                    return render_template_string(SUCCESS_HTML, key_type='primary')
                else:
                    logging.warning(f"Primary key save verification failed for user {fingerprint}, attempt {attempt + 1}")
            else:
                logging.warning(f"Primary key save failed for user {fingerprint}, attempt {attempt + 1}")
            
            # Wait a bit before retrying
            time.sleep(0.5)
        
        # If all retries failed, redirect back to generate page
        logging.error(f"Failed to save primary key after {max_retries} attempts for user {fingerprint}")
        flash("Failed to save your key. Please try again.", "error")
        return redirect(url_for('key_generate'))
    
    # Handle secondary key generation
    elif status['primary'] and not status['secondary']:
        # Check if same referrer used for both keys
        if referrer == status['primary_referrer']:
            # Same referrer - redirect to generate different key
            return redirect(url_for('key_generate'))
        
        # Try to update secondary key status with multiple retries
        max_retries = 3
        for attempt in range(max_retries):
            success = update_key_status(
                fingerprint, 
                secondary=True, 
                secondary_referrer=referrer
            )
            
            if success:
                # Verify the data was actually saved by checking again
                verification_status = get_user_status(fingerprint)
                if verification_status['secondary']:
                    logging.info(f"Secondary key successfully saved for user {fingerprint}")
                    return render_template_string(SUCCESS_HTML, key_type='secondary')
                else:
                    logging.warning(f"Secondary key save verification failed for user {fingerprint}, attempt {attempt + 1}")
            else:
                logging.warning(f"Secondary key save failed for user {fingerprint}, attempt {attempt + 1}")
            
            # Wait a bit before retrying
            time.sleep(0.5)
        
        # If all retries failed, redirect back to generate page
        logging.error(f"Failed to save secondary key after {max_retries} attempts for user {fingerprint}")
        flash("Failed to save your key. Please try again.", "error")
        return redirect(url_for('key_generate'))
    
    # Fallback
    return redirect('/keygenerate')

@app.route('/verify-access')
def verify_access():
    """Debug route to check user status"""
    fingerprint = get_user_fingerprint_from_request()
    small_fingerprint = int(fingerprint) % 1000000
    status = get_user_status(fingerprint)
    
    return jsonify({
        'fingerprint': small_fingerprint,
        'primary_key': status['primary'],
        'secondary_key': status['secondary'],
        'primary_referrer': status['primary_referrer'],
        'secondary_referrer': status['secondary_referrer']
    })

@app.route('/reset-keys')
def reset_keys():
    """Reset user keys for debugging"""
    fingerprint = get_user_fingerprint_from_request()
    try:
        data = {
            'fingerprint': fingerprint,
            'primaryKeySuccess': False,
            'secondaryKeySuccess': False,
            'primaryReferrer': '',
            'secondaryReferrer': ''
        }
        
        response = requests.post(
            "https://sessionn-579e1179aa8e.herokuapp.com/add-session",
            json=data,
            timeout=50
        )
        
        if response.status_code in [200, 201]:
            return jsonify({'success': True, 'message': 'Keys reset successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to reset keys'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/')
def home():
    """Home route - redirect to batches"""
    return redirect(url_for('batches'))

@app.route('/api/batches')
def get_batches():
    """Get batches with pagination and search functionality"""
    try:
        page = int(request.args.get('page', 0))
        limit = int(request.args.get('limit', 20))
        search = request.args.get('search', '').strip().lower()
        
        # Load all batches
        all_batches = load_batches()
        
        # Add encoded_id to each batch
        for batch in all_batches:
            batch['encoded_id'] = encode_params(batch['_id'])
        
        # Filter batches based on search term
        if search:
            filtered_batches = []
            for batch in all_batches:
                # Search in batch name (case insensitive)
                if search in batch.get('name', '').lower():
                    filtered_batches.append(batch)
            batches_to_paginate = filtered_batches
        else:
            batches_to_paginate = all_batches
        
        # Calculate pagination
        start_index = page * limit
        end_index = start_index + limit
        paginated_batches = batches_to_paginate[start_index:end_index]
        
        return jsonify({
            'success': True,
            'batches': paginated_batches,
            'total': len(batches_to_paginate),
            'page': page,
            'limit': limit,
            'has_more': end_index < len(batches_to_paginate)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'batches': []
        }), 500

@app.route('/api/favourite-batches', methods=['POST'])
def get_favourite_batches():
    """Get batch details for favourite batch IDs"""
    try:
        data = request.get_json()
        batch_ids = data.get('batch_ids', [])
        
        if not batch_ids:
            return jsonify({
                'success': True,
                'batches': []
            })
        
        # Load all batches
        all_batches = load_batches()
        
        # Filter batches that are in favourites and add encoded_id
        favourite_batches = []
        for batch in all_batches:
            if batch.get('_id') in batch_ids:
                batch['encoded_id'] = encode_params(batch['_id'])
                favourite_batches.append(batch)
        
        # Maintain the order of favourite_batches as per batch_ids
        ordered_batches = []
        for batch_id in batch_ids:
            for batch in favourite_batches:
                if batch.get('_id') == batch_id:
                    ordered_batches.append(batch)
                    break
        
        return jsonify({
            'success': True,
            'batches': ordered_batches
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'batches': []
        }), 500

# Update your existing batches route to work with the new API
@app.route('/batches')
def batches():
    """Render batches page template"""
    return render_template('batches.html')

# Your existing favourite routes remain the same
@app.route('/api/get-favourites')
def get_favourites():
    """Get user's favourite batch IDs from session"""
    try:
        favourites = session.get('favourite_batches', [])
        return jsonify({
            'success': True,
            'favourites': favourites
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/toggle-favourite', methods=['POST'])
def toggle_favourite():
    """Toggle batch favourite status in session"""
    try:
        data = request.get_json()
        batch_id = data.get('batch_id')
        
        if not batch_id:
            return jsonify({
                'success': False,
                'error': 'Batch ID is required'
            }), 400
        
        favourites = session.get('favourite_batches', [])
        
        if batch_id in favourites:
            favourites.remove(batch_id)
            action = 'removed'
        else:
            favourites.append(batch_id)
            action = 'added'
        
        session['favourite_batches'] = favourites
        session.permanent = True
        
        return jsonify({
            'success': True,
            'action': action,
            'message': f'Batch {action} {"to" if action == "added" else "from"} favourites'
        })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/data/<encoded_params>')
def subjects(encoded_params):
    params = decode_params(encoded_params)
    
    batch_id = params.get('b')
    if not batch_id:
        return jsonify({"success": False, "data": {"message": "Invalid parameters"}}), 400
    
    token = session.get('token')
    subjects = run_async_optimized(fetch_subjects_async(batch_id, token))
    today_schedule = run_async_optimized(get_todays_schedule(batch_id, token))
    
    return render_template('subjects.html', subjects=subjects, today_schedule=today_schedule, batch_id=batch_id)


def encrypt_video_data(data):
    key = "6f8cce39rarestudy40fca6b3".encode('utf-8')[:16]
    iv = "4a3bfc920rarestudyb67c567".encode('utf-8')[:16]
    
    if isinstance(data, dict):
        data_str = json.dumps(data)
    else:
        data_str = str(data)
    
    padded_text = pad(data_str.encode('utf-8'), AES.block_size)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(padded_text)
    return b64encode(ciphertext).decode('utf-8')

@app.route('/media/<encoded_params>')
def video_player(encoded_params):
    params = decode_params(encoded_params)
    
    url = params.get('url')
    parentId = params.get('parentId')
    childId = params.get('childId')
    
    if not all([url, parentId, childId]):
        return jsonify({"success": False, "data": {"message": "No Data Found"}}), 400
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({"success": True, "data": {"message": "Media request processed"}})
    
    # Check cache first
    try:
        cache_response = requests.get(f"https://cachevideo-0c4774b4d7c4.herokuapp.com/get/cache-video?childId={childId}", verify=False)
        
        if cache_response.status_code == 200:
            cached_data = cache_response.json()
            cached_video = cached_data.get('video')
            
            if cached_video:
                # Check if URL types are different (m3u8 vs mpd)
                cached_url = cached_video.get('data', {}).get('url', '') if 'data' in cached_video else cached_video.get('url', '')
                
                if cached_url and url:
                    cached_is_m3u8 = '.m3u8' in cached_url
                    current_is_mpd = '.mpd' in url
                    cached_is_mpd = '.mpd' in cached_url
                    current_is_m3u8 = '.m3u8' in url
                    
                    # If URL type hasn't changed, check if URL is still valid
                    if not ((cached_is_m3u8 and current_is_mpd) or (cached_is_mpd and current_is_m3u8)):
                        try:
                            url_check = requests.head(cached_url, verify=False)
                            if url_check.status_code == 200:
                                logging.info(f"Using cached video data for childId: {childId}")
                                video_data = cached_video.get('data', {}) if 'data' in cached_video else cached_video
                                encrypted_video = encrypt_video_data(video_data)
                                return render_template('drmplayer.html', encrypted_video=encrypted_video)
                        except:
                            logging.info(f"Cached URL expired for childId: {childId}")
                    else:
                        logging.info(f"URL type changed for childId: {childId}")
    except:
        logging.info(f"No cache found for childId: {childId}")
    
    # Fetch new video data
    logging.info(f"Fetching new video data for childId: {childId}")
    try:
        response = requests.get(
            f"https://pwpaidtoken-dd67b476c95f.herokuapp.com/video/process?url={url}&parentId={parentId}&childId={childId}", 
            verify=False
        )
        response.raise_for_status()
        video_response = response.json()
        
        # Fix success field to be boolean True
        if 'success' in video_response:
            video_response['success'] = True
        
        video = video_response.get('data', {})
        
        # Cache the new data
        try:
            cache_payload = {"childId": childId, "video": video_response}
            requests.post("https://cachevideo-0c4774b4d7c4.herokuapp.com/data", json=cache_payload, verify=False)
            logging.info(f"Video data cached for childId: {childId}")
        except:
            logging.error(f"Failed to cache data for childId: {childId}")
        
    except Exception as e:
        logging.error(f"Error fetching video data: {e}")
        return jsonify({"success": False, "data": {"message": "No Data Found"}}), 500
    
    encrypted_video = encrypt_video_data(video)
    
    return render_template('drmplayer.html', encrypted_video=encrypted_video)


@app.route('/content/<encoded_params>')
def chapters(encoded_params):
    params = decode_params(encoded_params)
        
    batch_id = params.get('b')
    subject_id = params.get('s')
    
    if not batch_id or not subject_id:
        return jsonify({"success": False, "data": {"message": "Invalid parameters"}}), 400
    
    token = session.get('token')
    chapters = run_async_optimized(fetch_chapters_async(batch_id, subject_id, token))
    return render_template('chapters.html', chapters=chapters, batch_id=batch_id, subject_id=subject_id)

@app.route('/stream/<encoded_params>/<section>')
def section_content(encoded_params, section):
    params = decode_params(encoded_params)
        
    batch_id = params.get('b')
    subject_id = params.get('s')
    chapter_id = params.get('c')
    
    if not batch_id or not subject_id or not chapter_id:
        return jsonify({"success": False, "data": {"message": "Invalid parameters"}}), 400
    
    if section not in ['videos', 'notes', 'DppNotes', 'DppVideos']:
        section = 'videos'
    
    token = session.get('token')
    data = run_async_optimized(fetch_chapter_content_async(batch_id, subject_id, chapter_id, section, token))
    
    sections = {'videos': 'Videos', 'notes': 'Notes', 'DppNotes': 'Dpp Notes', 'DppVideos': 'Dpp Videos'}
        
    return render_template('section.html', data=data, section=section, 
                         batch_id=batch_id, subject_id=subject_id, chapter_id=chapter_id, sections=sections)

if __name__ == '__main__':
    app.run(debug=True, threaded=True)