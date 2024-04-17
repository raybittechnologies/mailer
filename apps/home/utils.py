from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_openai import ChatOpenAI
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

blacklist = ['@email.com', '@example.com','@domain.com','@godaddy.com','@address.com','@filler.com','@xyz.com','@newsletter.com','@mystore.com', 'example@gmail.com', '@sentry', 'mail@mail.com', '@mail.com', 'example@mail.com', '.png', '.jpg']

llm = ChatOpenAI(
    model_name="gpt-3.5-turbo-0125",
    temperature=0,
    openai_api_key=openai_api_key
)
def check_blacklisted(email):
    return all([black not in email for black in blacklist] + ['@' in email])


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
    print(check_blacklisted("https://www.example.com"))
