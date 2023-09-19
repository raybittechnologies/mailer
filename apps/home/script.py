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

import os
#ZYTE Smart Proxy : https://app.zyte.com
proxies={
        "http": "http://cef7b4ee6daa4bc4810c42be269431fe:@proxy.crawlera.com:8011/",
        "https": "http://cef7b4ee6daa4bc4810c42be269431fe:@proxy.crawlera.com:8011/",
    }
verify='zyte-proxy-ca.crt'


now = datetime.now()
current_time = now.strftime("%H:%M:%S")
done_links = list()


def pass_data(item):
    WEB_HOST_IP = os.getenv("WEB_HOST_IP")
    print("pass_data", WEB_HOST_IP)
    response = requests.post(f'http://{WEB_HOST_IP}/msg', json={'result': item})
    # response = requests.post('http://146.190.51.19/msg', json={'result': item})
    print(response.text)
    


def yelp_scraper_run(url, user_name, user_id, id):
    WEB_HOST_IP = os.getenv("WEB_HOST_IP")
    print("yelp_scraper_run", WEB_HOST_IP)
    # url = urllib.parse.unquote(url).replace("+", " ") # Needed when using pure request query string
    find_desc = url.split("find_desc=")[1].split("&")[0]
    find_loc = url.split("find_loc=")[1].split("&")[0]
    print("Start scraping", url)
    
    session = requests.session()
    headers = {
        "User-Agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
    }
    session.headers = headers
    zyte_api_url = "https://api.zyte.com/v1/extract"
    
    start = 0
    page = 0
    
    while True:
        search_data = []
        start = page * 10 # 10 business per page
        
        response = requests.post(f'http://{WEB_HOST_IP}/check_state', json={'id': id})
        if response.text == "completed":
            return
        
        #ZYTE API 
        base_url = f"https://www.yelp.com/search/snippet?find_desc={find_desc}&find_loc={find_loc}&start={start}&parent_request_id=cff2259236faa40b&request_origin=user"
        payload = {
            "url" : base_url,
            "httpResponseBody" : True
        }
        
        try:
            response = session.post(zyte_api_url, auth=("be8e0737c3664421a37adc8e0a48d9cf", ""), json=payload, timeout=10)
        except Exception as e:
            print(str(e))
            continue
        
        # "venue	city	phone	Venue Type	Website	email	email 2	Email (facebook)	Facebook Link"
        if response.json()['statusCode'] == 200:
            response_json = json.loads(b64decode(response.json()["httpResponseBody"]))
            
            if "searchExceptionProps" in response_json['searchPageProps']:
                break
            
            for business in response_json['searchPageProps']['mainContentComponentsListProps']:
                if "bizId" in business:
                    bizId = business['bizId']
                    venue_name = business['searchResultBusiness']['name']
                    venue_type = ", ".join([i['title'] for i in business['searchResultBusiness']['categories']])
                    phone = business['searchResultBusiness']['phone']
                    
                    if business['searchResultBusiness']['website']:
                        website = business['searchResultBusiness']['website']['href']
                    else:
                        website = ""
                        
                    address = ""
                    for location in response_json['searchPageProps']['rightRailProps']['searchMapProps']['hovercardData'].values():
                        if bizId == location['bizId']:
                            address = " ".join(location['addressLines'])
                    
                    data = dict()
                    data['url'] = url,
                    data['venue'] = venue_name,
                    data['venuetype'] = venue_type,
                    data['website'] = website
                    data['Phone'] = phone
                    data['address'] = address
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
                    
                    search_data.append(data)
                    
            threads = []
            for data in search_data:
                thread = Thread(target=thread_runner, daemon=True, args=(data, ))
                thread.start()
                threads.append(thread)
                
            for th in threads:
                th.join()
            
        elif response.status_code in [429, 503]:
            print("Rate limited")
            time.sleep(1)
            continue
        
        else:
            print(response.status_code)
            break
        
        page += 1
    

def thread_runner(data):
    website = data['website']
    
    if website:
        fb_link, emails, fb_emails = get_fb_info(website)
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
        
    pass_data(data)
    
    
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
            response = scraper.get(url, timeout=10)
        
        elif url == "http://www.musictunnelktv.com/":
            response = scraper.get("https://www.musictunnelktv.com/home", timeout=10)
            
        elif url == "https://www.musictunnelktv.com":
            response = scraper.get("https://www.musictunnelktv.com/home", timeout=10)
        
        else:
            response = scraper.get(url, proxies=proxies, verify=verify, timeout=30)
            
    except Exception as e:
        print(url , str(e))
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
        while True:
            response = scraper.get(FB_link, proxies=proxies, verify=verify)
            
            if response.status_code == 200:
                html = response.text.replace(r"\u0040", "@")
                fb_emails = find_emails(html)
                
                # with open("fb.html", "w", encoding="utf-8") as f:
                #     f.write(html)
                break
            
            elif response.status_code == 503 or response.status_code == 429:
                print(FB_link, response.status_code)
                continue
            
            else:
                print(FB_link, response.status_code)
                break
            
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
                print(contact_url, str(e))
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
        email  for email in emails if not email[-4:] in ['.jpg', '.png'] and not "@sentry" in email]
    return filtered_emails
    
