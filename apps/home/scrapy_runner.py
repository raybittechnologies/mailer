# scrapy_runner.py

import os
from scrapy.crawler import CrawlerProcess
from script import homes  # Import your Scrapy spider class

def run_scrapy(urls, username, user_id):
    if len(urls)>0:
        process = CrawlerProcess({
            'USER_AGENT': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)'
        })

        process.crawl(homes, urls=urls, username=username, user_id=user_id)
        process.start()
        print("process has started")


run_scrapy(['https://www.yelp.com/search?find_desc=Toilet+Leak&find_loc=Upper+Canada+Village%2C+Ontario%2C+Canada'], 'username', 'user_id')