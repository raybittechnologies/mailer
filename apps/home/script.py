import re
from datetime import datetime
import requests

import json
from base64 import b64decode
import time
import re
import urllib.parse
from bs4 import BeautifulSoup as BS
from zenrows import ZenRowsClient
import cloudscraper

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from dotenv import load_dotenv

load_dotenv()
from apps.home.utils import check_blacklisted, is_blacklisted_venue, is_blackeslisted_venue_type, extract_city_state
from uuid import uuid4


#ZYTE Smart Proxy : https://app.zyte.com
proxies={
        "http": "http://cef7b4ee6daa4bc4810c42be269431fe:@proxy.crawlera.com:8011/",
        "https": "http://cef7b4ee6daa4bc4810c42be269431fe:@proxy.crawlera.com:8011/",
    }
verify='zyte-proxy-ca.crt'
zyte_api_url = "https://api.zyte.com/v1/extract"
API_KEY = "be8e0737c3664421a37adc8e0a48d9cf" #Enter_your_api_key


ZENROW_API_KEY = "88ea2ce3aa3fe48ab806519f26c7bf16948ddceb"
ZENROW_API_URL = "https://api.zenrows.com/v1/"


def pass_data(item):
    WEB_HOST_IP = os.getenv("WEB_HOST_IP")
    try:
        response = requests.post(f'{WEB_HOST_IP}/msg', json={'result': item}, timeout=30)
        print("Processes", response.text)
    except requests.exceptions.RequestException as e:
        print(f"Error sending data: {e}")
        # Retry once
        try:
            response = requests.post(f'{WEB_HOST_IP}/msg', json={'result': item}, timeout=30)
            print("Processes (retry)", response.text)
        except requests.exceptions.RequestException as retry_e:
            print(f"Retry failed: {retry_e}")


def zyte_session(url, id):
    auth = (API_KEY, "")
    while True:    
        session_id = str(uuid4())
        response = requests.post(zyte_api_url, auth=auth, json={
            "browserHtml": True,
            "url": url,
            "session": {
                    "id": session_id
                }
            })
        
        try:
            if is_scraper_completed(id):
                return None
            data = response.json()
            # print("initial request ------" +  str(data["statusCode"])) 
            
            if "statusCode" in data:
                if data["statusCode"] == 200:
                    return session_id
                
                else:
                    print("Failed to get initial request", data)
                    time.sleep(1)
                    continue
            else:
                print("Invalid response", data)
                if data["status"] in [429, 503]:
                    time.sleep(1)
                    continue
                
                elif data["status"] == 520:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        print("Retry after", retry_after, "seconds")
                        time.sleep(int(retry_after))
                        continue
                    else:
                        time.sleep(1)
                        print("Retry after not found")
                        continue
                else:
                    time.sleep(1)
                    return None
            
        except Exception as e:
            print("Initial request Error", str(e), data)
            time.sleep(1)
            continue
        
        
def is_scraper_completed(id):
    WEB_HOST_IP = os.getenv("WEB_HOST_IP")
    response = requests.get(f'{WEB_HOST_IP}/check_state/' + str(id))
    if response.text == "completed":
        return True
    return False

def create_session():
    # Create a session
    session = requests.session()
    return session


def get_geo_location(address):
    session = create_session()
    google_api_key = os.getenv("GOOGLE_GEOCODING_API_KEY")
    
    address = urllib.parse.quote_plus(address, safe='/:,')
    
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={google_api_key}"
    
    response = session.get(url)
    
    if response.json()['status'] == 'OK':
        return response.json()['results'][0]['geometry']['location']
    else:
        return None


def get_service_with_bizId(bizId, user_id):
    WEB_HOST_IP = os.getenv("WEB_HOST_IP")
    response = requests.get(f'{WEB_HOST_IP}/get_service_with_userid_bizid?user_id={user_id}&biz_id={bizId}')
    if response.status_code == 200:
        return response.json()
    else:
        return {}
    
    

def yelp_scraper_run(url, id, user_info):
    user_id = user_info.get('id')
    is_opt_musicians = user_info.get('is_opt_musicians') # 1: opt musicians, 0: no opt musicians
    is_allow_deduplicate = user_info.get('is_allow_deduplicate') # 1: allow duplicate, 0: no duplicate

    # url = urllib.parse.unquote(url).replace("+", " ") # Needed when using pure request query string
    try:
        find_desc = url.split("find_desc=")[1].split("&")[0]
        find_loc = url.split("find_loc=")[1].split("&")[0]
    except Exception as e:
        print("Invalid URL", url, str(e))
        return
    
    print("Start scraping", url)
    
    client = ZenRowsClient(ZENROW_API_KEY)
    
    start = 0
    page = 0
    
    while True:
        search_data = []
        start = page * 10 # 10 business per page        
        if is_scraper_completed(id):
            return
        
        print("Start", start)
        
        #ZYTE API 
        base_url = f"https://www.yelp.com/search?find_desc={find_desc}&find_loc={find_loc}&start={start}"
        params = {
            'js_render': 'true',
            'premium_proxy': 'true',
        }
        
        while True:
            try:
                response = client.get(base_url, params=params)
            except Exception as e:
                time.sleep(1)
                continue
            
            if response.status_code == 200:
                break
            else:
                time.sleep(1)
                continue
        
        # "venue	city	phone	Venue Type	Website	email	email 2	Email (facebook)	Facebook Link"
        if response.status_code == 200:

            try:
                contents_text = '{"locale"' + response.text.split('<!--{"locale"')[1].split("--></script>")[0] 
                response_json = json.loads(contents_text)
            except Exception as e:
                print("Failed to parse response", str(e))
                break
            
            if "searchPageProps" not in response_json['legacyProps']['searchAppProps']:
                break
            
            try:
                if "searchExceptionProps" in response_json['legacyProps']['searchAppProps']['searchPageProps']:
                    break
            except Exception as e:
                # write reponse to json  file for debugging
                # with open("response.json", "w", encoding="utf-8") as f:
                #     json.dump(response_json, f, indent=4)
                # page += 1
                continue
            
            businesses = [
                b for b in response_json["legacyProps"]["searchAppProps"]["searchPageProps"]["mainContentComponentsListProps"]
                if "bizId" in b
            ]
            if not businesses:
                break

            # Parallelize slow per-business work: get_service_with_bizId, get_addresses, get_geo_location
            search_data = []
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(
                        build_one_business_data,
                        business,
                        client,
                        url,
                        id,
                        user_id,
                        is_opt_musicians,
                        is_allow_deduplicate,
                    ): business
                    for business in businesses
                }
                for future in as_completed(futures):
                    if is_scraper_completed(id):
                        break
                    try:
                        data = future.result()
                        if data:
                            print("<Venue>", data["venue"], "<Address>", data["address"])
                            search_data.append(data)
                    except Exception as e:
                        print("build_one_business_data error", str(e))

            if not search_data:
                break

            # Bounded concurrency for thread_runner (get_fb_info + pass_data)
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                list(executor.map(thread_runner, search_data))
            
        else:
            print("Status Code: ", response.status_code, base_url)
            break
        
        page += 1

# Max concurrent workers for I/O (API calls, scraping). Prevents overwhelming APIs and connection limits.
MAX_WORKERS = 8


def build_one_business_data(business, client, url, id, user_id, is_opt_musicians, is_allow_deduplicate):
    """Build data dict for one business. Runs in thread pool to parallelize get_addresses/get_service_with_bizId."""
    if "bizId" not in business:
        return None
    bizId = business["bizId"]
    
    businessUrl = "https://www.yelp.com" + business["businessUrl"]

    photoList = business["scrollablePhotos"]["photoList"][0] if len(business["scrollablePhotos"]["photoList"]) > 0 else {}
    thumbnail_url = photoList.get("src") if photoList else ""

    service_data = get_service_with_bizId(bizId, user_id)
    if is_allow_deduplicate and service_data.get("is_exist"):
        return None
    service = service_data.get("service", {})

    full_address = service.get("address", "") or ""
    city = service.get("city") or ""
    state = service.get("state") or ""
    zip = service.get("zip") or ""
    country = service.get("country") or ""
    latitude = service.get("latitude") or ""
    longitude = service.get("longitude") or ""

    try:
        addresses = get_addresses(client, businessUrl)
    except Exception as e:
        print("Failed to get address", str(e), businessUrl)
        addresses = {}

    try:
        venue_name = addresses.get("venue_name", "")
    except Exception as e:
        print("Failed to get venue name", str(e))
        return None

    venue_types = addresses.get("venue_types", [])
    phone = addresses.get("phone", "")

    if is_opt_musicians:
        if is_blacklisted_venue(venue_name):
            return None
        if is_blackeslisted_venue_type(venue_types):
            return None
        if phone and (phone.startswith("-") or len(phone) < 10):
            return None

    if "temp. closed" in venue_name.lower() or "closed" in venue_name.lower():
        return None

    venue_type = ", ".join(venue_types)

    address = addresses.get("streetAddress", "")
    city = addresses.get("addressLocality", "") or city
    state = addresses.get("addressRegion", "") or state
    zip = addresses.get("postalCode", "") or zip
    country = addresses.get("addressCountry", "") or country
    website = addresses.get("homepage", "")
    full_address = f"{address}, {city}, {state}, {zip} {country}".strip(" ,") or ""

    if full_address and not latitude and not longitude:
        location = get_geo_location(full_address)
        if location:
            latitude = location["lat"]
            longitude = location["lng"]
    if full_address and (not city or not state):
        city, state = extract_city_state(full_address)

    data = {
        "url": url,
        "venue": venue_name,
        "venuetype": venue_type,
        "website": website,
        "Phone": phone,
        "address": full_address,
        "facebook": service.get("facebook", ""),
        "instagram": service.get("instagram", ""),
        "twitter": service.get("twitter", ""),
        "Email1": service.get("email1", "") if check_blacklisted(service.get("email1", "")) else "",
        "Email2": service.get("email2", "") if check_blacklisted(service.get("email2", "")) else "",
        "Email3": service.get("email3", "") if check_blacklisted(service.get("email3", "")) else "",
        "Email4": service.get("email4", "") if check_blacklisted(service.get("email4", "")) else "",
        "FacebookEmail1": service.get("fbemail1", "") if check_blacklisted(service.get("fbemail1", "")) else "",
        "FacebookEmail2": service.get("fbemail2", "") if check_blacklisted(service.get("fbemail2", "")) else "",
        "url_id": id,
        "user_id": user_id,
        "bizId": bizId,
        "city": city,
        "state": state,
        "zip": zip,
        "country": country,
        "latitude": latitude,
        "longitude": longitude,
        "thumnailurl": thumbnail_url,
    }
    return data


def get_addresses(client, url):
    
    while True:
        params = {
            'js_render': 'true',
            'premium_proxy': 'true',
        }
        try:
            response = client.get(url, params=params)
        except Exception as e:
            print("Failed to Biz detail page", url, str(e))
            time.sleep(1)
            continue
        
        if response.status_code == 200:
            try:
                # text = b64decode(response.json()["browserHtml"]).decode("utf-8")
                # text = response.json()["browserHtml"]
                text = response.text
                soup = BS(text, 'html.parser')

                venue_name = soup.find('h1').text
                venue_types = [i.find('a').text for i in soup.find_all('span', attrs={'data-testid': "BizHeaderCategory"})]

                try:
                    phone = soup.find('span', attrs={'alt': 'Business phone number'}).find_parent('div').find_next_sibling('div').text.replace('Phone number', '').strip()
                except:
                    phone = None

                try:
                    website = soup.find('span', attrs={'alt': 'Business website'}).find_parent('a').get('href')
                    homepage = urllib.parse.parse_qs(urllib.parse.urlparse(website).query)['url'][0]
                except:
                    homepage = None
                
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
                    "addressCountry": addressCountry.group(1) if addressCountry else '',
                    "homepage": homepage if homepage else '',
                    "venue_name": venue_name,
                    "venue_types": venue_types,
                    "phone": phone,
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
            # if any emails is in data then skip this process
            if data.get('Email1') or data.get('Email2') or data.get('Email3') or data.get('Email4') or data.get('FacebookEmail1') or data.get('FacebookEmail2'):
                pass
            else:
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
            
        # if venuetype is empty and no email then ignore this record
        if data['venuetype'] == "" and data['Email1'] == "" and data['Email2'] == "" and data['Email3'] == "" and data['Email4'] == "" and data['FacebookEmail1'] == "" and data['FacebookEmail2'] == "":
            return
            
        pass_data(data)

    except Exception as e:
        print("Thread runner", str(e))
        return
    
    
def get_fb_info(url):
    
    scraper = create_session()
    params = {
        'url': url,
        'apikey': ZENROW_API_KEY
    }
    
    FB_link = ""
    emails = []
    fb_emails = []
    
    try:
        response = scraper.get(ZENROW_API_URL, params=params)
            
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
        possible_contact_pages = ['contact', 'contact-us', 'info', 'barmenu', 'about']
        base_url = url.split(":")[0] + "://" + urllib.parse.urlparse(url).netloc
        
        for contact in possible_contact_pages:
            if base_url[-1] == "/":
                contact_url = base_url + contact
            else:
                contact_url = base_url + "/" + contact
                
            params = {
                'url': contact_url,
                'apikey': ZENROW_API_KEY,
            }
                
            try:
                response = scraper.get(ZENROW_API_URL, params=params)
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
            html = browser_html.replace(r"\u0040", "@")
            emails = find_emails(html)
            return emails
    
        elif api_response.json()['statusCode'] in [429, 503]:
            print(f"Rate limited for {url}, continuing")
            time.sleep(3)
            continue
        
        else:
            print(f"Failed to get FB page for {url}, {api_response.json()['statusCode']}")
            return []


if __name__ == "__main__":
    # yelp_scraper_run("https://www.yelp.com/search?find_desc=Bars&find_loc=Los+Angeles%2C+CA", 1, 1)
    fb_url = 'https://www.facebook.com/barleyandboar'
    print(get_fb_page(fb_url))

