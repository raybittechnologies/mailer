from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_openai import ChatOpenAI
import pyap
from pywebpush import webpush, WebPushException
import json
from dotenv import load_dotenv
load_dotenv()
# from langchain_community.callbacks import get_openai_callback

# from typing import List, Optional

# from kor.extraction import create_extraction_chain
# from langchain_community.document_loaders import TextLoader

# from pydantic import BaseModel, Field
# from kor import extract_from_documents, from_pydantic, create_extraction_chain

# from langchain.text_splitter import RecursiveCharacterTextSplitter

import os
openai_api_key=os.getenv("OPENAI_API_KEY")
# print(openai_api_key)
# eben@eyebytes.com & also reject Name Eben along w/ it in the firstname field 
# amkryukov@gmail.com & also reject Name amkryukov or amy along w it in the firstname field 
# eyebytes.com
# @yourwebsite.com
# Any emails with u00 in it (u003efmbboxoffice@livenation.com , for example..sometime they will be u002, u001, etc..)
# your@
# @email.com
# @uber.com
# @lyft.com
# @doordash.com
# @yelp.com
# @grubhub.com
# yourname@
# @yourname.com
# @youraddress.com 
# youraddress@
# you@
# @whatever.com
# username@
# noreply@
# firstlast@
# @pixelspread.com
# Emails with more than 1 period after the @ sign (ex.materialdesigniconsfont@4.5.95.min.css)
# Emails ending in .webp (not even necessarily directly after the @ sign too!)


email_blacklist = [
                '@email.com', 
                '@example.com',
                '@domain.com',
                '@godaddy.com',
                '@address.com',
                '@filler.com',
                '@xyz.com',
                '@newsletter.com',
                '@mystore.com', 
                'example@gmail.com', 
                '@sentry', 
                'mail@mail.com', 
                '@mail.com', 
                'example@mail.com', 
                '.png', 
                '.jpg', 
                'sentry.io', 
                '@mysite.com', 
                'example@', 
                'sample@', 
                'donotreply@', 
                '@company.com', 
                '@yourdomain.com', 
                'accessibility@wyndham.com',
                'email@',
                '@latofonts.com',
                '@fontawesome.com',
                '.gif',
                'eben@',
                'amkryukov@',
                'eyebytes.com',
                '@yourwebsite.com',
                'your@',
                '@uber.com',
                '@lyft.com',
                '@doordash.com',
                '@yelp.com',
                '@grubhub.com',
                'yourname@',
                '@yourname.com',
                '@youraddress.com',
                'youraddress@',
                'you@',
                '@whatever.com',
                'username@',
                'noreply@',
                'firstlast@',
                '@pixelspread.com',
                '.webp',
                '.css',
                'name@',
                '@youremail.com',
                'name@',
                '@youremail.com',
                'eben@eyebytes.com',
                'eyebytes.com',
                'amkryukov@gmail.com'
             ]

black_list_venue_types = "Lighting Fixtures & Equipment, DJs, Adult Education, Performing Arts, Comedy Clubs, Airlines, Airport Shuttles, Party Bus Rentals, Airport Terminals, Limos, Town Car Service, Airports, Car Rental, Music & DVDs, Music Production Services, Museums, Dance, Classes, Teacher, Musician, Band, Hookah Bars, Musical Instruments & Teachers, Recording & Rehearsal Studios, Observatories, Historical Tours, Opera & Ballet, Outdoor Movies, Paint & Sip, Art Classes, Party & Event Planning, Venues & Event Spaces, Parking, Psychics, Feng Shui, Private Tutors, Musicians, Ramen, Tattoo, Art Galleries, Piercing, Taxis, Tea Room, Teppanyaki, Tours, Boat Charters, Ferries, Flight Instruction, Travel Services, Toy Stores, Comic Books, Trains, Trampoline Parks, Indoor Playcentre, Transportation, Bus Tours, bus stations, buses, Travel Agents, Tutoring Centers, Summer Camps, Vacation Rentals, Video/Film Production, Audio/Visual Equipment Rental, Vocal Coach, Virtual Reality Centers, Yoga, Health Retreats, Pole Dancing Classes, Women's Clothing, Men’s Clothing, Amusement Parks, Arcades, Go Karts, Specialty Schools, Kids Activities, Bingo Halls, Karaoke, Food Trucks, Amateur Sports Teams, Social Clubs, Dance Schools, Landmarks & Historical Buildings, Town Hall, Professional Sports Teams, Accessories, Attraction Farms, Antiques, Mini Golf, Batting Cages, Astrologers, Psychic Mediums, Caricatures, Commissioned Artists, Car Share Services, Clowns, Magicians, Counseling & Mental Health, Framing, Printing Services, Flea Markets, Used, Vintage & Consignment, Haunted Houses, Hobby Shops, Jewelry, Watches, Race Tracks, Home Decor, Gift Shops, Indian, Guitar Stores, Photo Booth Rentals, Reiki, Supernatural Readings, Meditation Centers, Web Design, Graphic Design, Clock Repair, Snuggle Services, Musical Instruments & Teachers, Musicians, Vocal Coach, Pet Boarding, Pet Groomers, Pet Sitting, Pet Training, Pet Stores, Resorts, Water Parks, Sunglasses, Aerial Fitness, butcher, Caterers, dog parks, Commissioned Artists, cupcakes, Drive-In Theater, fast food, fishing, flea markets, florists, Food Delivery Services, gas stations, gold buyers, Hair Salons, Women's Clothing, hiking, health markets, Ice Cream & Frozen Yogurt, Juice Bars & Smoothies, Hot Dogs, Jet Skis, Paddleboarding, Tours, Paint-Your-Own Pottery, korean, life coach, makerspaces, marketing, Medical Transportation, private investigation, Private Jet Charter, Rafting/Kayaking, thai, Ticket Sales, courthouses, Fire Departments, Jails & Prisons, language schools, Public Services & Government, beverage stores, Bike Sharing, Calligraphy, Cheerleading, Childbirth Education, Doulas, Childbirth Education, Midwives, Prenatal/Perinatal Care, Childbirth Education, Prenatal/Perinatal Care, Lactation Services, College Counseling, Career Counseling, Editorial Services, Test Preparation, Educational Services, Tutoring Centers, CPR Classes, First Aid Classes, Criminal Defense Law, Personal Injury Law, General Litigation, Divorce & Family Law, Immigration Law, Wills, Trusts, & Probates, Elementary Schools, Middle Schools & High Schools, Flight Instruction, Aerial Tours, Private Jet Charter, Aircraft Dealers, Immigration Law, Personal Injury Law, Criminal Defense Law, Specialty Schools, Middle Schools & High Schools, Musical Instruments & Teachers, Performing Arts, Divey, Summer Camps, Kids Activities, Special Education, Speech Therapists, Parenting Classes, Home Health Care, Speech Training, game truck rental"
black_list_venue_types = black_list_venue_types.split(', ')
# convert to lower case
black_list_venue_types = [x.lower() for x in black_list_venue_types]

must_not_include_venue_types = [
    'musician',
    'musicians',
    'dj',
    'djs',
    'symphony'
]

venue_black_list = [
    'applebee',
    'symphony',
    'orchestra',
    'Subway',
    'IHOP',
    'Panera Bread',
    'Moe’s Southwest Grill',
    'Burlington Mall',
    'P.F. Chang’s',
    'Chuck E. Cheese',
    'Seasons 52',
    'Taco Bell',
    'Chili’s',
    'Applebee’s Grill + Bar',
    'Dave & Buster’s',
    'Yard House',
    'Buffalo Wild Wings',
    'School of Rock',
    'RaceTrac',
    'Ruby Tuesday',
    'Chuy’s',
    'Eddie V’s Prime Seafood',
    'Main Event',
    'Fleming’s Prime Steakhouse & Wine Bar',
    'Bowlero Chula Vista',
    'Sammy’s Restaurant & Bar',
    'red roof inn',
    'best buy'
]
llm = ChatOpenAI(
    model_name="gpt-3.5-turbo-0125",
    temperature=0,
    openai_api_key=openai_api_key
)
def check_blacklisted(email):
    if email is None:
        return False
    
    return all([black not in email for black in email_blacklist] + ['@' in email] + [email.startswith('u00') == False] + [email.count('@') == 1])

def is_blacklisted_venue(venue_name):
    return any([black.lower() in venue_name.lower() for black in venue_black_list])

# … for example “museums, music venues” KEEP IT IN THAT CASE. The only exception to this rule is if 
# it says “musician, music venue” if "musician" is in there with “music venue” it still gets deleted. 
# Also have scraper reject any venues that come back with a blank “type” UNLESS it has emails with it
# REJECT THESE “TYPE” COLUMN (UNLESS “MUSIC VENUES” IS TIED INTO THE KEYWORDS!!!! BUT unless one of the 
# keywords is “musicians” or “dj” or “symphony” even if music venue is tied to those 2 - reject) / 
# Also make it easy to add more “rejected types” later if we need to. 
# Also reject for “DJ” also have the db look at “venue” and reject if “dj” is in the venue name. 
# (meaning crawler doesn’t scrape it, and moves on to next work)
def is_blackeslisted_venue_type(venue_types):
    
    for venue_type in venue_types:
        if venue_type.strip().lower() in must_not_include_venue_types:
            return True
        
    low_cases_venue_types = [venue_type.strip().lower() for venue_type in venue_types]
    
    for venue_type in venue_types:
        if venue_type.strip().lower() in black_list_venue_types and not "music venue" in low_cases_venue_types and not "music venues" in low_cases_venue_types:
            return True
    
    return False
    

def send_push_notification(subscription, title,  body, reminder_id, vapid_claims, vapid_private_key, url):
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({"title": title, "body": body, "reminderId": reminder_id, "url": url}),
            vapid_private_key=vapid_private_key,
            vapid_claims=vapid_claims
        )
    except WebPushException as ex:
        print(f"Error sending push notification: {ex}")
        return False
    return True

def is_music_venue(venue_type, batch_filter_venues):
    for venue in venue_type.split(','):
        if venue.strip() in batch_filter_venues:
            return True
    return False


def get_sub_batches(music_batch, batch_size):

    batch_count = len(music_batch) // batch_size
    if len(music_batch) % batch_size != 0:
        batch_count += 1

    sub_batches = []
    for i in range(batch_count):
        start = i * batch_size
        end = start + batch_size
        sub_batches.append(music_batch[start:end])

    return sub_batches

def extract_first_name(email):
    '''
    Use the LLM to extract the first name from the given text.
    '''
    template = """Extract the first name from the given text. The text is: {email}.
                  Do not add any attributes, Do NOT add any additional words. 
                  Just First Name of Person only. If there is no first name of person then return 'None'."""
    
    prompt = PromptTemplate(template=template, input_variables=["email"])

    llm_chain = LLMChain(prompt=prompt, llm=llm)
        
    output = llm_chain.invoke(input=email)
    return output['text']


def extract_address(address):
    address_parser  = pyap.parse(address, country='US')
    try:
        parsed_address = address_parser[0]
        city = parsed_address.city
        state = parsed_address.region1
    except IndexError as e:
        # print(address, 'not parsed', str(e))
        try:
            city = address.split(',')[0].strip().split()[-1]
        except Exception as e:
            city = ""
            state = ""
            return city, state
            
        try:
            state = address.split(',')[1].strip().split()[0]
        except Exception as e:
            state = ""

    except Exception as e:
        city = ""
        state = ""

    if city == "York":
        city = "New York"
    if city == "Angeles":
        city = "Los Angeles"
    if city == "Vegas":
        city = "Las Vegas"
    if city == "Francisco":
        city = "San Francisco"
    if city == "Diego":
        city = "San Diego"
    if city == "Jose":
        city = "San Jose"
    if city == "Antonio":
        city = "San Antonio"
    if city == "Orleans":
        city = "New Orleans"
    if city == "Beach":
        city = "Miami Beach"
    if city == "Clemente":
        city = "San Clemente"

    return city, state

# class Person(BaseModel):
#     name: Optional[str] = Field(
#         description="The Person First Name which is hidden inside the email address."
#     )
#     email: Optional[str] = Field(
#         description="The email address."
#     )

# schema, extraction_validator = from_pydantic(
#     Person,
#     description="""You're an information extractor working for a data analytics firm.
#     Your primary responsibility is to process unstructured data and extract valuable information
#     for various clients across industries. Recently, your team received a dataset containing a list
#     of email addresses from a client who wants to identify person associated with these emails. The person first name is hidden inside the email address think step by step.
#     Your task is to accurately extract the first name of the person from the email addresses
#     and present the findings in a structured format for further analysis. Your expertise in natural language
#     processing and data extraction techniques will be crucial in completing this task effectively. Do not consider 'info' as a person first name.""",

#     examples = [
#     (
#         'kimrobinson@bestdayeverpicnics.com',
#         {"name": 'Kim', 'email': 'kimrobinson@bestdayeverpicnics.com'}
#     ),
#     (
#         'krista@ohwhatfunpartyco.com',
#         {"name": 'Krista', 'email': 'krista@ohwhatfunpartyco.com'}
#     ),
#     (
#         'levenuebrandon@gmail.com',
#         {"name": 'Brandon', 'email': 'levenuebrandon@gmail.com'}
#     ),
#     (
#         'lorrin@wagnerevents.com',
#         {"name": 'Lorrin', 'email': 'lorrin@wagnerevents.com'}
#     ),
#     (
#         'michelle@preciousmomentseventsllc.com',
#         {"name": 'Michelle', 'email': 'michelle@preciousmomentseventsllc.com'}
#     ),
#     (
#         'myevent.kingdomkatering@gmail.com',
#         {"name": 'Kingdom', 'email': 'myevent.kingdomkatering@gmail.com'}
#     ),
#     (
#         'mylezedwardcreations@gmail.com',
#         {"name": 'Mylez Edward', 'email': 'mylezedwardcreations@gmail.com'}
#     ),
#     (
#         'nancycottoevents@gmail.com',
#         {"name": 'Nancy', 'email': 'nancycottoevents@gmail.com'}
#     ),
#     (
#         'natalia@daysrememberedbynd.com',
#         {"name": 'Natalia', 'email': 'natalia@daysrememberedbynd.com'}
#     ),
#     (
#         'nikkiplansparties@gmail.com',
#         {"name": 'Nikki', 'email': 'nikkiplansparties@gmail.com'}
#     ),
#     (
#         'nomadicfeteart@gmail.com',
#         {"name": 'Nomadic', 'email': 'nomadicfeteart@gmail.com'}
#     ),
#     (
#         'pam@igniteyouroccasion.com',
#         {"name": 'Pam', 'email': 'pam@igniteyouroccasion.com'}
#     ),
#     (
#         'pamela@atmospheresdesigns.com',
#         {"name": 'Pamela', 'email': 'pamela@atmospheresdesigns.com'}
#     ),
#     (
#         'john@atmospheresdesigns.com',
#         {"name": 'John', 'email': 'john@atmospheresdesigns.com'}
#     ),
#     (
#         'gue@atmospheresdesigns.com',
#         {"name": 'Gue', 'email': 'gue@atmospheresdesigns.com'}
#     ),
#     (
#         'renee@partyhosthelper.com',
#         {"name": 'Renee', 'email': 'renee@partyhosthelper.com'}
#     ),
#     (
#         'sherrywilliamsmusic@verizon.net',
#         {"name": 'Sherry', 'email': 'sherrywilliamsmusic@verizon.net'}
#     ),
#     (
#         'Britt@elcidsunset.com',
#         {"name": 'Britt', 'email': 'Britt@elcidsunset.com'}
#     ),
#     (
#         'acesbargrill@gmail.com',
#         {"name": 'None', 'email': 'acesbargrill@gmail.com'}
#     ),
#     (
#         'adgreservation@alilahotels.com',
#         {"name": 'None', 'email': 'adgreservation@alilahotels.com'}
#     ),
#     (
#         'adr@coi.cz',
#         {"name": 'None', 'email': 'adr@coi.cz'}
#     ),
#     (
#         'advancedbookingtennis@outlook.com',
#         {"name": 'None', 'email': 'advancedbookingtennis@outlook.com'}
#     ),
# ],
#     many=True,
# )


# chain = create_extraction_chain(
#     llm,
#     schema,
#     encoder_or_encoder_class="csv",
#     validator=extraction_validator,
#     input_formatter="triple_quotes",
# )

# def create_chunks(path=None, emails=None):
#     if path:
#         loader = TextLoader(path)
#         data = loader.load()
#         data[0].page_content = data[0].page_content.replace('\n', ', ')
#         text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000)
#         docs = text_splitter.split_documents(data)
#     elif emails:
#         text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000)
#         if isinstance(emails, str):
#             emails = [emails]
#         emails = ', '.join(emails)
#         texts = text_splitter.create_documents([emails])
#         docs = text_splitter.split_documents(texts)
#     else:
#         raise ValueError("You must provide either a file path or a list of emails.")
#     return docs

# async def extract_first_names_from_emails(path=None, emails=None):
#     split_docs = create_chunks(emails=emails)

#     with get_openai_callback() as cb:
#         document_extraction_results = await extract_from_documents(
#             chain, split_docs, max_concurrency=3, use_uid=False, return_exceptions=True
#         )
#         # print    (f"Total Tokens: {cb.total_tokens}")
#         # print(f"Prompt Tokens: {cb.prompt_tokens}")
#         # print(f"Completion Tokens: {cb.completion_tokens}")
#         # print(f"Successful Requests: {cb.successful_requests}")
#         # print(f"Total Cost (USD): ${cb.total_cost}")

#     return document_extraction_results


# def generate_email_name_pairs(json_data):
#     email_name_pairs = []
#     for record in json_data:
#         employee_list = record.get('data', {}).get('person', [])
#         for employee in employee_list:
#             email = employee.get('email', '')
#             name = employee.get('name', '')  # Extracting the first name
#             email_name_pairs.append({'Email': email, 'First_Name': name})
#     return email_name_pairs

if __name__ == '__main__':
    # print(check_blacklisted(''))
    
    print(is_blackeslisted_venue_type(['symphony', 'Music Venue']))


