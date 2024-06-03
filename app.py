from flask import Flask, request
from waitress import serve
import requests
import hmac
import hashlib
from urllib.parse import urlencode, quote_plus
import time
import json
import base64

# Function to generate HMAC-SHA256 signature
def generate_signature_tk(secret, path, params):
    sorted_params = sorted((k, v) for k, v in params.items() if k != 'sign' and k != 'access_token')
    base_string = f"{secret}{path}" + ''.join(f"{k}{v}" for k, v in sorted_params) + secret
    return hmac.new(secret.encode(), base_string.encode(), hashlib.sha256).hexdigest()

#encode shipping label to base64
def pdf_to_base64(pdf_url):
    # Send a GET request to the PDF URL
    response = requests.get(pdf_url)
    response.raise_for_status()  # Ensure the request was successful

    # Read the content of the PDF
    pdf_content = response.content

    # Encode the PDF content to base64
    pdf_base64 = base64.b64encode(pdf_content)

    # Convert bytes to a string to make it readable/printable
    base64_string = pdf_base64.decode('utf-8')

    return base64_string

#function to generate yt warehouse signature
def generate_signature_yt(content, user_account, token):
    # Convert the list of dictionaries to a JSON string with sorted keys for consistency
    content_string = json.dumps(content, ensure_ascii=False, sort_keys=True)
    
    # Construct the sign factor by appending userAccount and token directly after the content
    sign_factor = f"{content_string}{user_account}{token}"
    
    # Generate MD5 hash of the combined string
    signature_hash = hashlib.md5(sign_factor.encode('utf-8')).hexdigest()
    
    # Convert the hash to uppercase and return
    return signature_hash.upper()

url_tk_token = "https://auth.tiktok-shops.com/api/v2/token/get"
tk_app_key = "6bv93b6ooeim9"
tk_app_secret = "dd17da7479460a5f0af8e1167eeca7577f247aa4"
param = {}
app = Flask(__name__)
data = {}
tk_base_url = "https://open-api.tiktokglobalshop.com"
full_url = ""
path = ""
timestamp = ""
contents = []

yt_user_account = "Wbb2C6"
yt_token = "954D0F1A8D16809AFAE87F32D46EE3E4"
yt_api_url = "http://fg.yitonggroups.com/api.php?mod=apiManage&act=createOrder"

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if code:
        params = {
            "app_key": tk_app_key, 
            "app_secret": tk_app_secret,
            "auth_code": code,
            "grant_type": "authorized_code"
        }
        response = requests.get(url_tk_token, params=params)
        if response.status_code == 200:
            data = response.json()

            access_token = data["data"]["access_token"]

            #get shop cypher
            path = "/authorization/202309/shops"
            timestamp = str(int(time.time()))
            params = {
                'timestamp': timestamp,
                'app_key': tk_app_key
            }
            signature = generate_signature_tk(tk_app_secret, path, params)
            params['sign'] = signature

            headers = {
                'Content-Type': 'application/json',
                'x-tts-access-token': access_token
            }

            query_string = urlencode(params)
            full_url = f"{tk_base_url}{path}?{query_string}"

            # Send the request
            response = requests.get(full_url, headers=headers)
            print("URL Requested:", full_url)
            print("Response:", response.json())
            data = response.json()

            shop_cipher = data['data']['shops'][0]['cipher']
            shop_id = data['data']['shops'][0]['id']

            #tiktok api call to fetch order, page size = 1 (but will prompt user to input order number later)
            confirm = 'n'
            page_size = 1
            while confirm == 'n':
                page_size = int(input('Please enter package number:(1-50):'))
                confirm = input(f'package number {page_size} is selected, confirm?(enter y to confirm, n to deny)').lower()
            path = "/order/202309/orders/search"
            timestamp = str(int(time.time()))
            params = {
                'app_key': tk_app_key,
                'shop_cipher': shop_cipher,
                'shop_id': shop_id,
                'timestamp': timestamp,
                'version': "202309",
                'order_status': "AWAITING_COLLECTION",
                'page_size': page_size
            }

            # Generate the signature
            signature = generate_signature_tk(tk_app_secret, path, params)
            params['sign'] = signature

            # Set up headers
            headers = {
                'Content-Type': 'application/json',
                'x-tts-access-token': access_token
            }
            query_string = urlencode(params)
            full_url = f"{tk_base_url}{path}?{query_string}"

            # Send the request
            response = requests.post(full_url, headers=headers)
            print("URL Requested:", full_url)
            print("Response:", response.json())
            data = response.json()

            ##another tiktok api call to fetch the label for those orders.
            params = {
                'app_key': tk_app_key,
                'shop_id': shop_id,
                'shop_cipher': shop_cipher,
                'timestamp': timestamp,
                'version': "202309",
                'document_type':'SHIPPING_LABEL'
                }
            package_map = {} #map to store package_id: {sku:sku, qty:#}
            contents = []

            for order in data["data"]["orders"]:

                for package in order["packages"]:
                    package_id = package["id"]
                    if package_id not in package_map:
                        package_map[package_id] = {}
                        #fetch shipping label 
                        path = f"/fulfillment/202309/packages/{package_id}/shipping_documents"
                        params['package_id'] = package_id
                        signature = generate_signature_tk(tk_app_secret, path, params)
                        params['sign'] = signature
                        headers = {
                            'Content-Type': 'application/json',
                            'x-tts-access-token': access_token
                        }
                        query_string = urlencode(params)
                        full_url = f"{tk_base_url}{path}?{query_string}"
                        responses = requests.get(full_url, headers=headers)
                        document_data = responses.json()
                        #label document here!
                        document_base64 = pdf_to_base64(document_data["data"]["doc_url"])

                        #fetch package sku qty detail
                        timestamp = str(int(time.time()))
                        params = {
                            'app_key': tk_app_key,
                            'shop_id': shop_id,
                            'shop_cipher': shop_cipher,
                            'timestamp': timestamp,
                            'version': "202309",
                            'package_id' : package_id
                        }
                        path = f"/fulfillment/202309/packages/{package_id}"
                        signature = generate_signature_tk(tk_app_secret, path, params)
                        params['sign'] = signature
                        headers = {
                            'Content-Type': 'application/json',
                            'x-tts-access-token': access_token
                        }
                        query_string = urlencode(params)
            
                        full_url = f"{tk_base_url}{path}?{query_string}"
                        responses = requests.get(full_url, headers=headers)
                        document_data = responses.json()
                        print(document_data)
                        for order in document_data["data"]["orders"]:
                            for sku_info in order["skus"]:
                                if sku_info["name"] not in package_map[package_id]:
                                    package_map[package_id][sku_info["name"]] = sku_info["quantity"]
                                else:
                                    package_map[package_id][sku_info["name"]] += sku_info["quantity"]

                        sku_info = [{"userSku": sku #need to change
                                        , "qty": package_map[package_id][sku]} for sku in package_map[package_id]]
            
                        content = {
                                "address": "16146 Meadowhouse Ave",
                                "carrierCode":"FHDCAT",
                                "city": "Chino",
                                "countryCode": "US",
                                "label": document_base64,
                                "orderId": package_id,
                                "platform": "tiktok shop",
                                "postCode": "91708",
                                "receiveUser": "test888",
                                "skuInfo": sku_info,
                                "state": "CA",
                                "storeCode": "USYTCAT",
                                "tel": "6266243797",
                                "trackNo": document_data["data"]["tracking_number"]
                            }
                        contents.append(content)

            print(contents)

            #yt api call to generate outbound bill
            signature = generate_signature_yt(contents, yt_user_account, yt_token)

            content_string = json.dumps(contents, ensure_ascii=False, sort_keys=True)

            # Prepare form data for POST request
            form_data = {
                "content": content_string,
                "sign": signature,
                "userAccount": yt_user_account
            }

            # Make the YT Warehouse POST request
            response = requests.post(yt_api_url, data=form_data)
            print("Status Code:", response.status_code)
            print("Response:", response.text)

            return f"Connection success!!!\nPlase go back to terminal to confirm how many order to ship."
        else:
            return f"Failed to retrieve access token:"
    else:
        return 'No code provided by TikTok API', 400

if __name__ == '__main__':
    serve(app, host='127.0.0.1', port=8081)

