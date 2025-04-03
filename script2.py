import re
from datetime import datetime
import requests

import json
from base64 import b64decode
import time
import re
import urllib.parse
from bs4 import BeautifulSoup as BS
import cloudscraper

from threading import Thread
import queue
import os
from apps.home.utils import check_blacklisted, is_blacklisted
from uuid import uuid4
from zenrows import ZenRowsClient

ZENROW_API_KEY = "88ea2ce3aa3fe48ab806519f26c7bf16948ddceb"
ZENROW_API_URL = "https://api.zenrows.com/v1/"


#ZYTE Smart Proxy : https://app.zyte.com
proxies={
        "http": "http://cef7b4ee6daa4bc4810c42be269431fe:@proxy.crawlera.com:8011/",
        "https": "http://cef7b4ee6daa4bc4810c42be269431fe:@proxy.crawlera.com:8011/",
    }
verify='zyte-proxy-ca.crt'
zyte_api_url = "https://api.zyte.com/v1/extract"
API_KEY = "be8e0737c3664421a37adc8e0a48d9cf" #Enter_your_api_key


# 2captcha API create task
CAPTCHA_API_KEY = "f7aef1d64e1753855de59d05bd975b37"

proxies = {
    "http": "http://brd-customer-hl_b2c07d89-zone-residential_proxy1:r1z5ijna9b30@brd.superproxy.io:33335/",
    "https": "http://brd-customer-hl_b2c07d89-zone-residential_proxy1:r1z5ijna9b30@brd.superproxy.io:33335/",
}

def pass_data(item):
    WEB_HOST_IP = os.getenv("WEB_HOST_IP")
    response = requests.post(f'{WEB_HOST_IP}/msg', json={'result': item})
    print("Processes", response.text)
    

def create_session():
    
    # session = cloudscraper.create_scraper(browser={
    #     'browser': 'chrome',
    #     'platform': 'windows'
    # })
    # session.headers = {
    #     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    # }
    
    session = requests.session()
    
    return session
    


def zyte_session(session, url):
    while True:    
        session_id = str(uuid4())
        response = session.get(url, verify=False, timeout=60)
        
        try:
            # if is_scraper_completed(id):
            #     return None
            
            if response.status_code == 200:
                return session_id
            else:
                print("Failed to get session", response.status_code)
                time.sleep(1)
                return None
            
        except Exception as e:
            print("Initial request Error", str(e))
            time.sleep(1)
            continue
        
        
def is_scraper_completed(id):
    WEB_HOST_IP = os.getenv("WEB_HOST_IP")
    response = requests.get(f'{WEB_HOST_IP}/check_state/' + str(id))
    if response.text == "completed":
        return True
    return False


# 2captcha API create task
def create_task(dd_json, url):
    task_url = "https://api.2captcha.com/createTask"
    site_key = dd_json['cid']
    hash = dd_json['hsh']
    cookie = dd_json['cookie']
    t = dd_json['t']
    s = dd_json['s']
    e = dd_json['e']
    # dm = dd_json['dm']
    url = urllib.parse.quote(url, safe='')
    site_key = urllib.parse.quote(site_key)
    cookie = urllib.parse.quote(cookie)
    # dm = urllib.parse.quote(dm)
    
    captchaUrl = f"https://geo.captcha-delivery.com/captcha/?initialCid={site_key}&hash={hash}&cid={cookie}&t={t}&referer={url}&s={s}&e={e}&dm=cd"
    # convert to url encoded
    
    data = {
    "clientKey": CAPTCHA_API_KEY,
    "task": {
            "type": "DataDomeSliderTask",
            "websiteURL": url,
            "captchaUrl": captchaUrl,
            "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "proxyType":"http",
            "proxyAddress":"brd.superproxy.io",
            "proxyPort": "33335",
            "proxyLogin":"brd-customer-hl_b2c07d89-zone-residential_proxy1",
            "proxyPassword":"r1z5ijna9b30"
        }
    }
    
    response = requests.post(task_url, json=data)
    
    return response.json()


def get_task_result(task_id):
    url = "https://api.2captcha.com/getTaskResult"
    data = {
        "clientKey": CAPTCHA_API_KEY,
        "taskId": task_id
    }
    
    response = requests.post(url, json=data)
    
    return response.json()
    
    
    

def yelp_scraper_run(url, user_id, id):
    # url = urllib.parse.unquote(url).replace("+", " ") # Needed when using pure request query string
    try:
        find_desc = url.split("find_desc=")[1].split("&")[0]
        find_loc = url.split("find_loc=")[1].split("&")[0]
    except Exception as e:
        print("Invalid URL")
        return
    
    print("Start scraping", url)
    
    start = 0
    page = 0
    # auth = (API_KEY, "")
    # page_url = f"https://www.yelp.com/search?find_desc={find_desc}&find_loc={find_loc}&start={start}"
    
    session = create_session()
        
    while True:
        search_data = []
        start = page * 10 # 10 business per page        
        print("Start", start)
        # if is_scraper_completed(id):
        #     return
        
        #ZYTE API 
        base_url = f"https://www.yelp.com/search?find_desc={find_desc}&find_loc={find_loc}&start={start}"
        params = {
            'url': base_url,
            'apikey': ZENROW_API_KEY,
            'js_render': 'true',
            'premium_proxy': 'true',
        }
        
        try:
            response = session.get(ZENROW_API_URL, params=params)
        except Exception as e:
            print("Failed to get data", str(e))
            break
        

        # "venue	city	phone	Venue Type	Website	email	email 2	Email (facebook)	Facebook Link"
        if response.status_code == 200:
            
            contents_text = '{"locale"' + response.text.split('<!--{"locale"')[1].split("--></script>")[0] 
            response_json = json.loads(contents_text)
            
            if "searchExceptionProps" in response_json['legacyProps']['searchAppProps']['searchPageProps']:
                break
            
            for business in response_json['legacyProps']['searchAppProps']['searchPageProps']['mainContentComponentsListProps']:
                if "bizId" in business:
                    bizId = business['bizId']
                    venue_name = business['searchResultBusiness']['name']

                    if is_blacklisted(venue_name):
                        continue

                    if "temp. closed" in venue_name.lower() or "closed" in venue_name.lower():
                        continue

                    venue_type = ", ".join([i['title'] for i in business['searchResultBusiness']['categories']])
                    phone = business['searchResultBusiness']['phone']
                    
                    if business['searchResultBusiness']['website']:
                        website = business['searchResultBusiness']['website']['href']
                        if "http" != website[:4]:
                            website = ""
                    else:
                        website = ""

                    latitude = ""
                    longitude = ""
                    try:
                        for location in response_json['searchPageProps']['rightRailProps']['searchMapProps']['mapState']['markers']:
                            if "resourceId" in location and bizId == location['resourceId']:
                                try:
                                    latitude = location['location']['latitude']
                                    longitude = location['location']['longitude']
                                except:
                                    pass

                                break
                    except:
                        pass
                        
                    businessUrl = "https://www.yelp.com" + business['searchResultBusiness']['businessUrl']
                    if "/biz" not in businessUrl:
                        businessUrl = "https://www.yelp.com/biz/" + business['searchResultBusiness']['alias']

                    photoList = business['scrollablePhotos']['photoList'][0] if len(business['scrollablePhotos']['photoList']) > 0 else {}
                    thumbnail_url = photoList.get('src') if photoList else ''

                    try:
                        addresses = get_addresses(session, businessUrl)
                    except Exception as e:
                        print("Failed to get address", str(e), businessUrl)
                        addresses = {}

                    full_address = ''
                    city = addresses.get('addressLocality', '')
                    state = addresses.get('addressRegion', '')
                    zip = addresses.get('postalCode', '')
                    country = addresses.get('addressCountry', '')
                    address = addresses.get('streetAddress', '')
                    
                    # if address, city and state, zip , country is empty then skip this record
                    full_address = f"{address}, {city}, {state}, {zip} {country}"
                    if full_address == ", , ,  ":
                        full_address = ""
                    
                    data = dict()
                    data['url'] = url,
                    data['venue'] = venue_name,
                    data['venuetype'] = venue_type,
                    data['website'] = website
                    data['Phone'] = phone
                    data['address'] = full_address
                    data['facebook'] = ""
                    data['instagram'] = ""
                    data['twitter'] = ""
                    data['Email1'] = ""
                    data['Email2'] = ""
                    data['Email3'] = ""
                    data['Email4'] = ""
                    data['FacebookEmail1'] = ""
                    data['FacebookEmail2'] = ""
                    data['url_id'] = id
                    data['user_id'] = user_id
                    data['bizId'] = bizId
                    data['city'] = city
                    data['state'] = state
                    data['zip'] = zip
                    data['country'] = country
                    data['latitude'] = latitude
                    data['longitude'] = longitude
                    data['thumnailurl'] = thumbnail_url
                    search_data.append(data)
                    
            if len(search_data) == 0:
                break
            
            # threads = []
            # for data in search_data:
            #     thread = Thread(target=thread_runner, daemon=True, args=(data, ))
            #     thread.start()
            #     threads.append(thread)
                
            # for th in threads:
            #     th.join()
            
        else:
            print(response.status_code, base_url)
            break
        
        page += 1


def get_datadom_solution(dd_json, url):
    response = create_task(dd_json, url)
            
    if response['errorId'] == 0:
        task_id = response['taskId']
        while True:
            result = get_task_result(task_id)
            
            if result['errorId'] == 0:
                if result['status'] == "ready":
                    return result
            else:
                time.sleep(5)
                continue
    else:
        print("Failed to create task", response)
        return {}
            
            
    

def get_addresses(session, url):
    
    while True:
        params = {
            'url': url,
            'apikey': ZENROW_API_KEY,
            'js_render': 'true',
            'premium_proxy': 'true',
        }
        try:
            response = session.get(ZENROW_API_URL, params=params)
        except Exception as e:
            print("Failed to Biz detail page", url, str(e))
            time.sleep(1)
            continue
        
        if response.status_code == 200:
            try:
                # text = b64decode(response.json()["browserHtml"]).decode("utf-8")
                # text = response.json()["browserHtml"]
                text = response.text
                
                # Regex patterns to capture the content of each field
                street_pattern = r'"streetAddress"\s*:\s*"([^"]+)"'
                locality_pattern = r'"addressLocality"\s*:\s*"([^"]+)"'
                region_pattern = r'"addressRegion"\s*:\s*"([^"]+)"'
                postal_pattern = r'"postalCode"\s*:\s*"([^"]+)"'
                country_pattern = r'"addressCountry"\s*:\s*"([^"]+)"'

                streetAddress = re.search(street_pattern, text)
                addressLocality = re.search(locality_pattern, text)
                addressRegion = re.search(region_pattern, text)
                postalCode = re.search(postal_pattern, text)
                addressCountry = re.search(country_pattern, text)

                return {
                    "streetAddress": streetAddress.group(1) if streetAddress else '',
                    "addressLocality": addressLocality.group(1) if addressLocality else '',
                    "addressRegion": addressRegion.group(1) if addressRegion else '',
                    "postalCode": postalCode.group(1) if postalCode else '',
                    "addressCountry": addressCountry.group(1) if addressCountry else ''
                }
            except Exception as e:
                print("Failed to parse address", url, str(e))
                return {}
        else:
            print("Failed to get response ", url, response.status_code, response.text)
            # return {}
            continue
    

def thread_runner(data):
    try:
        website = data['website']
        WEB_HOST_IP = os.getenv("WEB_HOST_IP")
        
        response = requests.get(f'{WEB_HOST_IP}/check_state/' + str(data['url_id']))

        if response.text == "completed":
            return
        
        if website:
            try:
                fb_link, emails, fb_emails = get_fb_info(website)
            except Exception as e:
                print("Failed to get fb info", str(e))
                fb_link = ""
                emails = []
                fb_emails = []
            
            if fb_link:
                data['facebook'] = fb_link
            if fb_emails:
                try:
                    data['FacebookEmail1'] = fb_emails[0]
                    data['FacebookEmail2'] = fb_emails[1]
                except:
                    pass
            if emails:
                try:
                    data['Email1'] = emails[0]
                    data['Email2'] = emails[1]
                    data['Email3'] = emails[2]
                    data['Email4'] = emails[3]
                except:
                    pass

            response = requests.get(f'{WEB_HOST_IP}/check_state/' + str(data['url_id']))
            if response.text == "completed":
                return
            
        pass_data(data)

    except Exception as e:
        print("Thread runner", str(e))
        return
    
    
def get_fb_info(url):
    
    scraper = cloudscraper.create_scraper(browser={
        'browser': 'chrome',
        'platform': 'windows'
    })
    
    FB_link = ""
    emails = []
    fb_emails = []
    
    try:
        if url == "http://www.whiskyagogo.com":
            url = "https://www.whiskyagogo.com/calendar/"
            response = scraper.get(url, timeout=30)
        
        elif url == "http://www.musictunnelktv.com/":
            response = scraper.get("https://www.musictunnelktv.com/home", timeout=10)
            
        elif url == "https://www.musictunnelktv.com":
            response = scraper.get("https://www.musictunnelktv.com/home", timeout=10)
        
        else:
            response = scraper.get(url, proxies=proxies, verify=verify, timeout=60)
            
    except Exception as e:
        print("Failed to get data", url, str(e))
        return FB_link, emails, fb_emails 
        
    #Fetch data
    if response.status_code == 200:
        html = response.text.replace(r"\u0040", "@")
        
        # with open("home.html", "w", encoding="utf-8") as f:
        #     f.write(html)
            
        emails = find_emails(html)
        
    else:
        print(url, response.status_code)
        return FB_link, emails, fb_emails 
        
    if url == "http://www.hotelcafe.com":
        FB_link = "https://www.facebook.com/thehotelcafe/"
        
    elif url == "http://www.mambocrazecabaret.com":
        FB_link = "https://www.facebook.com/mambocrazecabaret/"
        
    elif url == "http://barlisla.com":
        FB_link = "https://www.facebook.com/barlisla"
    
    elif url == "https://thesunrose.com":
        url = "https://thesunrose.com/?page_id=151"
        FB_link = ""
        emails = ["Booking@TheSunrose.cOm"]
        return FB_link, emails, fb_emails
    
    elif url == "https://novacancyla.com":
        emails = ['info@novacancyla.com', 'media@houstonhospitalityla.com', 'events@houstonhospitalityla.com']
        FB_link = "https://www.facebook.com/NoVacancyLA"
        return FB_link, emails, fb_emails
    
    else:
        soup = BS(response.content, "lxml")
        for link in soup.find_all("a"):
            if link.get('href') and "facebook.com/" in link['href']:
                if "profile.php" in link['href']:
                    FB_link = link['href']
                elif ".php" in link['href'] or "tr?id=" in link['href']:
                    continue
                elif not "http" in link['href']:
                    continue
                
                FB_link = link['href']
                break
            
        if FB_link == "" and "facebook.com/" in response.text:
            FB_link = "https://www.facebook.com/" + response.text.split("facebook.com/")[1].split('"')[0]
                
        if "/fbml" in FB_link or "tr?id" in FB_link:
            FB_link = ""
            
    if FB_link :
        # Some FB page can not access without login
        # TODO : Using ZYTE API instead of smart proxy
        fb_emails = get_fb_page_2(FB_link)
            
    if len(emails) == 0 and len(fb_emails) == 0:
        # Possible pages which might have emails
        possible_contact_pages = ['contact', 'contact-us', 'info', 'barmenu']
        base_url = url.split(":")[0] + "://" + urllib.parse.urlparse(url).netloc
        
        for contact in possible_contact_pages:
            if base_url[-1] == "/":
                contact_url = base_url + contact
            else:
                contact_url = base_url + "/" + contact
                
            try:
                response = scraper.get(contact_url, timeout=10)
            except Exception as e:
                print("Failed to get contact page", contact_url, str(e))
                continue
                
            if response.status_code == 200:
                html = response.text.replace(r"\u0040", "@")
                
                # with open("home.html", "w", encoding="utf-8") as f:
                #     f.write(html)
                emails = find_emails(html)
                
                if len(emails):
                    break
            # else:
                # print(contact_url, response.status_code)
            
    # print(url, FB_link, emails, fb_emails)
    return FB_link, emails, fb_emails
        
        
def find_emails(html):
    email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    emails = re.findall(email_regex, html)
    emails = list(set( [ email.lower() for email in emails] ))
    filtered_emails = [
        email  for email in emails if check_blacklisted(email)]
    return filtered_emails


def get_fb_page(url):
    try:
        response = requests.get(url, proxies=proxies, verify=verify, timeout=60)
    except Exception as e:
        print("Failed to get FB page", url, str(e))
        return ""
    
    if response.status_code == 200:
        html = response.text.replace(r"\u0040", "@")
        
        # with open("home.html", "w", encoding="utf-8") as f:
        #     f.write(html)
        
        emails = find_emails(html)
        return emails
    
    else:
        print(url, response.status_code)
        return ""

def get_fb_page_2(url):
    while True:
        api_response = requests.post(
            zyte_api_url,
            auth=(API_KEY, ""),
            json={
                "url": url,
                "browserHtml": True,
                },
            )

        if api_response.json()['statusCode'] == 200:
            browser_html: str = api_response.json()["browserHtml"]
            emails = find_emails(browser_html)
            return emails
    
        elif api_response.json()['statusCode'] in [429, 503]:
            print(f"Rate limited for {url}, continuing")
            time.sleep(3)
            continue
        
        else:
            print(f"Failed to get FB page for {url}, {api_response.json()['statusCode']}")
            return []


if __name__ == "__main__":
    yelp_scraper_run("https://www.yelp.com/search?find_desc=Bars&find_loc=Los+Angeles%2C+CA", 1, 1)

