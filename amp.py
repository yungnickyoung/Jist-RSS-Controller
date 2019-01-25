import requests

def ampify_url_list(article_url_list):
    """ Returns a mapping of input URLs to AMP Cache URLs

    Uses the Google AMP API to return a dict of AMP Cache URLs for valid news article URLs.

    Args:
        article_url_list: A list of URLS to articles

    Returns: 
        A dict mapping the valid input URLs to their AMP URLs.
        E.g. { 'url1':'amp_url1', 'url2':'amp_url2', ... }

    Raises:
        Exception: Quota reached - wait a few seconds before attempting to access the API again.
        requests.exceptions.RequestException
    """
    data = { 'urls':article_url_list }
    params = { 'key':'AIzaSyAuOS_oCZCG6s70iDjjcV2IOW1qM0yd2sc' }

    resp = requests.post('https://acceleratedmobilepageurl.googleapis.com/v1/ampUrls:batchGet', params=params, json=data)

    resp_json = resp.json()
    # print (resp_json)

    # Check if quota reached
    try:
        print ('ERROR: RESPONSE CODE ' + resp_json['error']['code'] + ': ' + resp_json['error']['message'])
        raise Exception("Quota reached - wait a few seconds before attempting to access the API again.")
    except KeyError as ke:
        pass

    amp_dict = {}
    invalid_urls = []
    try:
        for AmpUrl in resp_json['ampUrls']:
            amp_dict[AmpUrl['originalUrl']] = AmpUrl['cdnAmpUrl']
    except KeyError as ke:
        print ("No ampUrls in API response")

    try:
        for AmpUrlError in resp_json['urlErrors']:
            errorCode = AmpUrlError['errorCode']
            errorMessage = AmpUrlError['errorMessage']
            originalUrl = AmpUrlError['originalUrl']

            print ('Encountered error "' + errorCode + ': ' + errorMessage)
            print ('Skipping URL... ' + originalUrl)

            invalid_urls.append(originalUrl)

        print ("Skipped the following URLS: ")
        print (invalid_urls)
    except KeyError as ke:
        print ("No urlErrors in API response")
    
    # print ("amp dict:")
    # print (amp_dict)
    return amp_dict