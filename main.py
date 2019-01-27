
import json
import requests
import time
import xml.etree.ElementTree as ET
from amp import ampify_url_list

def loadJson():
	with open('feeds.json') as f:
		data = json.load(f)

	return data["top_stories"]

def parseFeed(feed):
	domain = feed['domain']
	print('--------------------------------%s---------------------------------' %(domain))


	# Retrieve the RSS page for the given feed.
	# Max 20 attempts before printing an error and returning.
	curAttempts = 0
	MAX_ATTEMPTS = 20
	while True:
		try:
			resp = requests.get(feed['rss_url'])
			break
		except requests.exceptions.ConnectionError as err: # Connection refused --> abort
			print('############################ CONNECTION ERROR #############################') # The current link for foxnews appears to be down
			print(err)
			raise
		except requests.exceptions.ContentDecodingError as err:
			if curAttempts > MAX_ATTEMPTS:
				print('############################ DECODING ERROR #############################') # huffingtonpost will sometimes throw this error
				print(err)
				raise

			curAttempts += 1
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
				print('############################ PARSING ERROR #############################') # huffingtonpost will sometimes throw this error
				print(err)
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
				try:
					resp = requests.get(article_url)
					article_url = resp.url
				except requests.exceptions.ConnectionError as err:
					print("ERROR GETTING URL: " + article_url + " IN DOMAIN " + domain)
					print (err)
					error_encountered = True
					break

				# Check if this article is an ad
				if( ("www." + domain not in article_url) and ("http://" + domain not in article_url) and ("https://" + domain not in article_url) and (domain + ".com" not in article_url) and (domain + ".org" not in article_url) ):
					ad = True
					break

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
				pubDate = child.text.strip()

		if (ad == False and error_encountered == False):
			article_entry = { 'domain': domain, 'title': title, 'description': description, 'pubDate':pubDate, 'article_url': article_url, 'amp_url':'', 'summary':'' }
			print (article_entry)
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
	amp_dict_list = []
	for i in range (0, len(url_list), 50):
		while True:
			try:
				amp_dict = ampify_url_list(url_list[i:i+50])
			except Exception as e:
				print (e)
				# Wait some time before retrying
				time.sleep(5)
				print ("Waiting ...")
				continue
			break

		amp_dict_list.append(amp_dict)

	# Update all entries with their amp urls
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

	for small_list in big_list:
		for item in small_list:
			# Skip items with empty AMP urls
			if item['amp_url'] == '':
				continue
			
			# Send POST for getting summary for article
			data = { 'url':item['amp_url'], 'domain':item['domain'] }
			resp = requests.post(url='http://jist-html-parser-container/parse', json=data)

			print ('Response <' + str(resp.status_code) + '>')

			# Try to get summary
			try:
				summary = resp.json()['summary']
			except json.decoder.JSONDecodeError as jde_error: # URL was probably invalid or weird
				item['amp_url'] = '' # Mark the article as to be discarded and continue
				continue

			item['summary'] = summary

			print ('Article ' + item['title'] + ': ')
			print (summary)

if __name__ == "__main__":
	main()
