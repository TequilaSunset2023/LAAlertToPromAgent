from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoServiceError
from typing import List, Optional
import os
import requests
import urllib.parse
import time
import re
from pathlib import Path

def update_env_file(key, value):
    """
    更新 .env 文件中的环境变量值，如果变量不存在则添加
    
    Args:
        key (str): 环境变量名
        value (str): 环境变量值
    """
    # 获取上级目录的 .env 文件路径
    env_path = Path(__file__).parent.parent.parent / '.env'
    
    # 读取现有的 .env 文件内容
    content = ""
    if env_path.exists():
        with open(env_path, 'r') as file:
            content = file.read()
    
    # 检查变量是否已存在
    pattern = re.compile(r'^' + re.escape(key) + r'=.*$', re.MULTILINE)
    if pattern.search(content):
        # 替换现有变量
        new_content = pattern.sub(f'{key}={value}', content)
    else:
        # 添加新变量
        new_content = content
        if new_content and not new_content.endswith('\n'):
            new_content += '\n'
        new_content += f'{key}={value}\n'
    
    # 写入 .env 文件
    with open(env_path, 'w') as file:
        file.write(new_content)

def get_kusto_token() -> str:
    """
    Get a Kusto authentication token by making a token request to Azure AD.
    
    Returns:
        str: The authentication token for Kusto queries
    
    Raises:
        Exception: If there's an error fetching the token
    """
    try:
        # Check if we already have a valid access token in environment variables
        existing_access_token = os.getenv("KUSTOACCESSTOKEN")
        expiry_time = os.getenv("KUSTOACCESSTOKENEXPIRY")
        
        # Check if token exists and is not expired
        current_time = int(time.time())
        if existing_access_token and expiry_time and current_time < int(expiry_time):
            return existing_access_token
            
        url = "https://login.microsoftonline.com/organizations/oauth2/v2.0/token"
        
        # Try to get refresh token from environment variables first
        refresh_token = os.getenv("KUSTOREFRESHTOKEN")
        # If not found, use the hardcoded default
        if not refresh_token:
            refresh_token = "1.AVMB6q7FzcUVtk2wefyt0lBdwlKOgfm9UD5GiTKhZQvT-tJTAT5TAQ.AgABAwEAAABVrSpeuWamRam2jAF1XRQEAwDs_wUA9P-Q1UFevOwsYEW34ykGTOOU-3Wze7AoqF5KiIeZCdmAd3PsSaq3-7ViwUCk5NZx-3j9dXehSFhQruTPdr-R-vQ3_5ug7fjsN7A0xDLyxLxTM_A4wj-sEnB-8lhdHkRngu5s8Xf9QVvx-FGjbLgC542mrbw8y-P7Zem9b3WS66rJt4S4d2Xd7cKQxFYTNmnm3J8W6RZEvntIC375DdKdTXbLYbbmpcsOkWmm5Sfqbrzupsrz9JewvIfebab4-FPpPmWKcBn4BsMfk8mDsVuknNTvnSHEAh8cPhOD1uQA2eQPWm_3U0bRfyGtY0IIePmGnLiXY4Iq5893s_Ao5rPfyLkSiUAIsS3Ts2Gzq1U4jJ5d3Bbd47Un3ePrNRzxsIDBUxLLJFDT4BZEfJx1KM_47ebUX04euMNcc-Wqn-d7sQQSaMARp_UpE-75YgZLbdYS4k9vGGbUOU2EeHfcx20ute83TIanajtZHuhdwWE_FMGLqyuLAwhMl4OqbvqEmVn4dAkZL5IppgjR-MlUx3dvpyhXFHa7DW-vHOYRHe27VnLLgYpsDiidhfAykkxIpgOydZ2o6Pft82vinWrXVHzqSEOKMXTFobQAHtLm22srIpgojFz8hmqte0aCX4_uz995C4AfejdCjEBi71t8I6WoC6TkyWZ2Nm4xLJ3FIkf67g4G8IJKBXmg1JhoaPU8JrvDSbWtuzrTXYZbmgQ7OQKW5jC0Okx0742TpdJ4NqwmsTis_kbeiEhn0D5V8DAFFX2nyKUa2sth5Qvre1D-Vyvr-b_LIoPOq5esG2g3Vcp_mDBDPhnHHVpZdqtq2n9GzAvQ0ZI9itB1xl3MEjHpub-SHfzMGOmhTeyX0N9_XvaOd6cBTEEnxIinv5-Ul-JREj9SAm-waXZZwbstUrTApvSog9Amk3d4CjDEgA5o-meEIrBNJA4-LJIa75shVrJCf2Ds6mQaENqLrKEmMU5BhJFCRD1lZ4oZuFWmazl63UmuyrZnyTEqcgGgG_abTAxE4vHHSMWueMP0JVRYULaZRL6T6Mz-5CjXARQ"
        
        # Form data parameters - 使用更简单的方式定义，确保编码正确
        data = {
            "client_id": "f9818e52-50bd-463e-8932-a1650bd3fad2",
            "redirect_uri": "https://dataexplorer.azure.com/blank.html",
            "scope": "https://kusto.kusto.windows.net/.default openid profile offline_access",
            "grant_type": "refresh_token",
            "client_info": "1",
            "x-client-SKU": "msal.js.browser",
            "x-client-VER": "3.27.0",
            "x-ms-lib-capability": "retry-after, h429",
            "x-client-current-telemetry": "5|61,0,,,|,",
            "x-client-last-telemetry": "5|26|||0,0",
            "refresh_token": refresh_token,
            "X-AnchorMailbox": "Oid:d872f973-3fc3-477e-b32d-399b6bc6ba0f@cdc5aeea-15c5-4db6-b079-fcadd2505dc2"
        }
        
        # Headers
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://dataexplorer.azure.com",
            "priority": "u=1, i",
            "Referer": "https://dataexplorer.azure.com/",
            "sec-ch-ua": '"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": 'empty',
            "sec-fetch-mode": 'cors',
            "sec-fetch-site": 'cross-site'
        }
        
        # 打印请求信息，帮助调试
        print(f"Sending request to {url}")
        print(f"Headers: {headers}")
        
        # 使用请求库的正确编码方式发送表单数据
        # Make POST request
        response = requests.post(
            url, 
            data=data,  # requests 会自动正确编码表单数据
            headers=headers
        )
        
        # 打印响应状态和内容，帮助调试
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {response.headers}")
        if response.status_code != 200:
            print(f"Error response: {response.text}")
            
        response.raise_for_status()  # Raise exception for HTTP errors
        
        # Parse response JSON and extract tokens
        token_data = response.json()
        access_token = token_data.get("access_token")
        new_refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)  # Default to 1 hour if not provided
        
        # Calculate expiry time and store it with tokens
        expiry_timestamp = int(time.time()) + int(expires_in)
        
        # 更新环境变量
        os.environ["KUSTOACCESSTOKEN"] = access_token
        os.environ["KUSTOACCESSTOKENEXPIRY"] = str(expiry_timestamp)
        if new_refresh_token:
            os.environ["KUSTOREFRESHTOKEN"] = new_refresh_token
        
        # 同时更新 .env 文件
        update_env_file("KUSTOACCESSTOKEN", access_token)
        update_env_file("KUSTOACCESSTOKENEXPIRY", str(expiry_timestamp))
        if new_refresh_token:
            update_env_file("KUSTOREFRESHTOKEN", new_refresh_token)
        
        return access_token
        
    except Exception as e:
        print(f"Error in get_kusto_token: {str(e)}")
        raise Exception(f"Failed to fetch Kusto token: {str(e)}")

def execute_kusto_query(
    cluster_url: str,
    database_name: str,
    query: str,
    pack: bool = True,
) -> List[str]:
    """
    Execute a Kusto query in a specified database and return the results as a list of strings.
    
    Args:
        cluster_url (str): The URL of the Kusto cluster (e.g., "https://myinstance.kusto.windows.net")
        database_name (str): The name of the database to query
        query (str): The Kusto query to execute
    
    Returns:
        List[str]: A list of result strings from the Kusto query
    
    Raises:
        KustoServiceError: If there's an error executing the query
        ValueError: If invalid connection parameters are provided
    """
    try:
        # Set up the connection to Kusto using default user authentication
        # kcsb = KustoConnectionStringBuilder.with_az_cli_authentication(cluster_url)

        # Get token from web request instead of environment variable
        token = os.getenv("KUSTOTOKEN")
        kcsb = KustoConnectionStringBuilder.with_aad_user_token_authentication(cluster_url, token)
        
        # Create the client
        client = KustoClient(kcsb)
        
        # pack all columns into a single string
        if pack:
            # Pack all columns into a single string
            query = f"""
                {query.strip().strip(';')}
                | project ResultAsJson = tostring(pack_all())
            """

        # Execute the query
        response = client.execute(database_name, query)
        
        # Process the results
        result_list = []
        primary_results = response.primary_results[0]
        
        # Extract data rows as strings
        for row in primary_results:
            if len(row) == 1:
                result_list.append(str(row[0]))
            else:
                result_list.append(str(row))
        
        return result_list
    
    except KustoServiceError as e:
        raise KustoServiceError(f"Error executing Kusto query: {str(e)}")
    except Exception as e:
        raise ValueError(f"Failed to connect to Kusto or execute query: {str(e)}")