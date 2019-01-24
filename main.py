
import json
import requests
import xml.etree.ElementTree as ET

def loadJson():
	with open('feeds.json') as f:
		data = json.load(f)

	return data["top_stories"]

def parseFeed(feed):
	print('--------------------------------%s---------------------------------' %(feed['domain']))

	curAttempts = 0
	maxAttempts = 20
	while True:
		try:
			resp = requests.get(feed['rss_url'])
			break
		except requests.exceptions.ConnectionError as err: # Connection refused --> abort
			print('############################ CONNECTION ERROR #############################') # The current link for foxnews appears to be down
			print(err)
			return
		except requests.exceptions.ContentDecodingError as err:
			if curAttempts > maxAttempts:
				print('############################ DECODING ERROR #############################') # huffingtonpost will sometimes throw this error
				print(err)
				return

			curAttempts += 1
			continue

	curAttempts = 0
	while True:
		try:
			tree = ET.fromstring(resp.text)
			break
		except ET.ParseError as err:
			if curAttempts > maxAttempts:
				print('############################ PARSING ERROR #############################') # huffingtonpost will sometimes throw this error
				print(err)
				return

			curAttempts += 1
			continue
	
	articles = []
	for item in tree.findall('./channel/item'):
		ad = False # We do not keep any items labeled as ads

		for child in item:
			if(child.tag == 'rss_url'):
				link = child.text
				if(feed['domain'] not in child.text):
					ad = True
					break

			if(child.tag == 'description'):
				description = child.text

			if(child.tag == 'title'):
				title = child.text

		if (ad == False):
			print(title)

def main():
	feeds = loadJson()

	for feed in feeds:
		parseFeed(feed)
	payload = {'url': 'https://amp-cnn-com.cdn.ampproject.org/c/s/amp.cnn.com/cnn/2019/01/23/politics/donald-trump-nancy-pelosi-government-shutdown-congress/index.html', 'domain': 'cnn'}
	requests.post(url = "http://jist-html-parser-container/parse", data = payload) 



if __name__ == "__main__":
	main()
