from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_openai import ChatOpenAI
import pyap
from pywebpush import webpush, WebPushException
import json

import emailable
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


emailable_client = emailable.Client(api_key=os.getenv("EMAILABLE_API_KEY"))


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
                'eben@eyebytes.com',
                'eyebytes.com',
                'amkryukov@gmail.com',
                '@doe.com',
                '@xxx.com',
                '@web.com',
                'calendar.google.com',
                '@n-.os',
                '@9j.wn'
             ]

def read_black_list_venue_types():
    """
    Reads the black list venue types from a file.
    """
    try:
        venue_types = []

        self_path = os.path.dirname(os.path.abspath(__file__))
        bl_venue_path = os.path.join(self_path, 'black_list_venue_types.txt')

        with open(bl_venue_path, 'r') as file:
            for line in file.readlines():
                # Remove leading/trailing whitespace and newline characters
                line = line.strip()
                if line:
                    venue_types.append(line.lower())  # Convert to lower case
            
    except FileNotFoundError:
        print("Black list venue types file not found.")
        return []

    return venue_types

black_list_venue_types = read_black_list_venue_types()

# print(black_list_venue_types)

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
    'best buy',
    'Dunkin’', 
    'Krispy Kreme',
    'McDonald’s', 
    'Zaxbys',
    'Aldi',
    'Meijer',
    'Wendy’s',
    'Horse Racing',
    'Horse Boarding'
]
llm = ChatOpenAI(
    model_name='gpt-4',
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
# & for “Venues & Event Spaces”, and “Wine Tours” - REMOVE ONLY IF IT’S NOT combined with other keywords (“Venues & Event Spaces” - counts as a single keyword) (for example “Venues & Event Spaces, Beer Gardens” would be OK)
# For the single keyword “Colleges & Universities” REMOVE ONLY if it IS combined with other keywords UNLESS ONE OF THEM ARE “Music Venues” (ex: Colleges & Universities, Police Departments - REJECT)…so to summarize the single keyword “Colleges & Universities” SHOULD ONLY ACCEPT IT IF IT’S STANDALONE (Unless it also has “music venue” tied to it - keep it)
# BAD EMAILS (Reject JUST the email address)

def is_blackeslisted_venue_type(venue_types):
    
    for venue_type in venue_types:
        if venue_type.strip().lower() in must_not_include_venue_types:
            return True
        
    low_cases_venue_types = [venue_type.strip().lower() for venue_type in venue_types]
    
    for venue_type in venue_types:
        if venue_type.strip().lower() in black_list_venue_types and not "music venue" in low_cases_venue_types and not "music venues" in low_cases_venue_types:
            return True

        if "venues & event spaces" in venue_type.strip().lower() and len(venue_types) == 1:
            return True
        
        if "wine tours" in low_cases_venue_types and len(venue_types) == 1:
            return True
        
        if "colleges & universities" in low_cases_venue_types and len(venue_types) > 1:
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
    if email.strip() == '':
        return ''
    
    template = """Extract ONLY a valid human first name from email: "{email}"
    
CRITICAL RULES:
- Return ONLY if it's a recognizable human first name (like John, Mary, David, Sarah, Michael, etc.)
- REJECT generic terms: info, contact, admin, support, sales, help, service, webmaster, hello, test, user
- REJECT company/department/role names
- If unsure, return empty string
- No explanations, just the name or empty string

Valid examples: 
john.doe@email.com → john
jane_doe@company.org → jane
michael-smith@gmail.com → michael

Invalid examples:
info@company.com → 
admin@site.com → 
support@help.com → 

Output:"""
    
    prompt = PromptTemplate(template=template, input_variables=["email"])
    llm_chain = LLMChain(prompt=prompt, llm=llm)
        
    output = llm_chain.invoke(input=email)
    return output['text']

def extract_city_state(address):
    '''
    Use the LLM to extract the city and state from the given address.
    '''
    if address is None or address.strip() == "":
        return '', ''
    
    template = """Extract the city and state from the given address. The address is: {address}.
                  Do not add any attributes, Do NOT add any additional words. 
                  Just City and State only in json format like this:
                  {{"city": "City Name", "state": "State Name"}}. If there is no state return region ."""
    
    prompt = PromptTemplate(template=template, input_variables=["address"])

    llm_chain = LLMChain(prompt=prompt, llm=llm)

    
    output = llm_chain.invoke(input=address)
    try:
        text = json.loads(output['text'])
        city = text.get('city', '')
        state = text.get('state', '')
        return city, state
    except json.JSONDecodeError:
        print("Error decoding JSON:", output['text'])
        return '', ''


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

def check_emailable(email):
    response = emailable_client.verify(email)
    return response
    
if __name__ == '__main__':
    # print(check_blacklisted(''))
    
    # print(is_blackeslisted_venue_type(['Middle Schools & High Schools']))

    response  = check_emailable('test@example.com')
    print(response.status_code)
    print(response.accept_all)
