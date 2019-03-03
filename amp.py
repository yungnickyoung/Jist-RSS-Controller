import requests
import sys
from bcolors import bcolors

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

    # Check if quota reached
    try:
        print (bcolors.FAIL + 'ERROR: RESPONSE CODE ' + str(resp_json['error']['code']) + ': ' + str(resp_json['error']['message']) + bcolors.ENDC, file=sys.stderr)
        raise Exception("Quota reached - wait a few seconds before attempting to access the API again.")
    except KeyError as ke:
        pass

    # Fill the amp dict with the cdn AMP URLs
    amp_dict = {}
    invalid_urls = []
    try:
        for AmpUrl in resp_json['ampUrls']:
            amp_dict[AmpUrl['originalUrl']] = AmpUrl['cdnAmpUrl']
    except KeyError as ke:
        print (bcolors.WARNING + "No ampUrls in API response" + bcolors.ENDC, file=sys.stderr)

    # Record errors returned for any URLS that are not valid for some reason
    try:
        for AmpUrlError in resp_json['urlErrors']:
            errorCode = AmpUrlError['errorCode']
            errorMessage = AmpUrlError['errorMessage']
            originalUrl = AmpUrlError['originalUrl']

            print ('Encountered error "' + str(errorCode) + ': ' + str(errorMessage), file=sys.stderr)
            print ('Skipping URL... ' + str(originalUrl), file=sys.stderr)

            invalid_urls.append(originalUrl)

        print (bcolors.WARNING + "Skipped the following URLS: " + bcolors.ENDC, file=sys.stderr)
        print (invalid_urls, file=sys.stderr)
    except KeyError as ke:
        print (bcolors.GREEN + "No urlErrors in API response" + bcolors.ENDC, file=sys.stderr)
    
    return amp_dict