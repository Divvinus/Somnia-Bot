import requests

cookies = {
    '_gcl_au': '1.1.394771002.1740675696',
    '___adrsbl_nonce': '599dadd42819a1e5b99eb72f29f20524',
    '_ga': 'GA1.1.1186785516.1740675697',
    '_hjSessionUser_4948525': 'eyJpZCI6ImIyMDQ3ZmMyLTM5Y2QtNTI0OS1iM2FiLWVkMjk4ZTQ2OWRlMCIsImNyZWF0ZWQiOjE3NDA2NzU2OTc0MDgsImV4aXN0aW5nIjp0cnVlfQ==',
    '_hjSession_4948525': 'eyJpZCI6IjI4MTQwZDAyLTMyMmItNGEyNS05MWFhLTlhZTJkMTgzN2VmMSIsImMiOjE3NDIzOTM2NzEzNjgsInMiOjAsInIiOjAsInNiIjowLCJzciI6MCwic2UiOjAsImZzIjowfQ==',
    '_rdt_uuid': '1740675696572.3639c2eb-6a75-45b2-b07a-c9514219d59a',
    '_ga_VRC3ZXBRT1': 'GS1.1.1742393670.26.1.1742394737.49.0.0',
}

headers = {
    'authority': 'quest.somnia.network',
    'accept': '*/*',
    'accept-language': 'ru,en-US;q=0.9,en;q=0.8',
    'authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOjIzMDQ0Nzc2LCJyb2xlIjoiVVNFUiIsInVzZXJBZGRyZXNzIjoiMHg2M2Y3OGVjY2IzNjA1MTZjMTNkZDQ4Y2EzY2EzZjcyZWIzZDRmZDNlIiwiaWF0IjoxNzQyMzg1NTAzLCJleHAiOjE3NDI0NzE5MDN9.g9em1tYekLN-ZMVyvBe0nRIp-tRRV6tsWxSdNKhPfmk',
    'cache-control': 'no-cache',
    'content-type': 'application/json',
    # 'cookie': '_gcl_au=1.1.394771002.1740675696; ___adrsbl_nonce=599dadd42819a1e5b99eb72f29f20524; _ga=GA1.1.1186785516.1740675697; _hjSessionUser_4948525=eyJpZCI6ImIyMDQ3ZmMyLTM5Y2QtNTI0OS1iM2FiLWVkMjk4ZTQ2OWRlMCIsImNyZWF0ZWQiOjE3NDA2NzU2OTc0MDgsImV4aXN0aW5nIjp0cnVlfQ==; _hjSession_4948525=eyJpZCI6IjI4MTQwZDAyLTMyMmItNGEyNS05MWFhLTlhZTJkMTgzN2VmMSIsImMiOjE3NDIzOTM2NzEzNjgsInMiOjAsInIiOjAsInNiIjowLCJzciI6MCwic2UiOjAsImZzIjowfQ==; _rdt_uuid=1740675696572.3639c2eb-6a75-45b2-b07a-c9514219d59a; _ga_VRC3ZXBRT1=GS1.1.1742393670.26.1.1742394737.49.0.0',
    'dnt': '1',
    'origin': 'https://quest.somnia.network',
    'pragma': 'no-cache',
    'referer': 'https://quest.somnia.network/campaigns/9',
    'sec-ch-ua': '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
}

json_data = {
    'questId': 42,
}

response = requests.post('https://quest.somnia.network/api/onchain/erc20-token', cookies=cookies, headers=headers, json=json_data)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"questId":42}'
#response = requests.post('https://quest.somnia.network/api/onchain/erc20-token', cookies=cookies, headers=headers, data=data)
print(response.text)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"walletAddress":"0x63F78ecCB360516C13Dd48CA3CA3f72eB3D4Fd3e","message":"hi"}'
#response = requests.post('https://quills.fun/api/mint-nft', cookies=cookies, headers=headers, data=data)