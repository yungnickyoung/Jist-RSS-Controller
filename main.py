import hashlib
import sys
import json
import requests
import time
import re
import xml.etree.ElementTree as ET
from amp import ampify_url_list
from bcolors import bcolors
from flask import Flask, request, jsonify, abort, Response
from threading import Thread
from bs4 import BeautifulSoup
import os

app = Flask(__name__)
cleanHtmlRegexp = re.compile('<.*?>')

## /ready -- POST
# Initiates RSS processing on a new thread
#
# Returns: 
#   - 202: RSS processing has successfully been initiated
#   - 500: If error occurs while attempting to initiate RSS processing
@app.route("/ready", methods = ['POST'])
def serviceReady():
    try:
        thr = Thread(target=main, args=[])
        print(bcolors.GREEN + "All services ready - RSS feed engine initiated." + bcolors.ENDC, file=sys.stderr)
        thr.start()
    except Exception as e:
        print(bcolors.FAIL + "ERROR while attempting to initiate RSS process: " + str(e) + boclors.ENDC)
        abort(Response(status=500, response="500: Error (500): Unable to start RSS process: " + str(e)))

    return '', 202

# Load list of RSS files from JSON file passed as command-line arg
# Returns:
#   The JSON file as a dict. None if no file provided
def getRSSFeedListFromJSONFile():
    if sys.argv[1] == "":
        return None

    with open(sys.argv[1]) as f:
        print(bcolors.BLUE + "Using RSS file {}".format(sys.argv[1]) + bcolors.ENDC, file=sys.stderr)
        data = json.load(f)

    return data["top_stories"]


def parseFeed(feed):
    domain = feed['domain']
    domainStr = "(" + domain + ")"
    print(bcolors.BOLD + bcolors.UNDERLINE + "# # # # STARTING PARSE FEED FOR DOMAIN {} # # # #".format(domain) + bcolors.ENDC + bcolors.ENDC, file=sys.stderr)

    # Retrieve the RSS page for the given feed.
    # Max 20 attempts before printing an error and returning.
    attempts = 20
    while True:
        try:
            resp = None
            resp = requests.get(feed['rss_url'])
            break
        except requests.exceptions.ConnectionError as err: # Connection refused --> abort (URL is probably wrong)
            print(bcolors.FAIL + domainStr + " ERROR: Connection refused for RSS URL for domain {} (exceeded 20 attempts)\nSkipping domain . . .".format(domain) + bcolors.ENDC, file=sys.stderr)
            raise
        except requests.exceptions.ContentDecodingError as err: # Huffington Post will seemingly randomly throw this error
            if attempts <= 0:
                print(bcolors.FAIL + domainStr + " ERROR: Decoding error for RSS URL for domain {} (exceeded 20 attempts)\nSkipping domain . . .".format(domain) + bcolors.ENDC, file=sys.stderr)
                raise

            if (resp and resp.status_code == requests.codes.too_many_requests):
                time.sleep(10)

            attempts -= 1
            time.sleep(2)
            continue

    # Parse the RSS file as XML.
    # Max 20 attempts before printing an error and returning.
    attempts = 20
    while True:
        try:
            tree = ET.fromstring(resp.text)
            break
        except ET.ParseError as err: # Huffington Post will seemingly randomly throw this error
            if attempts <= 0:
                print(bcolors.FAIL + domainStr + " ERROR: Unable to parse RSS feed from domain {} (exceeded 20 attempts)\nSkipping domain . . .".format(domain) + bcolors.ENDC, file=sys.stderr)
                raise

            attempts -= 1
            continue

    article_list = []
    for item in tree.findall('./channel/item'):
        ad = False # Do not keep any items labeled as ads
        error_encountered = False # Only keep items which do not encounter errors during this process

        for child in item:
            # Get item's article url
            if(child.tag == 'link'):
                articleUrl = child.text.strip()

                # Check the URL Hash to see if the article is already stored
                urlHash = hashlib.md5(articleUrl.encode()).hexdigest()
                try:
                    print(domainStr + " Checking hash of " + articleUrl + " (" + urlHash + ")", file=sys.stderr)
                    resp = requests.get(url="http://jist-database-api:5003/articleExists", params={"url_hash": urlHash})
                except Exception as e:
                    print(bcolors.WARNING + domainStr + " WARNING: An error occured while checking hash: " + str(e) + bcolors.ENDC, file=sys.stderr)
                    error_encountered = True
                    break

                if resp.status_code == 200: # Article exists
                    print(domainStr + " Hash " + str(urlHash) + " already exists, skipping article...", file=sys.stderr)
                    error_encountered = True
                    break
                elif resp.status_code == 404:
                    print(domainStr + " Hash does not yet exist, proceeding with article...", file=sys.stderr)
                else:
                    print(bcolors.WARNING + domainStr + " Received abnormal error code ({0}) when sending request to /articleExists with hash {1}\nSkipping article...".format(resp.status_code, urlHash + bcolors.ENDC), file=sys.stderr)

                # Follow URL to get "real" URL in case there is a redirect
                attempts = 20
                try:
                    resp = requests.get(articleUrl, headers={ 'Accept-Encoding': 'gzip' })
                    articleUrl = resp.url
                except requests.exceptions.ConnectionError as err:
                    print(bcolors.WARNING + domainStr + " WARNING: Unable to connect to article URL {0} (exceeded 20 attempts)\nSkipping URL...".format(articleUrl) + bcolors.ENDC, file=sys.stderr)
                    error_encountered = True
                    break
                except requests.exceptions.ContentDecodingError as err:
                    if attempts <= 0:
                        print(bcolors.WARNING + domainStr + " WARNING: Decoding error for article URL {0} (exceeded 20 attempts)\nSkipping URL...".format(articleUrl) + bcolors.ENDC, file=sys.stderr)
                        error_encountered = True
                        break

                    if resp and resp.status_code == requests.codes.too_many_requests:
                        time.sleep(10)

                    attempts -= 1
                    time.sleep(2)
                    continue

                # Check if this article is an ad
                if( ("www." + domain not in articleUrl) and ("http://" + domain not in articleUrl) and ("https://" + domain not in articleUrl) and (domain + ".com" not in articleUrl) and (domain + ".org" not in articleUrl) ):
                    ad = True
                    continue

            # Get article description
            if(child.tag == 'description'):
                description = child.text

                # Sometimes there are HTML elements in the description which we need to get rid of
                try:
                    description = removeHTML(description)
                except Exception as e:
                    print(bcolors.WARNING + "Error removing HTML from description: " + str(e) + bcolors.ENDC, file=sys.stderr)
                    pass
 
                # Sometimes there is no description provided (e.g. some articles for politico), so we must encase stripping in a try-except block
                try:
                    description = description.strip()
                except:
                    pass

            # Get article title
            if(child.tag == 'title'):
                title = child.text

                # Sometimes there is no title provided (e.g. some slideshow "articles" for nbcnews), so we must encase stripping in try-except
                try:
                    title = title.strip()
                except:
                    pass

            # Get article publish date
            if (child.tag == 'pubDate'):
                pub_date = child.text.strip()

        if (ad == False and error_encountered == False):
            article_entry = { 'domain': domain, 'title': title, 'description': description, 'thumbnail_url':'', 'pub_date':pub_date, 'article_url': articleUrl, 'amp_url':'', 'summary':'', 'url_hash': urlHash }
            article_list.append(article_entry)

    return article_list


def main():
    try:
        rssFeedList = getRSSFeedListFromJSONFile()
    except FileNotFoundError as fnferr:
        print(bcolors.FAIL + "ERROR: No such file or directory: {}\nAborting RSS engine...".format(sys.argv[1]) + bcolors.ENDC, file=sys.stderr)
        return
    
    if rssFeedList is None:
        print(bcolors.FAIL + "ERROR: No RSS feed JSON filename argument provided\nAborting RSS engine..." + bcolors.ENDC, file=sys.stderr)
        return

    bigList = []

    for feed in rssFeedList:
        try:
            bigList.append(parseFeed(feed))
        except requests.exceptions.ConnectionError:
            continue
        except requests.exceptions.ContentDecodingError:
            continue
        except ET.ParseError:
            continue

    # Get all valid article URLs from all news sources
    urlList = []
    for smallList in bigList:
        for item in smallList:
            urlList.append(item['article_url'])

    print (bcolors.HEADER + "TOTAL ARTICLE URLS: " + str(len(urlList)) + bcolors.ENDC, file=sys.stderr)

    # Fetch AMP urls for every article
    print("Fetching AMP urls...", file=sys.stderr)
    ampDictList = []
    for i in range (0, len(urlList), 50):
        while True:
            print(bcolors.WARNING + str(len(urlList) - i) + " articles left" + bcolors.ENDC, file=sys.stderr)
            try:
                ampDict = ampify_url_list(urlList[i:i+50])
            except Exception as e:
                print(bcolors.WARNING + "Error in ampify_url_list: " + str(e) + bcolors.ENDC, file=sys.stderr)

                # Wait some time before retrying
                print(bcolors.WARNING + "Waiting 30 seconds..." + bcolors.ENDC, file=sys.stderr)
                sys.stderr.flush()
                time.sleep(30)
                continue
            break

        ampDictList.append(ampDict)

    # Update all entries with their amp urls
    print(bcolors.BLUE + "Updating entries with amp urls..." + bcolors.ENDC, file=sys.stderr)
    for ampDict in ampDictList:
        for key, value in ampDict.items():
            found_entry = False
            # Find the entry in bigList with the same article_url as this item
            for smallList in bigList:
                for entry in smallList:
                    if entry['article_url'] == key:
                        entry['amp_url'] = value
                        found_entry = True
                        break

                if (found_entry == True):
                    break

    htmlParseCodeCount = {}
    databaseCodeCount = {}

    for smallList in bigList:
        for item in smallList:
            # Skip items with empty AMP urls
            if item['amp_url'] == '':
                continue
            
            # Send POST for getting summary for article
            resp = requests.post(url='http://jist-html-parser:5001/parse', json=item)

            # Print title, domain, and HTTP response code
            print(bcolors.HEADER + "({}) ".format(item['domain']) + item['title'] + bcolors.ENDC, file=sys.stderr)
            if resp.status_code == 200:
                print(bcolors.BLUE + "    HTML Parser response: {}".format(resp.status_code) + bcolors.ENDC, file=sys.stderr)
            else:
                print(bcolors.WARNING + "    HTML Parser response: {}".format(resp.status_code) + bcolors.ENDC, file=sys.stderr)

            # Keep track of response code count for displaying at the end
            try:
                htmlParseCodeCount[resp.status_code] += 1
            except:
                htmlParseCodeCount[resp.status_code] = 1

            # Try to get summary
            try:
                summary = resp.json()['summary']
            except json.decoder.JSONDecodeError as jde_error: # URL was probably invalid or weird
                item['amp_url'] = '' # Mark the article as to be discarded and continue
                continue

            item['summary'] = summary

            print("    " + str(summary), file=sys.stderr)

            # Send to database
            resp = requests.post(url='http://jist-database-api:5003/postArticle', json=item)

            if resp.status_code == 201:
                print(bcolors.GREEN + "    Database response: 201 (Success)" + bcolors.ENDC, file=sys.stderr)
            elif resp.status_code == 400:
                print(bcolors.WARNING + "    Database response: 400 (Missing data?)" + bcolors.ENDC, file=sys.stderr)
            elif resp.status_code == 500:
                print(bcolors.FAIL + "    Database response: 500 (Error occurred during INSERT)" + bcolors.ENDC, file=sys.stderr)
            else:
                print(bcolors.FAIL + "    Database response: {} (UNUSUAL)".format(resp.status_code) + bcolors.ENDC, file=sys.stderr)

            # Keep track of response code count for displaying at the end
            try:
                databaseCodeCount[resp.status_code] += 1
            except:
                databaseCodeCount[resp.status_code] = 1

    print(bcolors.GREEN + "HTML Parser responses: {}".format(str(htmlParseCodeCount)) + bcolors.ENDC, file=sys.stderr)
    print(bcolors.GREEN + "Database responses: {}".format(str(databaseCodeCount)) + bcolors.ENDC, file=sys.stderr)
    sys.stderr.flush()

def removeHTML(rawHTML):
    cleanText = re.sub(cleanHtmlRegexp, '', rawHTML)
    return cleanText

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
    
