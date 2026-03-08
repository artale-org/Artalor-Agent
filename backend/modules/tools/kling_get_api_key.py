# -----------------------------------------------------------------------------
# © 2026 Artalor
# Artalor Project — All rights reserved.
# Licensed for personal and educational use only.
# Commercial use or redistribution prohibited.
# See LICENSE.md for full terms.
# -----------------------------------------------------------------------------

import time
import jwt
import os
# from modules.utils import load_env

# load_env()

ak = os.environ['KLING_GEN_AK']  # access key
sk = os.environ['KLING_GEN_SK']  # secret key


def encode_jwt_token(ak, sk):
    headers = {
        "alg": "HS256",
        "typ": "JWT"
    }
    payload = {
        "iss": ak,
        "exp": int(time.time()) + 1800,
        "nbf": int(time.time()) - 5
    }
    token = jwt.encode(payload, sk, headers=headers)
    return token


def get_kling_image_api_key():
    api_token = encode_jwt_token(ak, sk)
    # print(api_token)
    return api_token