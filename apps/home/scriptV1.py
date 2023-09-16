import scrapy
import re
from datetime import datetime
import requests
import asyncio

now = datetime.now()
current_time = now.strftime("%H:%M:%S")
done_links = list()


def pass_data(item):
    print(item)
    response = requests.post('http://172.31.15.146:8081/msg', json={'result': item})
    print(response)
    return ""


def find_emails(html):
    email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    emails = re.findall(email_regex, html)
    # filtered_emails = [
    #     email for email in emails if not re.search(r'@\d', email)]
    # return filtered_emails
    filtered_emails = []
    for email in emails:
        if not re.search(r'@\d', email) and len(email.split('@')[0]) <= 25:
            filtered_emails.append(email)

    return filtered_emails


class homes(scrapy.Spider):
    name = 'homes'
    custom_settings = {
        'DOWNLOADER_MIDDLEWARES': {'scrapy_zyte_smartproxy.ZyteSmartProxyMiddleware': 610},
        "ZYTE_SMARTPROXY_ENABLED": True,
        "ZYTE_SMARTPROXY_APIKEY": 'cef7b4ee6daa4bc4810c42be269431fe',
        "AUTOTHROTTLE_ENABLED": False,
        "CONCURRENT_REQUESTS": 16,
        "DOWNLOAD_TIMEOUT": 600,
        'RETRY_TIMES': 5,

    }

    def __init__(self, urls=None, username=None, user_id=None, url_id=None, *args, **kwargs):
        super(homes, self).__init__(*args, **kwargs)
        print(urls)
        self.urls = urls
        self.user_id = user_id
        self.username = username
        self.url_id = url_id
        try:
            filename = "scrapyd_data0.txt"
            with open(filename, 'w') as file:
                pass
            file.close()
        except:
            pass

    def start_requests(self):
        for loop in self.urls:
            alerts = ['ALERT-FOR-URL \n' + loop]
            try:
                print('-----------------------------------------------------------')
                print(alerts)
                print('-----------------------------------------------------------')
                # Tel_alert(alerts)
            except:
                print('-----------------------------------------------------------')
                print("ALERT SENDING EXCEPTION in YELP SCRAPER   ", current_time)
                print('-----------------------------------------------------------')
                pass
            yield scrapy.Request(url=loop, meta={'response_url': loop})

    async def closed(self):
        print('start close method called.................................................')
        async def send_data():
            print("Process has stopped))))))))))))))))))))))))))))))))))))))))))))00000000000")
        asyncio.run(send_data())

    def parse(self, response, **kwargs):
        try:
            with open('url_status.txt', 'a') as file:
                file.write(f"URL: {response.url}, Status Code: {response.status}\n")
            file.close()
        except:
            pass

        total_pages = int(
            response.css('div[aria-label="Pagination navigation"] div span.css-chan6m ::text').get().split('of')[-1])
        if total_pages == 1:
            print('Total_Products = ', len([v for v in response.css('h3.css-1agk4wl a ::attr(href)').extract() if
                                            'ad_business_id=' not in v]))
        else:
            a = 1
            print('Approx Products = 10 - ', total_pages * 10)

        for loop in response.css('h3.css-1agk4wl a ::attr(href)').extract():
            if 'ad_business_id=' not in loop:
                if 'https://www.yelp.com' + loop not in done_links:
                    yield scrapy.Request(url='https://www.yelp.com' + loop, callback=self.next_parse,
                                         meta={'response_url': response.meta['response_url']})
        if response.css('a[aria-label="Next"] ::attr(href)').get() != None:
            yield scrapy.Request(url=response.css('a[aria-label="Next"] ::attr(href)').get(), callback=self.parse,
                                 meta={'response_url': response.meta['response_url']})

    async def next_parse(self, response):
        async def send_mess():
            try:
                with open('url_status.txt', 'a') as file:
                    file.write(f"URL: {response.url}, Status Code: {response.status}\n")
                file.close()
            except:
                pass
            item = dict()
            item['Url'] = response.url
            try:
                item['Venue'] = response.css('h1.css-1se8maq ::text').get()
            except:
                item['Venue'] = ''

            try:
                item['Type'] = ','.join(response.css(
                    'span.display--inline__09f24__c6N_k.margin-r1-5__09f24__ot4bd.border-color--default__09f24__NPAKY span.css-1fdy0l5 a ::text').extract())
            except:
                item['Type'] = ''

            for index, parsing in enumerate(response.css('p')):
                if parsing.css(' ::text').get() == 'Phone number':
                    try:
                        item['Phone'] = response.css(
                            'p')[index + 1].css(' ::text').get()
                    except:
                        item['Phone'] = ''
                if parsing.css(' ::text').get() == 'Business website':
                    try:
                        item['website'] = 'https://www.' + response.css('p')[index + 1].css('a ::text').get(
                        ).replace('https://www.', '').replace('https://', "").replace('www.', "")
                    except:
                        item['website'] = ''
            if 'Phone' not in list(item.keys()):
                item['Phone'] = ''

            if 'website' not in list(item.keys()):
                item['website'] = ''

            try:
                item['address'] = ' '.join(response.css(
                    'div.arrange-unit__09f24__rqHTg.arrange-unit-fill__09f24__CUubG.border-color--default__09f24__NPAKY address ::text').extract())
            except:
                item['address'] = ""
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "max-age=0",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
            }

            if item['website'] != "":
                try:
                    resp = requests.get(
                        url=item['website'], headers=headers)
                    match = find_emails(resp.text)[0]
                    find_facebook = scrapy.Selector(text=resp.text)
                    facebooks_links = [v for v in find_facebook.css(
                        'a ::attr(href)').extract() if 'facebook.com' in v]
                    instagram_links = [v for v in find_facebook.css(
                        'a ::attr(href)').extract() if 'instagram.com' in v]
                    twitter_links = [v for v in find_facebook.css(
                        'a ::attr(href)').extract() if 'twitter.com' in v]
                    try:
                        item['facebook'] = facebooks_links[0]
                    except:
                        item['facebook'] = ""
                    try:
                        item['instagram'] = instagram_links[0]
                    except:
                        item['instagram'] = ""
                    try:
                        item['twitter'] = twitter_links[0]
                    except:
                        item['twitter'] = ""

                    item['email'] = match
                    if item['email'][-4:] in ['.jpg', '.png']:
                        item['email'] = ""
                except:
                    item['email'] = ""

                try:
                    if item['email'] == None or item['email'] == "":
                        scrapy_resp = scrapy.Selector(text=resp.text)
                        for all_chore in scrapy_resp.css('a'):
                            if all_chore.css(' ::text').get() != None:
                                if 'contact us' in all_chore.css(' ::text').get().lower():
                                    find_achore = all_chore.css(
                                        ' ::attr(href)').get()
                                    break
                                if 'contact-us' in all_chore.css(' ::text').get().lower():
                                    find_achore = all_chore.css(
                                        ' ::attr(href)').get()
                                    break

                                if 'contactus' in all_chore.css(' ::text').get().lower():
                                    find_achore = all_chore.css(
                                        ' ::attr(href)').get()
                                    break
                                if 'contact' in all_chore.css(' ::text').get().lower():
                                    find_achore = all_chore.css(
                                        ' ::attr(href)').get()
                                    break
                        try:
                            resp = requests.get(
                                url= find_achore, headers=headers)
                        except:
                            try:
                                find_achore = item['website'] + \
                                              find_achore.replace('\\', "")
                                resp = requests.get(
                                    url=find_achore, headers=headers)
                            except:
                                a = 1
                                pass

                        try:
                            match = find_emails(resp.text)[0]
                            item['email'] = match
                            if item['email'][-4:] in ['.jpg', '.png']:
                                item['email'] = ""
                        except:
                            item['email'] = ""
                    try:
                        if 'core-js-bundle@' in item['email']:
                            item['email'] = ""
                    except:
                        item['email'] = ""
                except:
                    item['email'] = ""
                if '@1.3.1' in item['email']:
                    item['email'] = ""

            for loopa in ['email', 'facebook', 'instagram', 'twitter']:
                if loopa not in list(item.keys()):
                    item[loopa] = ''
            item['url_id'] = self.url_id
            item['user_id'] = self.user_id
            try:
                filename= "scrapyd_data0.txt"
                with open(filename, 'a') as file:
                    file.write(str(item) + '\n')
                file.close()
            except:
                pass
            pass_data(item)

        asyncio.get_event_loop().run_until_complete(send_mess())


