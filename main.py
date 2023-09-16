import requests
import pandas as pd
import re
import urllib.parse
from bs4 import BeautifulSoup as BS

import time

import cloudscraper

proxies={
        "http": "http://cef7b4ee6daa4bc4810c42be269431fe:@proxy.crawlera.com:8011/",
        "https": "http://cef7b4ee6daa4bc4810c42be269431fe:@proxy.crawlera.com:8011/",
    }

verify='zyte-proxy-ca.crt'

def main():

    url = "https://www.yelp.com/search?find_desc=live+music&find_loc=Oklahoma+City%2C+OK%2C+United+States"
    url = urllib.parse.unquote(url).replace("+", " ")
    
    find_desc = url.split("find_desc=")[1].split("&")[0]
    find_loc = url.split("find_loc=")[1].split("&")[0]
    
    base_url = "https://www.yelp.com/search/snippet"
    
    session = requests.session()
    headers = {
        "User-Agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
    }

    session.headers = headers
    
    start = 0
    page = 0
    
    search_data = []
    
    while True:
        
        start = page * 10
        params = {
            "find_desc" : find_desc,
            "find_loc" : find_loc,
            "start" : start,
            "parent_request_id" : "df4e47308c3b7a1b",
            "request_origin" : "user"
        }
        print("page", page)
        try:
            response = session.get(base_url, params=params, timeout=10, proxies=proxies, verify=verify)
        except Exception as e:
            print(repr(e))
            continue
        # "venue	city	phone	Venue Type	Website	email	email 2	Email (facebook)	Facebook Link"
        
        if response.status_code == 200:
            
            if "searchExceptionProps" in response.json()['searchPageProps']:
                break
            
            for business in response.json()['searchPageProps']['mainContentComponentsListProps']:
                
                if "bizId" in business:
                    
                    bizId = business['bizId']
                    venue_name = business['searchResultBusiness']['name']
                    venue_type = ", ".join(i['title'] for i in business['searchResultBusiness']['categories'])
                    phone = business['searchResultBusiness']['phone']
                    if business['searchResultBusiness']['website']:
                        website = business['searchResultBusiness']['website']['href']
                    else:
                        website = ""
                        
                    address = ""
                    for location in response.json()['searchPageProps']['rightRailProps']['searchMapProps']['hovercardData'].values():
                        
                        if bizId == location['bizId']:
                            address = " ".join(location['addressLines'])
                            
                    data = dict()
                    data['Venue'] = venue_name
                    data['Phone'] = phone
                    data['VenueType'] = venue_type
                    data['Website'] = website
                    data['Address'] = address
                    data['Email'] = ""
                    data['FacebookLink'] = ""
                    data['FacebookEmail'] = ""
                    
                    if website:
                        fb_link, emails, fb_emails = get_fb_info(website)
                        if fb_link:
                            data['FacebookLink'] = fb_link
                        if fb_emails:
                            data['FacebookEmail'] = ",".join(fb_emails)
                        if emails:
                            data['Email'] = ",".join(emails)
                            
                    search_data.append(data)
                    
        elif response.status_code in [429, 503]:
            print("Rate limited")
            time.sleep(1)
            continue
        
        else:
            print(response.status_code)
            break
        
        page += 1
    
    df = pd.DataFrame(search_data)
    df.to_csv(f"{find_loc}.csv", index=None)
    
    print("finished")
    
    
def get_fb_info(url):
    
    scraper = cloudscraper.create_scraper(browser={
        'browser': 'chrome',
        'platform': 'windows'
    })
    
    FB_link = ""
    emails = []
    fb_emails = []
    
    # if url != "http://www.losthighwaybar.com":
    #     return FB_link, emails, fb_emails
    
    if url == "http://www.whiskyagogo.com":
        url = "https://www.whiskyagogo.com/calendar/"
        response = scraper.get(url)
    
    elif url == "http://www.musictunnelktv.com/":
        response = scraper.get("https://www.musictunnelktv.com/home")
        
    elif url == "https://www.musictunnelktv.com":
        response = scraper.get("https://www.musictunnelktv.com/home")
    
    else:
        response = scraper.get(url, proxies=proxies, verify=verify)
        
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
        # Some FB page can access without login
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
        # Possible page which might have emails
        possible_contact_pages = ['contact', 'contact-us', 'info', 'barmenu']
        base_url = url.split(":")[0] + "://" + urllib.parse.urlparse(url).netloc
        
        for contact in possible_contact_pages:
            if base_url[-1] == "/":
                contact_url = base_url + contact
            else:
                contact_url = base_url + "/" + contact
                
            try:
                response = scraper.get(contact_url,  proxies=proxies, verify=verify)
            except Exception as e:
                print(contact_url, repr(e))
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
            
    print(url, FB_link, emails, fb_emails)
    return FB_link, emails, fb_emails
        
        
def find_emails(html):
    email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    emails = re.findall(email_regex, html)
    emails = list(set( [ email.lower() for email in emails] ))
    filtered_emails = [
        email  for email in emails if not email[-4:] in ['.jpg', '.png'] and not "@sentry" in email]
    return filtered_emails
    

if __name__ == "__main__":
    main()