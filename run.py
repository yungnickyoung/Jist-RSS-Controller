
import json
import requests
import xml.etree.ElementTree as ET

def loadJson():
	with open('feeds.json') as f:
		data = json.load(f)

	return data["feeds"]

def parseFeed(feed):
	resp = requests.get(feed['link'])

	tree = ET.fromstring(resp.text)
	
	articles = []
	for item in tree.findall('./channel/item'):
		ad = False
		for child in item:
			if(child.tag == 'link'):
				link = child.text
				if(feed['domain'] not in child.text):
					ad = True

			if(child.tag == 'description'):
				description = child.text

			if(child.tag == 'title'):
				title = child.text

		print(title)
		print('\n')

def main():
	feeds = loadJson()

	for feed in feeds:
		parseFeed(feed)


if __name__ == "__main__":
	main()
