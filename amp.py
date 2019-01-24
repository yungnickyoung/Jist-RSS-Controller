import requests

def ampify_url(url):
    data = { 'urls':[url,] }
    params = { 'key':'AIzaSyAuOS_oCZCG6s70iDjjcV2IOW1qM0yd2sc' }
    resp = requests.post('https://acceleratedmobilepageurl.googleapis.com/v1/ampUrls:batchGet', params=params, json=data)

    resp_json = resp.json()
    return resp_json['ampUrls'][0]['cdnAmpUrl'].strip()
