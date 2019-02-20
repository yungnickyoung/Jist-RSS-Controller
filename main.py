import hashlib
import sys
import json
import requests
import time
import xml.etree.ElementTree as ET
from amp import ampify_url_list
from flask import Flask, request, jsonify
from threading import Thread
import os

app = Flask(__name__)

# Tell RSS-Controller that a microservice is ready
# When all microservices are ready, begin
@app.route("/ready", methods = ['POST'])
def serviceReady():
	app.logger.info("Service responded: ready.")
	app.CONNECTED_SERVICES += 2
	if(app.CONNECTED_SERVICES >= app.MAX_SERVICES):
		thr = Thread(target=main, args=[])
		thr.start()
		app.logger.info("All services ready, starting RSS feed engine:")

	return ('', 204)

def loadJson():
	with open(sys.argv[1]) as f:
		data = json.load(f)

	return data["top_stories"]

def parseFeed(feed):
	domain = feed['domain']
	app.logger.info('--------------------------------%s---------------------------------' %(domain))

	headers = { 'Accept-Encoding': 'gzip' }

	# Retrieve the RSS page for the given feed.
	# Max 20 attempts before printing an error and returning.
	curAttempts = 0
	MAX_ATTEMPTS = 20
	while True:
		try:
			resp = None
			resp = requests.get(feed['rss_url'])
			break
		except requests.exceptions.ConnectionError as err: # Connection refused --> abort
			app.logger.info('############################ CONNECTION ERROR #############################') # The current link for foxnews appears to be down
			app.logger.info(err)
			raise
		except requests.exceptions.ContentDecodingError as err:
			if curAttempts > MAX_ATTEMPTS:
				app.logger.info('############################ DECODING ERROR #############################') # huffingtonpost will sometimes throw this error
				app.logger.info(err)
				raise

			if (resp and resp.status_code == requests.codes.too_many_requests):
				time.sleep(10)

			curAttempts += 1
			time.sleep(2)
			continue

	# Parse the RSS file as XML.
	# Max 20 attempts before printing an error and returning.
	curAttempts = 0
	while True:
		try:
			tree = ET.fromstring(resp.text)
			break
		except ET.ParseError as err:
			if curAttempts > MAX_ATTEMPTS:
				app.logger.info('############################ PARSING ERROR #############################') # huffingtonpost will sometimes throw this error
				app.logger.info(err)
				time.sleep(2)
				raise

			curAttempts += 1
			continue

	article_list = []
	for item in tree.findall('./channel/item'):
		ad = False # We do not keep any items labeled as ads
		error_encountered = False # Only keep items which do not encounter errors during this process

		for child in item:
			# Get item's article url
			if(child.tag == 'link'):
				article_url = child.text.strip()

				# check the pre-redirect url to check database conflicts
				url_hash = hashlib.md5(article_url.encode()).hexdigest()
				hash_check = ""
				try:
					app.logger.info("Checking hash of " + article_url + " (" + url_hash + ")")
					hash_check = requests.get(url="http://jist-database-api:5003/articleExists", json={'url_hash': url_hash})
				except Exception as e:
					app.logger.info("Error checking hash: " + str(e))

				if(hash_check.json()[0][0] > 0):
					app.logger.info("Hash: " + str(hash_check) + " exists, ignoring")
					continue
				else:
					app.logger.info("Hash doesn't exist, moving on.")

				# get post-redirect URL
				curAttempts = 0
				try:
					resp = requests.get(article_url, headers=headers)
					article_url = resp.url
				except requests.exceptions.ConnectionError as err:
					app.logger.info("ERROR GETTING URL: " + article_url + " IN DOMAIN " + domain)
					app.logger.info(err)
					error_encountered = True
					break
				except requests.exceptions.ContentDecodingError as err:
					if curAttempts > MAX_ATTEMPTS:
						app.logger.info('############################ DECODING ERROR GETTING REDIR #############################') # huffingtonpost will sometimes throw this error
						app.logger.info(err)
						error_encountered = True
						break

					if (resp and resp.status_code == requests.codes.too_many_requests):
						time.sleep(10)

					curAttempts += 1
					time.sleep(2)
					continue

				# Check if this article is an ad
				if( ("www." + domain not in article_url) and ("http://" + domain not in article_url) and ("https://" + domain not in article_url) and (domain + ".com" not in article_url) and (domain + ".org" not in article_url) ):
					ad = True
					continue

			# Get article description
			if(child.tag == 'description'):
				description = child.text
 
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
			article_entry = { 'domain': domain, 'title': title, 'description': description, 'pub_date':pub_date, 'article_url': article_url, 'amp_url':'', 'summary':'', 'url_hash': url_hash }
			#app.logger.info(article_entry)
			article_list.append(article_entry)

	return article_list

def main():
	feed_list = loadJson()
	big_list = []
	for entry in feed_list:
		try:
			big_list.append(parseFeed(entry))
		except requests.exceptions.ConnectionError:
			continue
		except requests.exceptions.ContentDecodingError:
			continue
		except ET.ParseError:
			continue

	# Get all valid article URLs from all news sources
	url_list = []
	for small_list in big_list:
		for item in small_list:
			url_list.append(item['article_url'])

	# Fetch AMP urls for every article
	app.logger.info("Fetching AMP urls...")
	amp_dict_list = []
	for i in range (0, len(url_list), 50):
		while True:
			try:
				amp_dict = ampify_url_list(url_list[i:i+50])
			except Exception as e:
				app.logger.info (e)
				# Wait some time before retrying
				app.logger.info ("Waiting 30 seconds...")
				app.logger.info(str(len(url_list) - i) + " articles left")
				time.sleep(30)
				continue
			break

		amp_dict_list.append(amp_dict)

	# Update all entries with their amp urls
	app.logger.info("Updating entries with amp urls...")
	for amp_dict in amp_dict_list:
		for key, value in amp_dict.items():
			found_entry = False
			# Find the entry in big_list with the same article_url as this item
			for small_list in big_list:
				for entry in small_list:
					if entry['article_url'] == key:
						entry['amp_url'] = value
						found_entry = True
						break

				if (found_entry == True):
					break

	code_count = {}
	for small_list in big_list:
		for item in small_list:
			# Skip items with empty AMP urls
			if item['amp_url'] == '':
				continue
			
			# Send POST for getting summary for article
			resp = requests.post(url='http://jist-html-parser:5001/parse', json=item)

			app.logger.info ('Response <' + str(resp.status_code) + '>')
			app.logger.info (item['title'] + ' - ' + item['domain'])

			try:
				code_count[resp.status_code] += 1
			except:
				code_count[resp.status_code] = 1

			if resp.status_code != requests.codes.ok:
				app.logger.info ("NON-200 DETECTED")
				# wait = input("Press Enter to continue...")

			# Try to get summary
			try:
				summary = resp.json()['summary']
			except json.decoder.JSONDecodeError as jde_error: # URL was probably invalid or weird
				item['amp_url'] = '' # Mark the article as to be discarded and continue
				continue

			item['summary'] = summary

			app.logger.info (summary)

			# Send to database
			app.logger.info('Storing in database')
			requests.post(url='http://jist-database-api:5003/postArticle', json = item)



	app.logger.info(code_count)

if __name__ == "__main__":
	# Number of services to connect to RSS controller before starting
	app.MAX_SERVICES = 1
	app.CONNECTED_SERVICES = 0

	app.run(debug=True, host='0.0.0.0', port=5000)
	
