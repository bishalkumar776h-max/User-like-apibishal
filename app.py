from flask import Flask, request, Response
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
from google.protobuf.message import DecodeError
import logging
import warnings
from urllib3.exceptions import InsecureRequestWarning
import os

warnings.simplefilter('ignore', InsecureRequestWarning)

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# ✅ Valid API keys (Both work now)
VALID_API_KEYS = {
    "paswan",
    "BISHAL"
}

# Daily limit configuration
DAILY_LIMIT = 120


# ================= Helper functions =================

def load_tokens(server_name):
    try:
        if server_name == "IND":
            file_name = "token_ind.json"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            file_name = "token_br.json"
        else:
            file_name = "token_bd.json"
        if not os.path.exists(file_name):
            app.logger.error(f"Token file {file_name} not found.")
            return None
        with open(file_name, "r") as f:
            tokens_data = json.load(f)
        if isinstance(tokens_data, dict):
            formatted_tokens = []
            for uid, token_str in tokens_data.items():
                formatted_tokens.append({"uid": uid, "token": token_str})
            return formatted_tokens
        return tokens_data
    except Exception as e:
        app.logger.error(f"Token load failed for region: {server_name}. Error: {e}")
        return None


def encrypt_message(plaintext):
    try:
        key = b'Yg&tc%DEuh6%Zc^8'
        iv = b'6oyZDr22E3ychjM%'
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded_message = pad(plaintext, AES.block_size)
        encrypted_message = cipher.encrypt(padded_message)
        return binascii.hexlify(encrypted_message).decode('utf-8')
    except Exception as e:
        app.logger.error(f"Encryption failed. Error: {e}")
        return None


def create_protobuf_message(user_id, region):
    try:
        message = like_pb2.like()
        message.uid = int(user_id)
        message.region = region
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Protobuf creation (like) failed. Error: {e}")
        return None


async def send_request(encrypted_uid, token, url):
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'Expect': "100-continue",
            'X-Unity-Version': "2018.4.11f1",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB55"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=edata, headers=headers) as response:
                if response.status != 200:
                    return response.status
                return await response.text()
    except Exception as e:
        app.logger.error(f"send_request exception occurred: {e}")
        return None


async def send_multiple_requests(uid, server_name, url):
    try:
        region = server_name
        protobuf_message = create_protobuf_message(uid, region)
        if protobuf_message is None:
            return None
        encrypted_uid = encrypt_message(protobuf_message)
        if encrypted_uid is None:
            return None
        tokens = load_tokens(server_name)
        if not tokens:
            return None
        tasks = []
        for i in range(DAILY_LIMIT):
            token = tokens[i % len(tokens)]["token"]
            tasks.append(send_request(encrypted_uid, token, url))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    except Exception as e:
        app.logger.error(f"send_multiple_requests exception occurred: {e}")
        return None


def create_protobuf(uid):
    try:
        message = uid_generator_pb2.uid_generator()
        message.saturn_ = int(uid)
        message.garena = 1
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Protobuf creation (uid) failed. Error: {e}")
        return None


def enc(uid):
    protobuf_data = create_protobuf(uid)
    if protobuf_data is None:
        return None
    return encrypt_message(protobuf_data)


def make_request(encrypt, server_name, token):
    try:
        if server_name == "IND":
            base_url = "https://client.ind.freefiremobile.com"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            base_url = "https://client.us.freefiremobile.com"
        else:
            base_url = "https://clientbp.ppmainecoonghj.com"
        url = f"{base_url}/GetPlayerPersonalShow"
        edata = bytes.fromhex(encrypt)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'Expect': "100-continue",
            'X-Unity-Version': "2018.4.11f1",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB55"
        }
        response = requests.post(url, data=edata, headers=headers, verify=False, timeout=30)
        return decode_protobuf(response.content)
    except Exception as e:
        app.logger.error(f"make_request exception occurred: {e}")
        return None


def decode_protobuf(binary):
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        return items
    except Exception as e:
        app.logger.error(f"Protobuf decode failed structure mismatch: {e}")
        return None


def fetch_player_level_from_api(uid):
    """
    Fetch player level from external API.
    Returns int level on success, None on failure.
    """
    try:
        url = f"https://bishal-paswan.vercel.app/bmw?uid={uid}"
        resp = requests.get(url, verify=False, timeout=15)
        if resp.status_code != 200:
            app.logger.error(f"Level API failed with status {resp.status_code}")
            return None
        data = resp.json()
        level = data.get("basicInfo", {}).get("level")
        if level is None:
            return None
        return int(level)
    except Exception as e:
        app.logger.error(f"fetch_player_level_from_api exception: {e}")
        return None


# ================= Main API endpoint =================

@app.route('/like', methods=['GET'])
def handle_requests():
    # ✅ API key authentication
    api_key = request.args.get("key")
    if not api_key or api_key not in VALID_API_KEYS:
        err_response = {"error": "Invalid or missing API key"}
        return Response(json.dumps(err_response, indent=2), mimetype='application/json'), 401

    uid = request.args.get("uid")
    server_name = request.args.get("region", request.args.get("server", "")).upper()

    if not uid or not server_name:
        err_response = {"error": "UID and region are required parameters"}
        return Response(json.dumps(err_response, indent=2), mimetype='application/json'), 400

    try:
        tokens = load_tokens(server_name)
        if not tokens:
            raise Exception("Failed to load tokens from storage configuration.")
        token = tokens[0]['token']
        encrypted_uid = enc(uid)
        if encrypted_uid is None:
            raise Exception("Encryption process of target UID failed.")

        before = make_request(encrypted_uid, server_name, token)
        if before is None:
            raise Exception("Failed to retrieve initial player data information.")

        data_before = json.loads(MessageToJson(before))
        before_like = data_before.get('AccountInfo', {}).get('Likes', 0)
        try:
            before_like = int(before_like)
        except Exception:
            before_like = 0

        if server_name == "IND":
            like_url = "https://client.ind.freefiremobile.com/LikeProfile"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            like_url = "https://client.us.freefiremobile.com/LikeProfile"
        else:
            like_url = "https://clientbp.ppmainecoonghj.com/LikeProfile"

        asyncio.run(send_multiple_requests(uid, server_name, like_url))

        after = make_request(encrypted_uid, server_name, token)
        if after is None:
            raise Exception("Failed to retrieve player data info after processing likes.")

        data_after = json.loads(MessageToJson(after))
        after_like = int(data_after.get('AccountInfo', {}).get('Likes', 0))
        player_uid = int(data_after.get('AccountInfo', {}).get('UID', 0))
        player_name = str(data_after.get('AccountInfo', {}).get('PlayerNickname', ''))
        player_region = str(data_after.get('AccountInfo', {}).get('PlayerRegion', server_name))

        # ✅ Level from external API (fallback to protobuf if fails)
        player_level = fetch_player_level_from_api(uid)
        if player_level is None:
            try:
                player_level = int(data_after.get('AccountInfo', {}).get('Level', 0))
            except Exception:
                player_level = 0

        like_given = after_like - before_like
        status = 1 if like_given != 0 else 2

        # Daily limit / usage tracking
        daily_limit = DAILY_LIMIT
        used_count = min(like_given, DAILY_LIMIT) if like_given > 0 else 0
        remaining = max(daily_limit - used_count, 0)

        # ✅ Updated response format
        response_data = dict([
            ("LikesGivenByAPI", like_given),
            ("LikesafterCommand", after_like),
            ("LikesbeforeCommand", before_like),
            ("PlayerNickname", player_name),
            ("Level", player_level),
            ("Region", player_region),
            ("UID", player_uid),
            ("status", status),
            ("daily_limit", daily_limit),
            ("used", used_count),
            ("remaining", remaining)
        ])

        json_output = json.dumps(response_data, indent=2, ensure_ascii=False)
        return Response(json_output, mimetype='application/json')

    except Exception as e:
        err_log = {"error": str(e)}
        return Response(json.dumps(err_log, indent=2), mimetype='application/json'), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)