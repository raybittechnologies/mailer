# from scrapy.crawler import CrawlerProcess
# from apps.home.script import  homes
from functools import wraps
import os
import pprint
import time
import json
import pytz
import tzlocal
from dotenv import load_dotenv

load_dotenv()

from apps.authentication.models import Users
from apps.authentication.util import verify_pass, hash_pass
from apps.home import blueprint
from flask import render_template, request, jsonify, redirect, url_for, current_app, send_file
from flask_login import login_required, current_user, logout_user, login_user
from jinja2 import Template as JT

from apps.config import API_GENERATOR
import requests
from datetime import datetime, timedelta, timezone
from apps import db, scheduler, csrf
import multiprocessing
from apps.home.script import yelp_scraper_run
from apps.models import *
from apps.db_utils import db_session, db_transaction, bulk_save_with_retry, safe_db_operation, get_db_connection_info, cleanup_connections
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import Insert

from concurrent.futures import ThreadPoolExecutor
from apps.authentication.forms import LoginForm, CreateAccountForm
from apps.home.emailler import *
from apps.authentication.util import generate_job_id
from nylas import Client
from nylas.models.auth import URLForAuthenticationConfig
from nylas.models.auth import CodeExchangeRequest
import pyap
from flask import Response
import base64
from sqlalchemy import or_ , and_

import pandas as pd
import urllib.parse

from pywebpush import webpush, WebPushException

from apps.home.utils import check_blacklisted, extract_city_state, send_push_notification, is_music_venue, get_sub_batches, check_emailable

NYLAS_API_KEY = os.getenv('NYLAS_API_KEY')
NYLAS_API_URI = os.getenv('NYLAS_API_URI')

print("NYLAS_API_URI: ", NYLAS_API_URI)

nylas = Client(
    api_key = NYLAS_API_KEY,
    api_uri = NYLAS_API_URI,
)

# calculate the number of workers to use - reduced to prevent DB connection overflow
workers = min(20, multiprocessing.cpu_count() + 1)  # Cap at 20 workers
print("Number of workers: ", workers)
executor = ThreadPoolExecutor(max_workers=workers)

processes = {}

@blueprint.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "frame-ancestors 'none';"
    return response


def role_required(role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            admin = Users.query.filter_by(email=current_user.email).first()
            if admin:
                if admin.role != role:
                    logout_user()
                    return redirect(url_for('home_blueprint.admin_login'))
                else:
                    return fn(*args, **kwargs)
            else:
                logout_user()
                return redirect(url_for('home_blueprint.admin_login'))
        return wrapper
    return decorator


def user_approved_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = Users.query.filter_by(email=current_user.email).first()
        if user and user.state == "pending":
            return redirect(url_for('home_blueprint.index'))
        else:
            return fn(*args, **kwargs)
    return wrapper



@blueprint.route('/home')
@login_required
def index():
    page_data = get_page_data()
    vapid_public_key = current_app.config.get('VAPID_PUBLIC_KEY')
    user_id = current_user.id
    print("VAPID_PUBLIC_KEY: ", vapid_public_key)
    return render_template('home/index.html', segment='index', API_GENERATOR=len(API_GENERATOR), page_data=page_data, public_key=vapid_public_key, user_id=user_id)

# https://github.com/sqlalchemy/sqlalchemy/issues/5374
@compiles(Insert, "mysql")
def mysql_insert_ignore(insert, compiler, **kw):
    return compiler.visit_insert(insert.prefix_with("IGNORE"), **kw)

@blueprint.route('/db_status', methods=['GET'])
@login_required
def db_status():
    """Database connection pool status endpoint"""
    try:
        connection_info = get_db_connection_info()
        if connection_info:
            return jsonify({
                "success": True,
                "connection_pool": connection_info,
                "message": "Database connection pool status retrieved successfully"
            })
        else:
            return jsonify({
                "success": False,
                "message": "Unable to retrieve database connection information"
            }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error retrieving database status: {str(e)}"
        }), 500

@blueprint.route('/cleanup_connections', methods=['POST'])
@login_required
def cleanup_db_connections():
    """Cleanup database connections endpoint"""
    try:
        cleanup_connections()
        return jsonify({
            "success": True,
            "message": "Database connections cleaned up successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error cleaning up connections: {str(e)}"
        }), 500

@blueprint.route('/url', methods=['POST', 'GET'])
@login_required
@user_approved_required
def url():
    if request.method == 'POST':
        locations = request.form['location'].split('|')
        businesses = request.form['business'].split('|')
        latitude = request.form['latitude']
        longitude = request.form['longitude']
        
        user = Users.query.get(current_user.id)
        
        if user.is_multi_search == 0:
            yeplurls = Yelpurl.query.filter_by(userid=current_user.id, state="running").all()
            if yeplurls:
                return {"success": False, "message": 'Another search is running. Please wait for it to complete.'}
        

        product_url = ""
        base_url = 'https://www.yelp.com/search?'
        urls = []
        for location in locations:
            for business in businesses:
                if business.strip() == "" or location.strip() == "":
                    continue
                encoded_business = urllib.parse.quote(business)
                encoded_location = urllib.parse.quote(location)

                encoded_url = f"find_desc={encoded_business}&find_loc={encoded_location}"
                url = base_url + encoded_url
                urls.append(url)
            
        product_url = ",".join(urls)

        existing_url = Yelpurl.query.filter_by(product_url=product_url, userid=current_user.id).first()
        if existing_url is None:
            business_name = ",".join(businesses)
            new_url = Yelpurl(product_url=product_url, userid=current_user.id, state="idle", name=business_name)
            new_url.latitude = latitude
            new_url.longitude = longitude
            with db_transaction() as session:
                session.add(new_url)
                session.flush()
                url_id = new_url.id
            return {"success": True, "message": "Url added successfully.", "url_id": url_id, "redirect": "/fetch/" + str(url_id)}
            
        else:
            print("already present in db")
            message = "This url is already reistered."
            url_id = existing_url.id
            return {"success": True, "message": message, "url_id": url_id, "redirect": "/url/view/" + str(url_id)}
            
        
    else:
        current_user_id = current_user.id
        user = Users.query.get(current_user_id)

        if user.is_multi_search == 1:
            return render_template('home/add_multi_url.html', segment='url')
        else:
            return render_template('home/add_url.html', segment='url')
        

# Add multiple urls
# @blueprint.route('/add_multi_url', methods=['POST'])
# @login_required
# @user_approved_required
# def add_multi_url():

#     location = request.form['location']
#     business = request.form['business']
#     latitude = request.form['latitude']
#     longitude = request.form['longitude']
    
#     print(request.form)
            
#     return {"success": True, "message": "Urls added successfully."}
        

# Export all data to excel file and download
@blueprint.route('/export_all_data', methods=['GET'])
@login_required
@user_approved_required
def export_all_data():
    services = Service.query.filter_by(user_id=current_user.id).all()
    all_services = {}
    services_list = []
    # make differnt dataframe per url_id and save it to excel in different sheet
    print("Total services: ", len(services))
    for service in services:
        biz_id = service.biz_id
        if biz_id in services_list and current_user.is_allow_deduplicate:
            print("Duplicate service found: ", biz_id)
            continue

        url_id = service.url_id
        address = service.address

        city = service.city
        state = service.state

        data = {
            'venue' : service.name,
            'phone': service.phone,
            'address': service.address,
            'city' : city,
            'state' : state,
            'type': service.venue_type,
            'website': service.website,
            'email1' : service.email1 if service.email1 else "",
            'firstname1' : service.first_name1 if service.first_name1 and service.first_name1 != "None" else "",
            'email2' : service.email2 if service.email2 else "",
            'firstname2' : service.first_name2 if service.first_name2 and service.first_name2 != "None" else "",
            'email3' : service.email3 if service.email3 else "",
            'firstname3' : service.first_name3 if service.first_name3 and service.first_name3 != "None" else "",
            'email4' : service.email4 if service.email4 else "",
            'firstname4' : service.first_name4 if service.first_name4 and service.first_name4 != "None" else "",
            'facebookemail1' : service.fbemail1 if service.fbemail1 else "",
            'firstname5' : service.first_name5 if service.first_name5 and service.first_name5 != "None" else "",
            'facebookemail2' : service.fbemail2 if service.fbemail2 else "",
            'firstname6' : service.first_name6 if service.first_name6 and service.first_name6 != "None" else "",
            'facebook' : service.facebook if service.facebook else "",
            'customtext' : "",
            'notes' : "",
            'bademail' : service.bademail if service.bademail else "",
            'venueid' : service.biz_id
        }

        if url_id not in all_services:
            all_services[url_id] = []
        all_services[url_id].append(data)
        services_list.append(biz_id)

    print("Total unique services: ", len(services_list))


    if all_services:
        upload_folder = "uploads"
        server_file_path = os.path.join(upload_folder, f'all_services_{current_user.id}.xlsx')
        
        with pd.ExcelWriter(server_file_path) as writer:
            for key, value in all_services.items():
                yelp_url = Yelpurl.query.get(key)
                if yelp_url is None:
                    continue

                product_url = yelp_url.product_url.split(',')[0]
                parsed_url = urllib.parse.urlparse(product_url)
                business = urllib.parse.parse_qs(parsed_url.query)['find_desc'][0]
                location = urllib.parse.parse_qs(parsed_url.query)['find_loc'][0]
                sheet_name = f"{business} in {location}"
                sheet_name = sheet_name[:31]
                df = pd.DataFrame(value)
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # get project root path
        project_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        server_file_path = os.path.join(project_path, server_file_path)

        return send_file(server_file_path, as_attachment=True)
    
    return "No data to export"


@blueprint.route('/url_history')
@login_required
@user_approved_required
def url_history():
    user_urls = Yelpurl.query.filter_by(userid=current_user.id).order_by(Yelpurl.create_datetime.desc()).all()
    url_list = []

    for url_entry in user_urls:
        url_data = {
            'url_id': url_entry.userid,
            'product_url': url_entry.product_url,
            'id': url_entry.id,
            'name': url_entry.name,
            'state' : url_entry.state,
            'updated_datetime' : url_entry.create_datetime,
            'latitude': url_entry.latitude,
            'longitude': url_entry.longitude
        }
        url_list.append(url_data)

    return jsonify(url_list)


# get all services for user
@blueprint.route('/get_all_services', methods=['GET'])
@login_required
@user_approved_required
def get_all_services():
    user_services = Service.query.filter(Service.user_id==current_user.id, and_(Service.latitude != '', Service.longitude != '')).limit(6000).all()
    # convert to list of dicts
    service_list = [service.to_dict() for service in user_services]

    return jsonify(service_list)


@blueprint.route('/view_url_history/<int:url_id>')
@login_required
@user_approved_required
def view_url_history(url_id):
    # Return only the urls that are credited
    user_urls = Service.query.filter_by(url_id=url_id, user_id=current_user.id).all()
    url_list = []
    for url_entry in user_urls:
        
        url_data = {
            "id": url_entry.id,
            "venue_type": url_entry.venue_type,
            "website": url_entry.website,
            "phone": url_entry.phone,
            "address": url_entry.address,
            "url_id": url_entry.url_id,
            "user_id": url_entry.user_id,
            "city": url_entry.city,
            "state": url_entry.state,
            "zip": url_entry.zip,
            "country": url_entry.country,
            "latitude": url_entry.latitude,
            "longitude": url_entry.longitude,
            "thumnailurl": url_entry.thumnailurl
        }

        if current_user.role != "lite":
            url_data['venue'] = url_entry.name
            url_data['facebook'] = url_entry.facebook
            url_data['instagram'] = url_entry.instagram
            url_data['twitter'] = url_entry.twitter
            url_data['email1'] = url_entry.email1
            url_data['email2'] = url_entry.email2
            url_data['email3'] = url_entry.email3
            url_data['email4'] = url_entry.email4
            url_data['fbemail1'] = url_entry.fbemail1
            url_data['fbemail2'] = url_entry.fbemail2
            url_data['bademail'] = url_entry.bademail
            url_data['first_name1'] = url_entry.first_name1
            url_data['first_name2'] = url_entry.first_name2
            url_data['first_name3'] = url_entry.first_name3
            url_data['first_name4'] = url_entry.first_name4
            url_data['first_name5'] = url_entry.first_name5
            url_data['first_name6'] = url_entry.first_name6
            url_data['biz_id'] = url_entry.biz_id

        url_list.append(url_data)
    return jsonify(url_list)


@blueprint.route('/view_scraped_data/<int:url_id>', methods=['GET'])
@login_required
@user_approved_required
def view_scraped_data(url_id):
    
    # Return only the services that are not credited
    user_urls = Service.query.filter_by(user_id=current_user.id, url_id=url_id, is_credited=0).limit(10).all()
    url_list = []
    for url_entry in user_urls:
        url_data = {
            "id": url_entry.id,
            "name": url_entry.name,
            "venue_type": url_entry.venue_type,
            "website": url_entry.website,
            "phone": url_entry.phone,
            "address": url_entry.address,
            "url_id": url_entry.url_id,
            "user_id": url_entry.user_id,
        }
        url_list.append(url_data)
    return jsonify(url_list)


@blueprint.route('/view_credited_data/<int:url_id>', methods=['GET'])
@login_required
@user_approved_required
def view_credited_data(url_id):
    
    # Return only the services that are not credited
    user_urls = Service.query.filter_by(user_id=current_user.id, url_id=url_id, is_credited=1).all()
    url_list = []
    for url_entry in user_urls:
        url_data = {
            "id": url_entry.id,
            "name": url_entry.name,
            "venue_type": url_entry.venue_type,
            "website": url_entry.website,
            "phone": url_entry.phone,
            "address": url_entry.address,
            "facebook": url_entry.facebook,
            "instagram": url_entry.instagram,
            "twitter": url_entry.twitter,
            "email1": url_entry.email1,
            "email2": url_entry.email2,
            "email3": url_entry.email3,
            "email4": url_entry.email4,
            "fbemail1": url_entry.fbemail1,
            "fbemail2": url_entry.fbemail2,
            "bademail": url_entry.bademail,
            "url_id": url_entry.url_id,
            "user_id": url_entry.user_id,
        }
        url_list.append(url_data)
    return jsonify(url_list)

@blueprint.route('/view_master_credited_data', methods=['GET'])
@login_required
@user_approved_required
def view_master_credited_data():
    
    # Return only the services that are not credited
    user_urls = Service.query.filter_by(user_id=current_user.id, is_credited=1).all()
    url_list = []
    for url_entry in user_urls:
        url_data = {
            "id": url_entry.id,
            "name": url_entry.name,
            "venue_type": url_entry.venue_type,
            "website": url_entry.website,
            "phone": url_entry.phone,
            "address": url_entry.address,
            "facebook": url_entry.facebook,
            "instagram": url_entry.instagram,
            "twitter": url_entry.twitter,
            "email1": url_entry.email1,
            "email2": url_entry.email2,
            "email3": url_entry.email3,
            "email4": url_entry.email4,
            "fbemail1": url_entry.fbemail1,
            "fbemail2": url_entry.fbemail2,
            "bademail": url_entry.bademail,
            "url_id": url_entry.url_id,
            "user_id": url_entry.user_id,
        }
        url_list.append(url_data)
    return jsonify(url_list)

@csrf.exempt
@blueprint.route('/history', methods=['POST', 'GET'])
@login_required
@user_approved_required
def history():
    return render_template('home/view_urls.html', segment='history')
    

@blueprint.route('/view_credited/<int:url_id>')
@login_required
@user_approved_required
def view_credited(url_id):
    credited = Service.query.filter_by(user_id=current_user.id, url_id=url_id, is_credited=1).count()
    return render_template('home/view_credited_data.html', segment='history', credited=credited, url_id=url_id)


@blueprint.route('/view_master_credited')
@login_required
@user_approved_required
def view_master_credited():
    credited = Service.query.filter_by(user_id=current_user.id, is_credited=1).count()
    return render_template('home/view_master_credited_data.html', segment='history', credited=credited)

@csrf.exempt
@blueprint.route('/update/credit', methods=['POST'])
@login_required
@user_approved_required
def credit_service():
    serviceid = request.json['id']
    action = request.json['action']

    with db_session() as session:
        user_credit = session.query(UserCredit).filter_by(userid = current_user.id).first()

        if user_credit is None:
            message = "Could not find credit info!"
            return {"success": False, 'message': message}

        credited_services = Service.query.filter_by(user_id = current_user.id, is_credited = 1).count()
        user_available_credit = user_credit.credit - credited_services
        service = Service.query.get(serviceid)

        if action == 'plus':
            if user_available_credit > 0:
                service.is_credited = 1
                message = f"Service '{service.name}' is credited successfully."
                available_credit = user_available_credit - 1
                return {"success": True, 'message': message, "available_credit" : available_credit, "user_credit" : user_credit.credit }
            
            else:
                return {"success": False, 'message': "You consumed all credit. You can not add more services."}
        else:
            service.is_credited = 2
            message = f"Service '{service.name}' is not credited."
            available_credit = user_available_credit
            return {"success": True, 'message': message, "available_credit" : available_credit, "user_credit" : user_credit.credit }


@csrf.exempt
@blueprint.route('/fetch/<int:id>', methods=['GET', 'POST'])
@login_required
@user_approved_required
def fetch(id):
    obj = Yelpurl.query.get(id)
    if obj.state != "running":
        obj.state = "running"
        
        urls = obj.product_url.split(',')
        
        #delete all sevices in db before run
        Service.query.filter_by(url_id=id).delete()
        db.session.commit()
        # run scraper
        user_info = {
            'id': current_user.id,
            'email': current_user.email,
            'role': current_user.role,
            'is_opt_musicians': current_user.is_opt_musicians,
            'is_allow_deduplicate': current_user.is_allow_deduplicate
        }
        try:
            executor.submit(lets_start, urls, id, user_info)
        except:
            print("something went wrong")
        
    return redirect(url_for('home_blueprint.fetching', id=id))

@csrf.exempt
@blueprint.route('/complete', methods=['POST'])
def complete_process():
    id = request.json['id']
    yelpurl = Yelpurl.query.get(int(id))
    yelpurl.state = "completed"
    db.session.commit()
    return "Completed"


@blueprint.route('/fetching', methods=['GET', 'POST'])
@login_required
@user_approved_required
def fetching():
    id = request.args.get('id')
    yelpurl = Yelpurl.query.get(id)
    print(yelpurl)
    
    if yelpurl.state == "running":
        if current_user.role == "lite":
            return render_template('home/fetch_url_data_for_lite.html', segment='url', current_url=yelpurl )
        else:
            return render_template('home/fetch_url_data.html', segment='url', current_url=yelpurl )
    else:
        return redirect(url_for('home_blueprint.url_view', id=id))
    
    
@blueprint.route('/uploaded_files', methods=['GET'])
@login_required
@user_approved_required
def uploaded_files():
    uploaded_files = Uploadedcontactfile.query.filter(Uploadedcontactfile.user_id == current_user.id, \
                                                    or_(Uploadedcontactfile.is_archived == None, Uploadedcontactfile.is_archived == False))\
                                                    .order_by(Uploadedcontactfile.create_datetime.desc()).all() # In SQL, NULL != 1 is unknown, not true.
    files = []

    for file in uploaded_files:
        url_data = {
            'id': file.id,
            'description': file.description,
            'filepath': file.filepath,
            'filename': file.filename,
            'create_datetime' : file.create_datetime
        }
        files.append(url_data)

    print("Total files: ", len(files))
    return jsonify(files)

@blueprint.route('/archive_contacts', methods=['GET'])
@login_required
@user_approved_required
def archive_contacts():
    uploaded_files = Uploadedcontactfile.query.filter(Uploadedcontactfile.user_id == current_user.id, Uploadedcontactfile.is_archived == 1)\
                                                    .order_by(Uploadedcontactfile.create_datetime.desc()).all() #
    files = []

    for file in uploaded_files:
        url_data = {
            'id': file.id,
            'description': file.description,
            'filepath': file.filepath,
            'filename': file.filename,
            'create_datetime' : file.create_datetime
        }
        files.append(url_data)

    print("Total files: ", len(files))
    return jsonify(files)
    
    
@blueprint.route('/upload_contact', methods=['GET', 'POST'])
@login_required
@user_approved_required
def upload_contact():
    upload_folder = "uploads"
    if request.method == "GET":
        return render_template('home/upload_contact.html',segment='upload_contact')
    
    elif request.method == "POST":
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        f = request.files['file'] 
        filepath = os.path.join(upload_folder, f.filename)
        f.save(filepath)
        
        if ".csv" in f.filename:
            df = pd.read_csv(filepath)
        elif ".xlsx" in f.filename:
            df = pd.read_excel(filepath)
        else:
            return {"success": False, "message": "File type not supported."}

        # total rows
        total_rows = len(df)

        if total_rows > 1000:
            return {"success": False, "message": "File contains more than 1000 rows. Please upload a file with less than 1000 rows."}

        columns  = ['venue', 'type', 'website', 'phone', 'address', 'facebook', 'customtext', 'notes', 'bademail', 'venueid']
        if 'firstname' in df.columns and 'email' in df.columns:
            columns += ['firstname']
            columns += ['email']
        else:
            columns += ['firstname' + str(i) for i in range(1, 7)] + ['email' + str(i) for i in range(1, 5)] + ['facebookemail' + str(i) for i in range(1, 3)]

        for col in columns:
            if col not in df.columns:
                print(col, "not in columns")
                return {"success": False, "message": "Keep column names/order EXACTLY how they are here, and no more and no less!. Missing column: " + col}

        description = request.form['description']
        # print(request.form)
        #  Batch operation 2021-09-07
        auto_batch = request.form.get('auto-batch', "false")
        batch_out_music_venue = request.form.get('batch-out-music-venue', 'false')
        verify_email = request.form.get('verify-email', 'false')

        print("verify_email: ", verify_email)
        print("batch_out_music_venue: ", batch_out_music_venue)
        print("auto_batch: ", auto_batch)

        # print("auto_batch: ", auto_batch)
        # print("batch_out_music_venue: ", batch_out_music_venue)

        batch_size = GlobalSetting.query.filter_by(name='batch_size').first()
        if batch_size is None:
            batch_size = 105
        else:
            batch_size = int(batch_size.value)

        # contact_file = Uploadedcontactfile(filename=f.filename, filepath=filepath, description=description, user_id=current_user.id)
        # db.session.add(contact_file)
        # db.session.flush()
        # file_id = contact_file.id
        
        batch_filter_venues = GlobalSetting.query.filter_by(name='batch_filter_venues').first()
        if batch_filter_venues is None:
            batch_filter_venues = ['Music Venues', 'Stadiums & Arenas']
        else:
            batch_filter_venues = batch_filter_venues.value.split(',')

        print("batch_filter_venues: ", batch_filter_venues)
        print("batch_size: ", batch_size)
        
        total_services = []
        df.fillna("", inplace=True)

        emails = []
        for idx, item in df.iterrows():
            if 'subscribed' in df.columns:
                is_unsubscribed = 1 if item['subscribed'].lower() == "unsubscribed" else 0
            else:
                is_unsubscribed = 0

            if 'email' in df.columns:
                email = item['email'].strip() if item.get('email') else ""
                service = dict()
                service['venue'] = item['venue']
                service['venue_type'] = item['type']
                service['website'] = item['website']
                service['phone'] = item['phone']
                service['address'] = item['address']
                service['facebook'] = item['facebook']
                service['customtext'] = item['customtext']
                service['originalemail'] = item['notes']
                service['email'] = email
                service['is_unsubscribed'] = is_unsubscribed
                service['firstname'] = item['firstname']
                service['bademail'] = item['bademail']
                
                service['biz_id'] = item['venueid']
                service['city'] = item.get('city', "")
                service['state'] = item.get('state', "")
                

                if email and check_blacklisted(email):
                    if email not in emails and email:
                        emails.append(email.lower())
                        total_services.append(service)
                elif email == "":
                    service['is_unsubscribed'] = 1
                    total_services.append(service)
            else:
                email1 = item['email1'].strip() if item.get('email1') else ""
                email2 = item['email2'].strip() if item.get('email2') else ""
                email3 = item['email3'].strip() if item.get('email3') else ""
                email4 = item['email4'].strip() if item.get('email4') else ""
                facebookemail1 = item['facebookemail1'].strip() if item.get('facebookemail1') else ""
                facebookemail2 = item['facebookemail2'].strip() if item.get('facebookemail2') else ""
                
                biz_id = item['venueid']
                city = item.get('city', "")
                state = item.get('state', "")

                is_all_empty = email1 == "" and email2 == "" and email3 == "" and email4 == "" and facebookemail1 == "" and facebookemail2 == ""

                # gather not empty emails only
                non_empty_emails = []
                for email in [email1, email2, email3, email4, facebookemail1, facebookemail2]:
                    if email:
                        non_empty_emails.append(email)

                # all emails are empty
                if is_all_empty:
                    service = dict()
                    service['venue'] = item['venue']
                    service['venue_type'] = item['type']
                    service['website'] = item['website']
                    service['phone'] = item['phone']
                    service['address'] = item['address']
                    service['facebook'] = item['facebook']
                    service['customtext'] = item['customtext']
                    service['originalemail'] = item['notes']
                    service['email'] = ""
                    service['is_unsubscribed'] = 1
                    service['firstname'] = item['firstname1']
                    service['bademail'] = item['bademail']
                    service['biz_id'] = biz_id
                    service['city'] = city
                    service['state'] = state
                    total_services.append(service)

                else:
                    for idx, email in enumerate([email1, email2, email3, email4, facebookemail1, facebookemail2]):
                        service = dict()
                        service['venue'] = item['venue']
                        service['venue_type'] = item['type']
                        service['website'] = item['website']
                        service['phone'] = item['phone']
                        service['address'] = item['address']
                        service['facebook'] = item['facebook']
                        service['customtext'] = item['customtext']
                        service['originalemail'] = item['notes']
                        service['email'] = email
                        service['firstname'] = item['firstname' + str(idx+1)]
                        service['is_unsubscribed'] = is_unsubscribed
                        service['bademail'] = item['bademail']
                        # creeat random biz_id
                        service['biz_id'] = biz_id
                        service['city'] = city
                        service['state'] = state


                        if email and check_blacklisted(email):
                            if email not in emails:
                                emails.append(email.lower())
                                # check if email is in bademail 
                                bademail = Uploadedservice.query.filter_by(bademail=email, user_id=current_user.id).first()
                                if bademail:
                                    service['is_unsubscribed'] = 1

                                total_services.append(service)


        #  Apply batch algorith, so if auto_batch is checked, we will batch out by batch_size and filter out music venues

        if batch_out_music_venue == "true":
            music_batch = []
            other_batch = []
            for service in total_services:
                if is_music_venue(service['venue_type'], batch_filter_venues):
                    music_batch.append(service)
                else:
                    other_batch.append(service)
        else:
            music_batch = total_services
            other_batch = []

        music_sub_batches = []
        other_sub_batches = []

        if auto_batch == "true":
            music_sub_batches = get_sub_batches(music_batch, batch_size)
            other_sub_batches = get_sub_batches(other_batch, batch_size)
        
        else:
            music_sub_batches.append(music_batch)
            other_sub_batches.append(other_batch)

        for group_id, batch_group in enumerate([music_sub_batches, other_sub_batches]):
            idx = 0
            for sub_batch in batch_group:
                if len(sub_batch) == 0:
                    continue
                
                idx += 1
                if auto_batch == "false" and batch_out_music_venue == "false":
                    batch_name = description
                
                elif auto_batch == "true" and batch_out_music_venue == "false":
                    batch_name = f"{description} - Batch {idx}"
                
                elif auto_batch == "false" and batch_out_music_venue == "true":
                    if group_id == 0:
                        batch_name = f"{description} - Music Venues - Batch"
                    else:
                        batch_name = f"{description} - Batch"

                else:
                    if group_id == 0: # Music Venues
                        batch_name = f"{description} - Music Venues - Batch {idx}"
                    else:
                        batch_name = f"{description} - Batch {idx}"


                services = []
                batch_file = Uploadedcontactfile(filename=f.filename, filepath=filepath, description=batch_name, user_id=current_user.id)
                db.session.add(batch_file)
                db.session.flush()
                file_id = batch_file.id

                emailables = []
                for service in sub_batch:
                    if service['email'].strip() == '':
                        continue
                    
                    results = Uploadedservice.query.filter(Uploadedservice.email == service['email'], Uploadedservice.user_id == current_user.id).all()

                    if len(results) > 0:
                        continue

                    uservice = Uploadedservice(name=service['venue'], venue_type=service['venue_type'], email=service['email'], user_id = current_user.id, file_id=file_id)
                    uservice.website = service['website']
                    uservice.phone = service['phone']
                    uservice.address = service['address']
                    uservice.facebook = service['facebook']
                    uservice.customtext = service['customtext']
                    uservice.originalemail = service['originalemail']
                    uservice.is_unsubscribed = service['is_unsubscribed']
                    uservice.firstname = service['firstname']
                    uservice.bademail = service['bademail']
                    uservice.biz_id = service['biz_id']
                    uservice.city = service['city']
                    uservice.state = service['state']

                    try:
                        if verify_email == 'true' and service['email']: # if verify_email is ON
                            emailable = Emailables.query.filter_by(email=service['email']).first()
                            current_datetime = datetime.datetime.utcnow()
                            # time diff is less than 6 month
                            time_diff = current_datetime - emailable.updated_at if emailable else datetime.timedelta(days=181)

                            if emailable and time_diff < datetime.timedelta(days=180):
                                score = emailable.score 

                                if emailable.state.lower() != 'unknown' and score <= 50:
                                    uservice.email = ''
                                    uservice.is_unsubscribed = 1
                                    uservice.bademail = service['email']
                                    # print("uservice: ", uservice.email, " is_unsubscribed: ", uservice.is_unsubscribed, " bademail: ", uservice.bademail)
                            else:
                                emailable_email_check = check_emailable(service['email'])
                                if emailable_email_check.status_code == 200:

                                    if emailable is None:
                                        emailable = Emailables()

                                    emailable.email = service['email']
                                    score = emailable_email_check.score
                                    emailable.score = score
                                    emailable.state = emailable_email_check.state

                                    emailable.accept_all = 1 if emailable_email_check.accept_all else 0
                                    emailables.append(emailable)

                                    # print("Emailable email: ", emailable.email, " Score: ", emailable.score, " State: ", emailable.state)

                                    if emailable_email_check.state.lower() != 'unknown' and score <= 50:
                                        uservice.email = ''
                                        uservice.is_unsubscribed = 1
                                        uservice.bademail = service['email']

                                else:
                                    print("Emailable email check failed: ", emailable_email_check.status_code)

                    except Exception as e:
                        print("When uploading , verify email", repr(e))
                        pass

                    services.append(uservice)

                if services:
                    bulk_save_with_retry(services, batch_size=500)

                if emailables:
                    bulk_save_with_retry(emailables, batch_size=500)

        return {"success": True, "message": "File uploaded successfully."}


@blueprint.route('/contact/delete', methods=['POST'])
@login_required
@user_approved_required
def contact_delete():
    file_id = int(request.form[ 'fileid'])
    file = Uploadedcontactfile.query.get(file_id)
    try:
        if file:
            # file.is_archived = True
            Uploadedservice.query.filter_by(file_id=file_id).delete()
            # for service in Uploadedservice.query.filter_by(file_id=file_id).all():
            #     #  delete reminder
            #     for reminder  in Reminder.query.filter_by(userid=current_user.id, email=service.email).all():
            #         if scheduler.get_job(reminder.job_id):
            #             scheduler.remove_job(reminder.job_id)

            #         db.session.delete(reminder)
            #         db.session.commit()
            #     db.session.delete(service)

            db.session.delete(file)
            db.session.commit()

            return {"success": True, 'message': "File deleted successfully."}
        else:
            return {"success": False, 'message': "File not found."}
    except Exception as e:
        return {"success": False, 'message': "Failed to delete file."}

 
@blueprint.route('/contact/<int:id>', methods=['GET'])
@login_required
@user_approved_required
def view_contact(id):
    userid = current_user.id
    uploaded_file = Uploadedcontactfile.query.filter_by(id=id, user_id=userid).first()

    if uploaded_file:
        file_desc = uploaded_file.description
        is_archived = uploaded_file.is_archived
        return render_template('home/view_contact.html', fileid=id, file_desc=file_desc, is_archived=is_archived, segment='upload_contact')
        
    else:
        return render_template('home/page-404.html')
    
@blueprint.route('/masterview', methods=['GET'])
@login_required
@user_approved_required
def view_all_contact():
    return render_template('home/view_all_contact.html')

@blueprint.route('/archived_contacts_view', methods=['GET'])
@login_required
@user_approved_required
def view_archived_contact():
    return render_template('home/view_archived_contact.html')


# archived_campaigns_view
@blueprint.route('/archived_campaigns_view', methods=['GET'])
@login_required
@user_approved_required
def view_archived_campaign():
    return render_template('home/campaigns_archived_view.html')


@csrf.exempt        
@blueprint.route('/contacts/list/<int:id>', methods=['GET', 'POST'])
@login_required
@user_approved_required
def contacts_list(id):
    if request.method == 'GET':
        services = Uploadedservice.query.filter(\
            Uploadedservice.user_id==current_user.id, \
            Uploadedservice.file_id==id, \
            or_(Uploadedservice.is_archived == 0, Uploadedservice.is_archived == None)).order_by(Uploadedservice.create_datetime.desc()).all()
        all_services = []

        for service in services:
            data = {
                'id': service.id,   
                'name': service.name,
                'venue_type': service.venue_type,
                'email': service.email,
                'is_bad' : service.is_bad,
                'create_datetime' : service.create_datetime,
                'is_unsubscribed' : service.is_unsubscribed,
                'unsubscribe_token' : service.unsubscribe_token,
                'website': service.website,
                'phone': service.phone,
                'address': service.address,
                'facebook': service.facebook,
                'firstname': service.firstname,
                'customtext': service.customtext,
                'originalemail': service.originalemail,
                'city': service.city,
                'state': service.state,
                'bademail': service.bademail,
                'biz_id': service.biz_id
            }
            all_services.append(data)

        return jsonify(all_services)
    else:
        data = request.json
        return jsonify(data)


@blueprint.route('/service/<int:id>', methods=['GET'])
@login_required
@user_approved_required
def get_service(id):
    service = Uploadedservice.query.get(id)
    if service is None:
        return {"success": False, 'message': "Service not found."}, 404
    
    data = {
        'id': service.id,
        'name': service.name,
        'venue': service.venue_type,
        'email': service.email,
        'is_bad' : service.is_bad,
        'create_datetime' : service.create_datetime,
        'is_unsubscribed' : service.is_unsubscribed,
        'unsubscribe_token' : service.unsubscribe_token,
        'website': service.website,
        'phone': service.phone,
        'address': service.address,
        'facebook': service.facebook,
        'firstname': service.firstname if service.firstname and service.firstname != "None" else "",
        'customtext': service.customtext,
        'originalemail': service.originalemail,
        'city': service.city,
        'state': service.state,
        'bademail': service.bademail,
        'biz_id': service.biz_id
    }
    return jsonify(data)

# Edit service
@blueprint.route('/service/edit', methods=['POST'])
@login_required
@user_approved_required
def service_edit():
    data = request.form
    try:
        service = Uploadedservice.query.get(data['serviceid'])
        service.name = data['venue']
        service.email = data['email']
        service.firstname = data['firstname']
        service.customtext = data['customtext']
        service.originalemail = data['originalemail']
        service.phone = data['phone']
        service.bademail = data['bademail']
        db.session.commit()
        return {"success": True, 'message': "Service updated successfully."}
    # Mysql integrity error
    except Exception as e:
        print(str(e))
        return {"success": False, 'message': "Failed to update service. Might be duplicate email."}


@blueprint.route('/contacts/all', methods=['GET'])
@login_required
@user_approved_required
def contacts_all_list():
    services = Uploadedservice.query.filter(Uploadedservice.user_id==current_user.id, or_(Uploadedservice.is_archived == False, Uploadedservice.is_archived == None)).order_by(Uploadedservice.create_datetime.desc()).all()
    all_services = []

    for service in services:
        biz_id = service.biz_id
        data = {
            'id': service.id,
            'name': service.name,
            'venue_type': service.venue_type,
            'email': service.email,
            'is_bad' : service.is_bad,
            'create_datetime' : service.create_datetime,
            'is_unsubscribed' : service.is_unsubscribed,
            'unsubscribe_token' : service.unsubscribe_token,
            'website': service.website,
            'phone': service.phone,
            'address': service.address,
            'facebook': service.facebook,
            'firstname': service.firstname if service.firstname and service.firstname != "None" else "",
            'customtext': service.customtext,
            'originalemail': service.originalemail,
            'city': service.city,
            'state': service.state,
            'bademail': service.bademail,
            'biz_id': service.biz_id
        }
        all_services.append(data)

    return jsonify(all_services)


@blueprint.route('/contacts/archived', methods=['GET'])
@login_required
@user_approved_required
def contacts_archived_list():
    services = Uploadedservice.query.filter_by(user_id=current_user.id, is_archived=True).order_by(Uploadedservice.create_datetime.desc()).all()
    all_services = []

    for service in services:
        biz_id = service.biz_id
        data = {
            'id': service.id,
            'name': service.name,
            'venue_type': service.venue_type,
            'email': service.email,
            'is_bad' : service.is_bad,
            'create_datetime' : service.create_datetime,
            'is_unsubscribed' : service.is_unsubscribed,
            'unsubscribe_token' : service.unsubscribe_token,
            'website': service.website,
            'phone': service.phone,
            'address': service.address,
            'facebook': service.facebook,
            'firstname': service.firstname if service.firstname and service.firstname != "None" else "",
            'customtext': service.customtext,
            'originalemail': service.originalemail,
            'city': service.city,
            'state': service.state,
            'bademail': service.bademail,
            'biz_id': service.biz_id
        }
        all_services.append(data)

    return jsonify(all_services)


     
@blueprint.route('/service/delete', methods=['POST'])
@login_required
@user_approved_required
def service_delete():
    
    serviceid = request.form['serviceid']
    service = Uploadedservice.query.get(serviceid)
    
    if service:
        unsubscribe_token = service.unsubscribe_token
        Email.query.filter_by(unsubscribe_token=unsubscribe_token).delete()
        
        db.session.delete(service)

        email = service.email
        user_id = current_user.id
        #  delete reminder
        reminder = Reminder.query.filter_by(userid=user_id, email=email).first()
        if reminder:
            if scheduler.get_job(reminder.job_id):
                scheduler.remove_job(reminder.job_id)

            db.session.delete(reminder)
        db.session.commit()

    return {"success": True, 'message': "Service deleted successfully."}


# archive service
@blueprint.route('/service/archive', methods=['POST'])
@login_required
@user_approved_required
def service_archive():
    serviceid = request.form['serviceid']
    service = Uploadedservice.query.get(serviceid)

    if service:
        service.is_archived = True
        unsubscribe_token = service.unsubscribe_token
        Email.query.filter_by(unsubscribe_token=unsubscribe_token).update({'is_archived': True})
        db.session.commit()

        email = service.email
        user_id = current_user.id
        #  delete reminder
        reminder = Reminder.query.filter_by(userid=user_id, email=email).first()
        if reminder:
            if scheduler.get_job(reminder.job_id):
                scheduler.remove_job(reminder.job_id)

            db.session.delete(reminder)
            db.session.commit()

        return {"success": True, 'message': "Service archived successfully."}

    return {"success": False, 'message': "Service not found."}


@blueprint.route('/url/view/<int:id>', methods=['GET', 'POST'])
@login_required
@user_approved_required
def url_view(id):
    user_id = Yelpurl.query.get(id).userid
    user = Users.query.get(user_id)

    if user.role == "lite":
        credit = UserCredit.query.filter_by(userid=current_user.id).first().credit
        consumed = Service.query.filter_by(user_id=current_user.id, is_credited=1).count()
        available_credit = credit - consumed
        return render_template('home/view_scraped_data.html', segment='history', available_credit=available_credit, user_credit=credit, consumed=consumed, current_url_id=id)
    
    else:
        yelpurl = Yelpurl.query.get(id)
        return render_template('home/view_url_data.html', segment='history', current_url=yelpurl)
    
@blueprint.route('/user/disconnect_unimail', methods=['POST'])
@login_required
@user_approved_required
def disconnect_unimail():
    user_id=request.form['user_id']
    url=request.form['url']
    mailing = Mailing.query.filter_by(user_id=user_id).first()
    if mailing:
        db.session.delete(mailing)
        db.session.commit()
        print(f"Mailing for user_id={user_id} deleted successfully.")
    else:
        print(f"No mailing found for user_id={user_id}.")
    return redirect(url)


@blueprint.route('/url/delete', methods=['POST'])
@login_required
@user_approved_required
def url_delete():
    url_id = int(request.form['urlid'])
    yelpurl = Yelpurl.query.get(url_id)
    Service.query.filter_by(url_id=url_id).delete()
    db.session.delete(yelpurl)
    
    db.session.commit()
    return redirect(url_for('home_blueprint.history'))
    

@blueprint.route('/profile')
@login_required
def profile():
    user_credit = db.session.query(UserCredit).filter_by(userid=current_user.id).first()
    mailings=Mailing.query.filter_by(user_id=current_user.id).first()
    is_auto_unsub = current_user.is_auto_unsub
    if user_credit:
        credit  = user_credit.credit
    else:
        credit = None
    return render_template('home/profile.html', segment='profile', user_credit=credit, is_auto_unsub=is_auto_unsub,mailings=mailings)


@blueprint.route('/how-to')
@login_required
def how_to():
    return render_template('home/how_to.html', segment='how-to')


@blueprint.route('/how-to-edit')
@login_required
def how_to_edit():
    return render_template('home/how_to_edit.html', segment='how_to_edit')


@blueprint.route('/process_stop/<int:id>')
def process_state(id):
    yelpurl = Yelpurl.query.get(int(id))
    yelpurl.state = "completed"
    db.session.commit()

    if current_user.role == "lite":
        
        credit = UserCredit.query.filter_by(userid=current_user.id).first().credit
        consumed = Service.query.filter_by(user_id=current_user.id, is_credited=1).count()
        available_credit = credit - consumed
        
        return render_template('home/view_scraped_data.html', segment='history', available_credit=available_credit, user_credit=credit, consumed=consumed, current_url_id=id)
    
    else:
        return redirect(url_for('home_blueprint.url_view', id=id))

@csrf.exempt
@blueprint.route('/check_state/<int:id>', methods=['GET'])
def check_state(id):
    yelpurl = Yelpurl.query.get(int(id))
    if yelpurl:
        return yelpurl.state
    else:
        return "completed"


def get_segment(request):
    try:
        segment = request.path.split('/')[-1]
        if segment == '':
            segment = 'index'

        return segment

    except:
        return None


def get_all_filters():
    user_urls = Yelpurl.query.filter_by(userid=current_user.id).count()

    return user_urls

def get_email_data():
    # get total email sent by user, join Automation and Email table
    total_email_sent = Email.query.join(Automation, Automation.job_id == Email.job_id).filter(Automation.userid == current_user.id, Email.is_sent == 1).count()
    total_email_opened = Email.query.join(Automation, Automation.job_id == Email.job_id).filter(Automation.userid == current_user.id, Email.is_opened == 1).count()
    total_email_replied = Email.query.join(Automation, Automation.job_id == Email.job_id).filter(Automation.userid == current_user.id, Email.is_replied == 1).count()
    return total_email_sent, total_email_opened, total_email_replied

def get_page_data():
    data_filter = get_all_filters()
    total_email_sent, total_email_opened, total_email_replied = get_email_data()    
    page_data = {
        'total_filters': data_filter,
        'total_email_sent': total_email_sent,
        'total_email_opened': total_email_opened,
        'total_email_replied': total_email_replied
    }
    return page_data


def get_admin_data():
    user_urls = Yelpurl.query.count()
    users = Users.query.filter(Users.role != "admin").count()
    services = Service.query.count()

    page_data = {
        'total_filters': user_urls,
        'total_users': users,
        'services': services
    }
    return page_data


def lets_start(urls, id, user_info):
    process = multiprocessing.Process(target=starting,
                                      args=(urls, id, user_info))
    process.start()

    process.join()


def is_scraper_completed(id):
    WEB_HOST_IP = os.getenv("WEB_HOST_IP")
    response = requests.get(f'{WEB_HOST_IP}/check_state/' + str(id))
    if response.text == "completed":
        return True
    return False


def starting(urls, id, user_info):
    if len(urls) > 0:
        
        WEB_HOST_IP = os.getenv("WEB_HOST_IP")
        
        for url in urls:
            try:
                if is_scraper_completed(id):
                    break

                yelp_scraper_run(url, id, user_info)
            except Exception as e:
                print("Something went wrong in while scraping", str(e))
                raise e
                # continue
        
        response = requests.post(f'{WEB_HOST_IP}/complete', json={'id': id})
        response = requests.post(f'{WEB_HOST_IP}/msg', json={'result': "completed", 'id' : id, 'user_id' : user_info['id']})
        print("Processes", response.text)

@csrf.exempt
@blueprint.route('/admin/register', methods=['POST'])
@login_required
def register():
    # username = request.json.get('name')
    email = request.json.get('email').lower()
    password = request.json.get('password')
    role = request.json.get('role', 'premium')

    if not email or not password or not role:
        return jsonify({'message': 'Missing required fields'}), 400

    user = Users.query.filter_by(email=email).first()
    if user:
        return jsonify({'message': 'Already registered user'}), 400

    # else we can create the user
    user = Users(username=email, email=email, password=password, role=role)
    db.session.add(user)
    db.session.flush()
    user_settings = UserCampaignSetting(userid=user.id)
    db.session.add(user_settings) 
    db.session.commit()
    return jsonify({'message': 'User registered successfully'}), 201


@blueprint.route('/admin/login', methods=['POST', 'GET'])
def admin_login():
    logout_user()
    if request.method == 'POST':
        email = request.form['email'].lower()
        password = request.form['password']
        user = Users.query.filter_by(email=email, role="admin").first()
        # Check the password
        if user and verify_pass(password, user.password):
            login_user(user)
            return redirect(url_for('home_blueprint.admin'))
        else:
            return render_template("home/admin_sign_in.html", data={'message': 'Invalid credentials'})
    else:
        return render_template("home/admin_sign_in.html", data={'message': ''})


@blueprint.route('/admin', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def admin():
    page_data = get_admin_data()
    return render_template("home/admin_index.html",
                           segment='index', API_GENERATOR=len(API_GENERATOR),
                           page_data=page_data
                           )


@blueprint.route('/admin/users', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def admin_users():
    page_data = get_admin_data()
    users = Users.query.filter(Users.role != "admin").join(UserCredit, UserCredit.userid == Users.id, isouter=True).all()
    mailing_user_ids = [m.user_id for m in Mailing.query.with_entities(Mailing.user_id).all()]
    return render_template("home/admin_users.html",
                           segment='users', API_GENERATOR=len(API_GENERATOR),
                           page_data=page_data,
                           users=users,
                           mailing_user_ids=mailing_user_ids
                           )


@blueprint.route('/admin/users_credit', methods=['GET'])
@login_required
@role_required('admin')
def admin_users_credit():
    return render_template("home/admin_users_credit.html", segment='users_credit')


@blueprint.route('/admin/users_campaign_settings', methods=['GET'])
@login_required
@role_required('admin')
def admin_users_campaign_settings():
    return render_template("home/admin_users_campaign_settings.html", segment='users_campaign_settings')


@blueprint.route('/admin/get_users_credit', methods=['GET'])
@login_required
@role_required('admin')
def get_users_credit():
    # users = Users.query.filter(Users.role != "admin").join(UserCredit, UserCredit.userid == Users.id, isouter=False).all()

    users = db.session.query(Users, UserCredit).filter(Users.role == "lite", Users.state == "approved").join(UserCredit, Users.id == UserCredit.userid, isouter=False).all()
    user_list = []

    for user in users:
        user_data = {
            'id': user[0].id,
            'username': user[0].username,
            'email': user[0].email,
            'update_datetime': user[1].update_datetime,
            'credit': user[1].credit,
            'monthly_credit': user[1].monthly_credit,
            'available_credit': user[1].credit - Service.query.filter_by(user_id=user[0].id, is_credited=1).count(),
        }
        user_list.append(user_data)

    return jsonify(user_list)

@blueprint.route('/admin/update/credit', methods=['POST'])
@login_required 
@role_required('admin')
def update_credit():
    userid = request.form['userid']
    user_monthly_credit = int(request.form['user-monthly-credit'])
    user_bonus_credit = int(request.form['user-bonus-credit'])

    if userid:
        temp = UserCredit.query.filter(UserCredit.userid == userid).first()
        temp.monthly_credit = user_monthly_credit 
        temp.credit = temp.credit + user_bonus_credit

        credited_services = Service.query.filter_by(user_id = userid, is_credited = 1).count()

        if temp.credit + user_bonus_credit < credited_services:
            limit = credited_services - temp.credit - user_bonus_credit
            services = Service.query.filter_by(user_id = userid, is_credited = 1).limit(limit).all()
            for service in services:
                service.is_credited = 0
        
    db.session.commit()
    return redirect(url_for('home_blueprint.admin_users_credit'))
    

@blueprint.route('/admin/profile', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def admin_profile():
    return render_template("home/admin_profile.html",
                           segment='users', API_GENERATOR=len(API_GENERATOR),
                           )


@blueprint.route('/admin/users/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_user():
    userid = request.form['userid']
    user = Users.query.get(int(userid))
    if user:
        db.session.delete(user)
        Service.query.filter_by(user_id=userid).delete()
        Yelpurl.query.filter_by(userid=userid).delete()
        Uploadedservice.query.filter_by(user_id=userid).delete()
        Uploadedcontactfile.query.filter_by(user_id=userid).delete()
        Template.query.filter_by(userid=userid).delete()
        jobs = Automation.query.filter_by(userid=userid)
        for _ in jobs:
            jod_id = _.job_id
            Email.query.filter_by(job_id=jod_id).delete()
            db.session.delete(_)
            
        Action.query.filter_by(userid=userid).delete()
        Campaign.query.filter_by(userid=userid).delete()
        UserCredit.query.filter_by(userid=userid).delete()
        UserCampaignSetting.query.filter_by(userid=userid).delete()
        
        db.session.commit()
    return redirect(url_for("home_blueprint.admin_users"))

    
@blueprint.route('/admin/users/approve/<id>', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def approve_user(id):
    user = Users.query.get(id)
    user.state = "approved"
    db.session.commit()
    return redirect(url_for("home_blueprint.admin_users"))


@blueprint.route('/admin/users/reset', methods=['POST'])
@login_required
@role_required('admin')
def reset_nylas_token():
    userid = request.form['userid']
    user = Users.query.get(int(userid))
    user.nylas_access_token = None
    db.session.commit()
    
    return redirect(url_for("home_blueprint.admin_users"))
    
@blueprint.route('/admin/users/inactive/<id>', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def inactive_user(id):
    user = Users.query.get(id)
    user.state = "pending"
    db.session.commit()
    return redirect(url_for("home_blueprint.admin_users"))


@blueprint.route('/admin/users/upgrade/premium/<id>', methods=['GET'])
@login_required
@role_required('admin')
def upgrade_user_premium(id):
    user = Users.query.get(id)
    user.role = "premium"
    db.session.commit()
    return redirect(url_for("home_blueprint.admin_users"))

    
@blueprint.route('/admin/users/upgrade/lite/<id>', methods=['GET'])
@login_required
@role_required('admin')
def upgrade_user_lite(id):
    user = Users.query.get(id)
    user.role = "lite"

    user_initial_credit = 10

    user_credit = UserCredit.query.filter_by(userid=id).first()
    if user_credit:
        # User get 30 credits for lite plan
        user_credit.credit = user_initial_credit
    else:
        user_credit = UserCredit(userid=id, credit=user_initial_credit)
        db.session.add(user_credit)

    db.session.commit()
    return redirect(url_for("home_blueprint.admin_users"))


@blueprint.route('/admin/users/upgrade/normal/<id>', methods=['GET'])
@login_required
@role_required('admin')
def upgrade_user_normal(id):
    user = Users.query.get(id)
    user.role = "user"
    db.session.commit()
    return redirect(url_for("home_blueprint.admin_users"))


@blueprint.route('/admin/add/user', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def add_user():
    create_account_form = CreateAccountForm(request.form)
    if request.method == 'POST':
        # print(request.form)
        email = request.form['email'].lower()

        # Check email exists
        user = Users.query.filter_by(email=email).first()
        if user:
            return render_template('home/admin_add_user.html',
                                   msg='Email already registered',
                                   success=False,
                                   form=create_account_form,
                                   segment="add_user"
                                   )

        if create_account_form.validate():
            user = Users(**request.form)
            user.username = email
            user.role = "premium"
            user.state = "pending"
            db.session.add(user)
            db.session.flush()
            user_settings = UserCampaignSetting(userid=user.id)
            db.session.add(user_settings)
            db.session.commit()
            return redirect(url_for('home_blueprint.admin_users'))
        else:
            print(create_account_form.errors)
            return render_template('home/admin_add_user.html',
                                   msg=create_account_form.errors['password'][0],
                                   success=False,
                                   form=create_account_form,
                                   segment="add_user"
                                   )
    else:
        return render_template('home/admin_add_user.html',
                               form=create_account_form,
                               segment="add_user"
                               )
        
@blueprint.route('/admin/add/template', methods=['POST', 'GET'])
@login_required 
@role_required('admin')
def add_template():
    if request.method == 'POST':
        template_name = request.form['template-name']
        template_desc = request.form['template-description']
        tempid = request.form['tempid']
        
        if tempid:
            print("tempid", tempid)
            temp = Template.query.get(tempid)
            temp.template_name = template_name
            temp.template_desc = template_desc
            temp.userid = current_user.id
        else:
            template = Template(template_name=template_name, template_desc=template_desc)
            template.userid = current_user.id
            template.status = "draft"
            db.session.add(template)
            
        db.session.commit()
        return redirect(url_for('home_blueprint.add_template'))
    else:
        return render_template('home/admin_add_template.html', segment="templates" )

@csrf.exempt
@blueprint.route('/admin/update/template', methods=['POST'])
@login_required 
@role_required('admin')
def update_template():
    status = request.json['status']
    tempid = request.json['tempid']
    
    temp = Template.query.get(tempid)
    if status:
        temp.status = "publish"
    else:
        temp.status = 'draft'
    
    db.session.commit()
    return {'success': True}

@csrf.exempt
@blueprint.route('/update/workflowstatus', methods=['POST'])
@login_required 
@user_approved_required
def update_workflow_status():
    status = request.json['status']
    tempid = request.json['tempid']
    
    temp = Template.query.get(tempid)
    if status:
        temp.status = "publish"
    else:
        temp.status = 'draft'
    
    db.session.commit()
    return {'success': True}

        
@blueprint.route('/admin/templates', methods=['GET'])
@login_required
@role_required('admin')
def admin_templates():
    templates = Template.query.filter_by(userid=current_user.id).order_by(Template.create_datetime.desc()).all()
    temp_list = []

    for temp in templates:
        temp_data = {
            'id': temp.id,
            'template_name': temp.template_name,
            'template_desc': temp.template_desc,
            'status': temp.status,
            'create_datetime' : temp.create_datetime,
            'tempid' : temp.tempid,
            'userid' : current_user.id
        }
        temp_list.append(temp_data)
    return jsonify(temp_list)



@blueprint.route('/template/delete', methods=['POST'])
@login_required
@role_required('admin')
def template_delete():
    templateid = int(request.form['templateid'])
    temp = Template.query.get(templateid)
    db.session.delete(temp)
    Action.query.filter_by(tempid=templateid).delete()
    db.session.commit()
    return redirect(url_for('home_blueprint.add_template'))


@blueprint.route('/workflow/delete', methods=['POST'])
@login_required
@user_approved_required
def workflow_delete():
    templateid = request.form['workflowid']
    temp = Template.query.get(templateid)
    
    actions = Action.query.filter_by(tempid=templateid).all()
    for action in actions:
        automations = Automation.query.filter((Automation.action_id == action.id) & (Automation.status != "completed")).all()
        
        if len(automations) > 0:
            return {"success": False, "message": "This workflow is already used in automation."}
        
        db.session.delete(action)
    
    db.session.delete(temp)
    db.session.commit()
    
    return {"success": True, "message": "Workflow deleted successfully."}



@blueprint.route('/template/view/<tid>', methods=['GET'])
@login_required 
@role_required('admin')
def template_view(tid):
    temp =Template.query.filter_by(tempid = tid).first()
    template = {
        "name" : temp.template_name,
        "tempid" : temp.id,
        "tid" : temp.tempid
    }
    return render_template('home/admin_view_template.html',
                            template=template
                            )

@blueprint.route('/workflow/view/<tid>', methods=['GET'])
@login_required 
@user_approved_required
def workflow_view(tid):
    temp =Template.query.filter_by(tempid = tid).first()
    template = {
        "name" : temp.template_name,
        "tempid" : temp.id,
        "tid" : temp.tempid
    }
    return render_template('home/view_workflow.html',
                            template=template
                            )
    
    
@blueprint.route('/admin/add/action', methods=['POST', 'GET'])
@login_required 
@role_required('admin')
def add_action():
    if request.method == 'POST':
        # print(request.form)
        action_name = request.form['action-name']
        subject = request.form['subject']
        fromname = request.form['fromname']
        wait_days = request.form['wait-days']
        message = request.form['message']
        tempid = request.form['tempid']
        tid = request.form['tid']
        actionid = request.form['actionid']
        
        if actionid:
            action = Action.query.get(actionid)
            action.action_name = action_name
            action.subject = subject
            action.fromname = fromname
            action.message = message
            action.waitdays = wait_days
            
        else:
            action = Action()
            action.action_name = action_name
            action.subject = subject
            action.fromname = fromname
            action.message = message
            action.waitdays = wait_days
            action.tempid = tempid
            action.userid = current_user.id
            db.session.add(action)
            
        db.session.commit()
        return redirect(url_for('home_blueprint.template_view', tid=tid))


@blueprint.route('/add/action', methods=['POST', 'GET'])
@login_required 
@user_approved_required
def add_user_action():
    if request.method == 'POST':
        # print(request.form)
        action_name = request.form['action-name']
        subject = request.form['subject']
        fromname = request.form['fromname']
        wait_days = request.form['wait-days']
        message = request.form['message']
        tempid = request.form['tempid']
        tid = request.form['tid']
        actionid = request.form['actionid']
        
        if actionid:
            action = Action.query.get(actionid)
            action.action_name = action_name
            action.subject = subject
            action.fromname = fromname
            action.message = message
            action.waitdays = wait_days
            
        else:
            action = Action()
            action.action_name = action_name
            action.subject = subject
            action.fromname = fromname
            action.message = message
            action.waitdays = wait_days
            action.tempid = tempid
            action.userid = current_user.id
            db.session.add(action)
            
        db.session.commit()
        return redirect(url_for('home_blueprint.workflow_view', tid=tid))
    
        
@blueprint.route('/admin/actions/<id>', methods=['GET'])
@login_required
@role_required('admin')
def admin_actions(id):
    actions = Action.query.filter_by(tempid=int(id)).order_by(Action.waitdays.asc()).all()
    temp_list = []

    for action in actions:
        temp_data = {
            'id': action.id,
            'action_name': action.action_name,
            'subject': action.subject,
            'fromname': action.fromname,
            'message': action.message,
            'waitdays' : action.waitdays,
            'create_datetime' : action.create_datetime,
            'userid' : action.userid,
            'tempid' : action.tempid
        }
        temp_list.append(temp_data)
    return jsonify(temp_list)


        
@blueprint.route('/actions/<id>', methods=['GET'])
@login_required
@user_approved_required
def user_actions(id):
    actions = Action.query.filter_by(tempid=int(id)).order_by(Action.waitdays.asc()).all()
    temp_list = []

    for action in actions:
        temp_data = {
            'id': action.id,
            'action_name': action.action_name,
            'subject': action.subject,
            'fromname': action.fromname,
            'message': action.message,
            'waitdays' : action.waitdays,
            'create_datetime' : action.create_datetime,
            'userid' : action.userid,
            'tempid' : action.tempid
        }
        temp_list.append(temp_data)
    return jsonify(temp_list)

        
@blueprint.route('/admin/action/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_action_delete():
    actionid = int(request.form['actionid'])
    # tempid = int(request.form['tempid'])
    tid = request.form['tid']
    action = Action.query.get(actionid)
    db.session.delete(action)
    
    db.session.commit()
    return redirect(url_for('home_blueprint.template_view', tid=tid))


@blueprint.route('/action/delete', methods=['POST'])
@login_required
@user_approved_required
def action_delete():
    actionid = request.form['actionid']
    automations = Automation.query.filter((Automation.action_id == actionid) & (Automation.status != "completed")).all()
    
    if len(automations) > 0:
        return {"success": False, "message": "This action is already used in automation."}
    
    action = Action.query.get(actionid)
    db.session.delete(action)
    db.session.commit()
    return {"success": True, "message": "Action deleted successfully."}
    
       
@blueprint.route('/myworkflow', methods=['POST', 'GET'])
@login_required 
@user_approved_required
def my_workflow():
    if request.method == 'POST':
        template_name = request.form['template-name']
        template_desc = request.form['template-description']
        tempid = request.form['tempid']
        
        if tempid:
            # print("tempid", tempid)
            temp = Template.query.get(tempid)
            temp.template_name = template_name
            temp.template_desc = template_desc
            temp.userid = current_user.id
        else:
            template = Template(template_name=template_name, template_desc=template_desc)
            template.userid = current_user.id
            template.status = "draft"
            db.session.add(template)
            
        db.session.commit()
        return redirect(url_for('home_blueprint.add_template'))
    else:
        
        return render_template('home/my_workflow.html', segment="myworkflow")


@blueprint.route('/templates', methods=['GET'])
@login_required
@user_approved_required
def get_templates():
    
    admin = Users.query.filter_by(role='admin').first()
    admin_id = admin.id
    
    templates = Template.query.filter_by(status="publish", userid=admin_id).order_by(Template.create_datetime.desc()).all()
    temp_list = []

    for temp in templates:
        temp_data = {
            'id': temp.id,
            'template_name': temp.template_name,
            'template_desc': temp.template_desc,
            'status': temp.status,
            'create_datetime' : temp.create_datetime,
            'userid' : current_user.id
        }
        temp_list.append(temp_data)
    return jsonify(temp_list)

@csrf.exempt
@blueprint.route('/get_workflows', methods=['GET', 'POST'])
@login_required
@user_approved_required
def get_users_workflow():
    userid = current_user.id
    
    temp_list = []
    if request.method == "GET":
        templates = Template.query.filter_by(userid=userid).order_by(Template.create_datetime.desc()).all()
        for temp in templates:
            temp_data = {
                'id': temp.id,
                'template_name': temp.template_name,
                'template_desc': temp.template_desc,
                'status': temp.status,
                'create_datetime' : temp.create_datetime,
                'tid' : temp.tempid,
                'userid' : current_user.id
            }
            temp_list.append(temp_data)
            
        return jsonify(temp_list)
    
    else:
        templates = Template.query.filter_by(userid=userid, status="publish").order_by(Template.create_datetime.asc()).all()
        contacts = Uploadedcontactfile.query.filter_by(user_id=userid).order_by(Uploadedcontactfile.create_datetime.desc()).all()
        
        temp_list = []
        contacts_list = []
        
        for temp in templates:
            temp_data = {
                'id': temp.id,
                'template_name': temp.template_name,
                'template_desc': temp.template_desc,
                'status': temp.status,
                'create_datetime' : temp.create_datetime,
                'tid' : temp.tempid,
                'userid' : current_user.id
            }
            temp_list.append(temp_data)
        
        for temp in contacts:
            # Get all emails in contact file

            count = Uploadedservice.query.filter_by(file_id=temp.id).count()

            temp_data = {
                'id': temp.id,
                'description': temp.description,
                'create_datetime' : temp.create_datetime,
                'service_count' : count
            }
            contacts_list.append(temp_data)

        user_settings = UserCampaignSetting.query.filter_by(userid=userid).first()
        emails_daily_limit = user_settings.emails_daily_limit
            
        data = {
            "templates" : temp_list,
            "contacts" : contacts_list,
            "emails_daily_limit" : emails_daily_limit
        }
        
        return jsonify(data)
    
@csrf.exempt
@blueprint.route('/api/template/create', methods=['POST'])
@login_required
@user_approved_required
def api_template_create():
    new_workflow = Template()
    new_workflow.template_name = "SHM AI Template"
    new_workflow.template_desc = "AI generated template"
    new_workflow.userid = current_user.id
    new_workflow.status = "draft"
    db.session.add(new_workflow)
    db.session.commit()

    data = {
        'tempid': new_workflow.id
    }
    
    return jsonify(data)

@csrf.exempt
@blueprint.route('/api/action/create', methods=['POST'])
@login_required
@user_approved_required
def api_action_create():
    action_name = request.json['action-name']
    subject = request.json['subject']
    fromname = request.json['fromname']
    wait_days = request.json['wait-days']
    message = request.json['message']
    tempid = request.json['tempid']

    action = Action()
    action.action_name = action_name
    action.subject = subject
    action.fromname = fromname
    action.message = message.replace('{{firstname}},', '{{firstname}}')
    action.waitdays = wait_days
    action.tempid = tempid
    action.userid = current_user.id
    db.session.add(action)
        
    db.session.commit()

    data = {
        'actionid': action.id
    }
    
    return jsonify(data)

@blueprint.route('/import/workflow', methods=['POST'])
@login_required
@user_approved_required
def import_users_workflow():
    tempid = request.form['select-template']
    template = Template.query.filter_by(id=tempid).first()
    
    new_workflow = Template()
    new_workflow.template_name = template.template_name
    new_workflow.template_desc = template.template_desc
    new_workflow.userid = current_user.id
    new_workflow.status = "draft"
    db.session.add(new_workflow)
    db.session.flush()
    
    new_temp_id = new_workflow.id
    
    new_actions = []
    actions = Action.query.filter_by(tempid=tempid).all()
    for at in actions:
        action = Action()
        action.action_name = at.action_name
        action.subject = at.subject
        action.fromname = at.fromname
        action.message = at.message
        action.waitdays = at.waitdays
        action.tempid = new_temp_id
        action.userid = current_user.id
        new_actions.append(action)
    
    bulk_save_with_retry(new_actions, batch_size=100)
    return redirect(url_for('home_blueprint.my_workflow'))


@blueprint.route('/update/workflow', methods=['POST'])
@login_required 
@user_approved_required
def update_workflow():
    template_name = request.form['workflow-name']
    template_desc = request.form['workflow-description']
    tempid = request.form['workflow_id']
    
    if tempid:
        temp = Template.query.get(tempid)
        temp.template_name = template_name
        temp.template_desc = template_desc
    else:
        template = Template(template_name=template_name, template_desc=template_desc)
        template.userid = current_user.id
        template.status = "draft"
        db.session.add(template)
        
    db.session.commit()
    return redirect(url_for('home_blueprint.my_workflow'))

@blueprint.route('/api/check-auth')
@login_required
def check_auth():
    """Endpoint for Node.js to check if user is authenticated"""
    return jsonify({
        'authenticated': True,
        'user': current_user.email
    })
    
@csrf.exempt
@blueprint.route('/admin/action/test', methods=['POST'])
@login_required 
@role_required('admin')
def admin_action_test():
    
    actionid = request.json['id']
    action = Action.query.filter_by(id=actionid).first()
    
    test_service = {
        "venue" : "Servcie Name",
        "unsubscribe_link" : "unsubscribe_link_test",
        "firstname" : "firstname",
        "customtext" : "customtext",
        "originalemail" : "originalemail"
    }
    
    SENDER_MAIL = os.getenv('SENDER_MAIL')
    
    jinja_temp = JT(action.message)
    mail_body = jinja_temp.render(test_service)
    
    if send_test_email(action.subject , action.fromname, mail_body, SENDER_MAIL, SENDER_MAIL):
        return {"success": True}
    
    else:
        return {"success": False}
    

@blueprint.route('/cancel_membership')
@login_required
def cancel_membership():
    
    if send_cancel_membership_email(current_user.email):
        return "Cancellation request sent successfully. We will contact you soon."
    
    else:
        return "Failed to send request. Please try again later."

    
@csrf.exempt
@blueprint.route('/action/test', methods=['POST'])
# @login_required 
# @user_approved_required
def action_test():
    actionid = request.json['id']
    action = Action.query.filter_by(id=actionid).first()
    
    test_service = {
        "venue" : "Servcie Name",
        "unsubscribe_link" : "unsubscribe_link_test",
        "firstname" : "firstname",
        "customtext" : "customtext",
        "originalemail" : "originalemail"
    }
    
    SENDER_MAIL = os.getenv('SENDER_MAIL')
    
    jinja_temp = JT(action.message)
    mail_body = jinja_temp.render(test_service)

    if send_email_via_nylas(nylas, action.subject, 'Service Name', SENDER_MAIL, action.fromname, mail_body, current_user.email, current_user.nylas_access_token):
        return {"success": True}
    
    else:
        return {"success": False}
    
#     try:
#         # jinja_temp = JT(action.message)
#         # mail_body = jinja_temp.render(test_service)
        
#         # grant_id = current_user.nylas_access_token
#         # mailings=Mailing.query.filter_by(user_id='517').first()
#         # response1= send_email_via_unimail(mailings, 'subject', 'venue', 'aamirbashir.ahangar@gmail.com', 'fromname', "Test email Body", 'aamirdev10@gmail.com', 'grant_id')
#         # if not grant_id:
#         #     WEB_HOST_IP = os.getenv("WEB_HOST_IP")
#         #     subject = "Failed to test email"
#         #     body = f'''<p> Please click the link below to connect your email.</p>
#         #                 <a href="{WEB_HOST_IP}/connect_email" style="color: #1a73e8; text-decoration: none;">Connect Email</a>
#         #             </p>'''
#         #     send_email_via_mailtrap(subject , "Robotic Booking Agent", body,  current_user.email)
            
#         #     return {"success": False, "message": body}
        
#         # send_email_via_unimail(nylas, action.subject , "Servcie Name",  current_user.email, action.fromname,  mail_body, receiver, grant_id)
# #         html=f"""
# #             <html>
# #   <body>
# #     <p>Hi John,</p>

# #     <p>
# #       Thanks for signing up! Please check the details below.
# #     </p>

# #     <p>
# #       <a href="https://6746496e4ff8.ngrok-free.app/click/12345?redirect=https://6746496e4ff8.ngrok-free.app/welcome">
# #         Click here to view your dashboard
# #       </a>
# #     </p>

# #     <!-- Tracking Pixel -->
# #     <img src="https://beunimail.raybitprojects.com/open/1988c41613029dfa.png" 
# #          width="100" height="100" 
# #          style="" 
# #          alt="" />
# #   </body>
# # </html>
# #         """
# #         url = "https://beunimail.raybitprojects.com/send-email"
# #         payload = {
# #             "id": '517',
# #             "to": 'huzuhuzair@gmail.com',
# #             "subject": "Test",
# #             "message": html,
# #             "message_id":'1212'
# #         }

#         try:
#             response = requests.post(url, json=payload)
#             print(response.json())
#             response.raise_for_status()
#             json_data = response.json()

#             # Wrap into objects for dot notation
#             # data_obj = SimpleNamespace(id='1212')
#             # response_obj = SimpleNamespace(
#             #     success=json_data.get("success", False),
#             #     message=json_data.get("message", ""),
#             #     data=data_obj
#             # )
#             return {"success": json_data}
#         except requests.exceptions.RequestException as e:
#             print(f"Failed to send email: {e}")
#             return {"fail": e}
        
#     except Exception as e:
#         print(repr(e))
#         if "No Grant found for this Grant ID." in str(e) or "Grant not found for given ID/Email" in str(e) or 'expired' in str(e).lower():
#             # Reset nylas token to none
#             current_user.nylas_access_token = None
#             db.session.commit()
#             return {"success": False, "message": "Please connect your email account."}
        
#         elif "Connection aborted" in str(e):
#             return {"success": False, "message": "Failed. Please try again later."}
        
#         else:
#             return {"success": False, "message": str(e)}
            
@csrf.exempt
@blueprint.route('/action/get', methods=['POST'])
@login_required 
@user_approved_required
def get_action():
    actionid = request.json['id']
    action = Action.query.filter_by(id=actionid).first()

    action_data = {
        "id" : action.id,
        "action_name" : action.action_name,
        "subject" : action.subject,
        "fromname" : action.fromname,
        "message" : action.message,
        "waitdays" : action.waitdays
    }

    return jsonify(action_data)

@blueprint.route("/track.gif/<string:message_id>", methods=["GET"])
def track_email_open(message_id):
    email = Email.query.filter_by(mail_id=message_id).first()
    if email and email.is_opened == 0:
        email.is_opened = 1
        db.session.commit()

    # Return a 1x1 transparent GIF
    gif = b'R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='
    return Response(base64.b64decode(gif), mimetype='image/gif')
   
@csrf.exempt
@blueprint.route('/webhooks', methods=['POST', "GET"])
def webhook():
    if request.method == "GET" : 
        # Verify webhooks on nylas settings 
        if "challenge" in request.args:
            return request.args['challenge']
        else:
            return "no challenge"
    
    else:
        try:
            event_type = request.json['type']
        except:
            pprint.pprint(request.json)
            return "OK"
        
        if event_type == 'message.bounce_detected':
            message_id = request.json['data']['object']['origin']['id']
            email = Email.query.filter_by(mail_id=message_id).first()
            if email:
                # unsubscribe the email
                unsub_token = email.unsubscribe_token
                if unsub_token:
                    emails = Email.query.filter_by(unsubscribe_token=unsub_token).all()
                    for email in emails:
                        email.is_unsubscribed = 1
                        email.is_bounced = 1
                        db.session.commit()
                    
                    service = Uploadedservice.query.filter_by(unsubscribe_token=unsub_token).first()
                    if service:
                        service.is_unsubscribed = 1
                        service.is_bad = 1
                        db.session.commit()

        elif event_type == 'grant.deleted' or event_type == 'grant.expired':
            grant_id = request.json['data']['object']['grant_id']
            user = Users.query.filter_by(nylas_access_token=grant_id).first()

            if user:
                user.nylas_access_token = None
                db.session.commit()

        if event_type == "message.opened":
            grant_id = request.json['data']['object']['grant_id']
            message_id = request.json['data']['object']['message_id']

            email = Email.query.filter_by(mail_id=message_id).first()
            if email:
                email.is_opened = 1
                db.session.commit()
            
        elif event_type == "thread.replied":
            grant_id = request.json['data']['object']['grant_id']
            message_id = request.json['data']['object']['thread_id']
            email = Email.query.filter_by(mail_id=message_id).first()

            if email:
                # pprint.pprint(request.json)

                print("Email replied", email.email, message_id)
                email.is_replied = 1
                db.session.commit()
                
                service = Uploadedservice.query.filter_by(unsubscribe_token=email.unsubscribe_token).first()
                # unsubscribe the email
                if service is None:
                    print("No service found")
                    return "OK"
                
                # Get user id
                user_id = service.user_id
                user = Users.query.get(user_id)

                if user.is_auto_unsub:
                    service.is_unsubscribed = 1
                    db.session.commit()
                
                    # update associated email
                    emails = Email.query.filter_by(unsubscribe_token=email.unsubscribe_token).all()
                    for email in emails:
                        email.is_unsubscribed = 1
                        db.session.commit()
                        
                    service = Uploadedservice.query.filter_by(unsubscribe_token=email.unsubscribe_token).first()
                    
                    # unsubscribe all emails from this business : same business
                    if service:
                        service.is_unsubscribed = 1
                        address = service.address
                        biz_id = service.biz_id

                        if biz_id:
                            # Unsubscribe all emails from this business : same business
                            services = Uploadedservice.query.filter_by(user_id = user_id, biz_id=biz_id).all()
                            for service in services:
                                # Unsubscribe all service with this business
                                service.is_unsubscribed = 1
                                
                                # Unsubscribe all emails from campaigns
                                unsubscribe_token = service.unsubscribe_token
                                email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                                if email:
                                    print("unsubscribed", email.email)
                                    email.is_unsubscribed = 1
                                db.session.commit()
                                
                        elif address:
                            # Unsubscribe all emails from this address : same business
                            services = Uploadedservice.query.filter_by(user_id = user_id, address=address).all()
                            for service in services:
                                # Unsubscribe all service with this address
                                service.is_unsubscribed = 1
                                
                                # Unsubscribe all emails from campaigns
                                unsubscribe_token = service.unsubscribe_token
                                email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                                if email:
                                    print("unsubscribed", email.email)
                                    email.is_unsubscribed = 1

                                db.session.commit()
                        else:
                            phone = service.phone
                            if phone:
                                # Unsubscribe all emails from this phone : same business
                                services = Uploadedservice.query.filter_by(user_id = user_id, phone=phone).all()
                                for service in services:
                                    # Unsubscribe all service with this phone
                                    service.is_unsubscribed = 1
                                    
                                    # Unsubscribe all emails from campaigns
                                    unsubscribe_token = service.unsubscribe_token
                                    email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                                    if email:
                                        print("unsubscribed", email.email)
                                        email.is_unsubscribed = 1
                                    db.session.commit()
                                    
                            else:
                                venue = service.name
                                if venue:
                                    # Unsubscribe all emails from this venue : same business
                                    services = Uploadedservice.query.filter_by(user_id = user_id, name=venue).all()
                                    for service in services:
                                        # Unsubscribe all service with this venue
                                        service.is_unsubscribed = 1
                                        
                                        # Unsubscribe all emails from campaigns
                                        unsubscribe_token = service.unsubscribe_token
                                        email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                                        if email:
                                            print("unsubscribed", email.email)
                                            email.is_unsubscribed = 1

                                        db.session.commit()
                                        
                user_id = service.user_id

                # Create reminder after 7 days at 2pm
                current_time = datetime.datetime.now() # RBS Server time is UTC timezone
                utc_time = pytz.utc.localize(current_time)
                est = pytz.timezone('US/Eastern')
                est_time = utc_time.astimezone(est)
                reminder_est_time = est_time + timedelta(days=7) 
                reminder_est_time = reminder_est_time.replace(hour=14, minute=0, second=0)

                # convert est time to utc time
                reminder_utc_time = reminder_est_time.astimezone(pytz.utc)
                utc_time_iso_string = reminder_utc_time.strftime('%Y-%m-%d %H:%M:%S')

                reminder = Reminder.query.filter_by(userid=user_id, email=email.email).first()

                if reminder:
                    job_id = reminder.job_id
                    if scheduler.get_job(job_id):
                        scheduler.remove_job(job_id)

                    db.session.delete(reminder)
                    db.session.commit()
                
                job_id = "job_" + generate_job_id(32)
                job = {
                    "id" : job_id,
                    'trigger' : 'date',
                    "run_date" : utc_time_iso_string,
                    "func" : "jobs:job_push_notification_reminder",
                    "args" : (job_id, user_id)
                }
                try:
                    scheduler.add_job(**job) # TODO: Uncomment this line
                    print("Auto created job for reminder", job_id)
                except Exception as e:
                    print("Failed to create job", str(e))
                    return {"success": False, "message": "Something went wrong. Please try again."}
                
                reminder_template = "Follow up w/ [name] @ [venue] **See email from [email] [phone]"
                reminder = Reminder()
                reminder.job_id = job_id
                reminder.note = ''
                reminder.name = service.firstname
                reminder.email = email.email
                reminder.phone = service.phone
                reminder.venue = service.name
                reminder.title = f"Follow up w/ {service.firstname} @ {service.name} **See email from {email.email} {service.phone}"
                reminder.note_template = reminder_template
                reminder.reminder_time = utc_time_iso_string  
                reminder.status = "active"
                reminder.userid = user_id
                db.session.add(reminder)
                db.session.commit()

        # reply with 200 status code
        return "OK"


# Get all services  from uploadedservice table for the user , ignore duplicate emails and unsubscribed emails
@blueprint.route('/services', methods=['GET'])
@login_required
@user_approved_required
def get_services():
    services = Uploadedservice.query.filter_by(user_id=current_user.id).all()
    service_list = []

    for service in services:
        service_data = {
            'id': service.id,
            'name': service.name,
            'email': service.email,
            'phone': service.phone,
        }
        service_list.append(service_data)

    return jsonify(service_list)

   
@blueprint.route('/automation', methods=['POST', 'GET'])
@login_required 
@user_approved_required
def automation():
    if request.method == 'POST':
        template_name = request.form['template-name']
        template_desc = request.form['template-description']
        tempid = request.form['tempid']
        
        if tempid:
            # print("tempid", tempid)
            temp = Template.query.get(tempid)
            temp.template_name = template_name
            temp.template_desc = template_desc
            temp.userid = current_user.id
        else:
            template = Template(template_name=template_name, template_desc=template_desc)
            template.userid = current_user.id
            template.status = "draft"
            db.session.add(template)
            
        db.session.commit()
        return redirect(url_for('home_blueprint.add_template'))
    else:
        
        return render_template('home/automation.html', segment="campaigns")
    
  
@blueprint.route('/campaigns', methods=['POST', 'GET']) 
@login_required 
@user_approved_required
def campaigns():
    if request.method == 'POST':
        template_name = request.form['template-name']
        template_desc = request.form['template-description']
        tempid = request.form['tempid']
        
        if tempid:
            # print("tempid", tempid)
            temp = Template.query.get(tempid)
            temp.template_name = template_name
            temp.template_desc = template_desc
            temp.userid = current_user.id
        else:
            template = Template(template_name=template_name, template_desc=template_desc)
            template.userid = current_user.id
            template.status = "draft"
            db.session.add(template)
            
        db.session.commit()
        return redirect(url_for('home_blueprint.add_template'))
    else:
        mailings=Mailing.query.filter_by(user_id=current_user.id).first()
        return render_template('home/campaigns.html', segment="campaigns",mailings=mailings)
    
@csrf.exempt
@blueprint.route('/create/campaign', methods=['POST'])
@login_required 
@user_approved_required
def create_campaign():
    
    workflow_id = request.json['workflow_id']
    contactfile_id = request.json['contactfile_id']
    max_emails_per_day = request.json['max_emails_per_day']
    # is_round_robin = request.json['is_round_robin']
    
    # print("is_round_robin", is_round_robin)
    # number of emails in a Group is 150 , so we need to divide emails into groups
    group_size = int(max_emails_per_day)
    
    # automations = Automation.query.filter( (Automation.userid == current_user.id), (Automation.status != "completed")).all()
    # if len(automations) > 0:
    #     print("There is an automation running")
    #     return {"success": False, "message": "There is an automation running. Please wait until it is completed."}
    
    actions = Action.query.filter_by(tempid=workflow_id).order_by(Action.waitdays.asc()).all()
    if len(actions) == 0:
        print("No actions")
        return {"success": False, "message": "There is no actions registered in this workflow. It should have at least one action."}
    
    services = Uploadedservice.query.filter_by(user_id=current_user.id, is_unsubscribed=0, file_id=contactfile_id).all()
    if len(services) == 0:
        print("No contacts")
        return {"success": False, "message": "There is no contacts uploaded. Please upload contacts first."}
    
    template = Template.query.get(workflow_id)
    template_name = template.template_name
    
    contactfile = Uploadedcontactfile.query.get(contactfile_id)
    contactfile_name = contactfile.description
        
    group_count =  len(services) // group_size if len(services) % group_size == 0 else len(services) // group_size + 1

    # calculate the group size for week days

    emails = []
    groups = []
    campaignid = generate_job_id(32)
    
    # A group is a job here
    for action in actions:
            
        for groupid in range(group_count):
            group = Automation()
            group.group_number = groupid
            group.action_id = action.id
            group.group_count = group_count
            group.action_name = action.action_name
            group.job_id = "job_" + generate_job_id(32)
            group.userid = action.userid
            group.status = "pending"
            group.campaignid = campaignid
            
            # First Job start time is waitdays + 1 minutes
            job_starttime = datetime.datetime.now() + timedelta(days=int(action.waitdays) + int(groupid), minutes=1)
            job_start_utctime = datetime.datetime.utcnow() + timedelta(days=int(action.waitdays) + int(groupid), minutes=1)
            group.action_datetime = job_start_utctime
            
            job = {
                "id" : group.job_id,
                'trigger' : 'date',
                "run_date" : job_starttime.strftime("%Y-%m-%d %H:%M:%S"),
                "func" : "jobs:email_automation_job",
                "args" : (nylas, action.id, group.job_id, current_user.email,current_user.id)
            }
            try:
                scheduler.add_job(**job) # TODO: Uncomment this line
                print("created job", group.job_id)
            except Exception as e:
                print("Failed to create job", str(e))
                return {"success": False, "message": "Something went wrong. Please try again."}
            
            groups.append(group)
            
            for service in services[groupid*group_size : (groupid+1)*group_size]:
                email = Email()
                email.email = service.email
                email.venue = service.name
                email.job_id = group.job_id
                email.unsubscribe_token = service.unsubscribe_token
                email.firstname = service.firstname
                email.customtext = service.customtext
                email.originalemail = service.originalemail
                emails.append(email)
    
    campaign = Campaign()
    campaign.contact_name = contactfile_name
    campaign.templatename = template_name
    campaign.campaignid = campaignid
    campaign.userid = current_user.id
    
    with db_transaction() as session:
        session.add(campaign)
        bulk_save_with_retry(groups, batch_size=100)
        bulk_save_with_retry(emails, batch_size=100)
    
    return {"success": True, "message": "Campaign created successfully. It will start on the scheduled time."}


@blueprint.route('/get_campaigns', methods=['GET'])
@login_required
@user_approved_required
def get_campaigns():
    userid = current_user.id
    campaigns = Campaign.query.filter(Campaign.userid == userid, or_(Campaign.is_archived == None, Campaign.is_archived == 0)).order_by(Campaign.create_datetime.desc()).all()
    temp_list = []

    for temp in campaigns:
        temp_data = {
            'id': temp.id,
            'campaignid': temp.campaignid,
            'contact_name': temp.contact_name,
            'templatename': temp.templatename,
            'create_datetime' : temp.create_datetime,
        }
        temp_list.append(temp_data)
        
    return jsonify(temp_list)

@blueprint.route('/get_archived_campaigns', methods=['GET'])
@login_required
@user_approved_required
def get_archived_campaigns():
    userid = current_user.id
    campaigns = Campaign.query.filter(Campaign.userid == userid, Campaign.is_archived == 1).order_by(Campaign.create_datetime.desc()).all()
    temp_list = []

    for temp in campaigns:
        temp_data = {
            'id': temp.id,
            'campaignid': temp.campaignid,
            'contact_name': temp.contact_name,
            'templatename': temp.templatename,
            'create_datetime' : temp.create_datetime,
        }
        temp_list.append(temp_data)
        
    return jsonify(temp_list)


@blueprint.route('/get_automations/<campaignid>', methods=['GET'])
@login_required
@user_approved_required
def get_automations(campaignid):
    userid = current_user.id
    # print('get_automations', campaignid)
    automations = Automation.query.filter(Automation.userid==userid, Automation.campaignid==campaignid).all()
    temp_list = []

    for temp in automations:
        temp_data = {
            'id': temp.id,
            'action_name': temp.action_name,
            'group_number': temp.group_number,
            'group_count': temp.group_count,
            'action_datetime' : temp.action_datetime,
            'job_id' : temp.job_id,
            'status' : temp.status
        }
        temp_list.append(temp_data)
        
    return jsonify(temp_list)


# get archived automations
@blueprint.route('/get_archived_automations', methods=['GET']) 
@login_required
@user_approved_required
def get_archived_automations():
    userid = current_user.id
    automations = Automation.query.filter(Automation.userid==userid, Automation.is_archived == True).all()
    temp_list = []

    for temp in automations:
        temp_data = {
            'id': temp.id,
            'action_name': temp.action_name,
            'group_number': temp.group_number,
            'group_count': temp.group_count,
            'action_datetime' : temp.action_datetime,
            'job_id' : temp.job_id,
            'status' : temp.status
        }
        temp_list.append(temp_data)

    return jsonify(temp_list)


@blueprint.route('/campaign/delete', methods=['POST'])
@login_required 
@user_approved_required
def camp_delete():
    id = request.form['campid']
    camp = Campaign.query.get(id)
    
    if camp:
        campid = camp.campaignid
        db.session.delete(camp)
        db.session.commit()
    
    if campid is None:
        return {"success": False, 'message': "Campaign not found."}
        
    automations = Automation.query.filter_by(campaignid=campid).all()
    
    for automation in automations:
        jobid = automation.job_id
        db.session.delete(automation)
        Email.query.filter_by(job_id=jobid).delete()
        db.session.commit()
        
        if scheduler.get_job(jobid):
            scheduler.remove_job(jobid)
        
    return {"success": True, 'message': "Campaign deleted successfully."}

@blueprint.route('/campaign/archive', methods=['POST'])
@login_required 
@user_approved_required
def camp_archive():
    id = request.form['campid']
    camp = Campaign.query.get(id)
    
    if camp:
        campid = camp.campaignid
        camp.is_archived = 1
        db.session.commit()
    
    if campid is None:
        return {"success": False, 'message': "Campaign not found."}
        
    automations = Automation.query.filter_by(campaignid=campid).all()
    
    for automation in automations:
        jobid = automation.job_id
        automation.is_archived = 1
        db.session.commit()
        
        if scheduler.get_job(jobid):
            scheduler.remove_job(jobid)

    return {"success": True, 'message': "Campaign archived successfully."}

@csrf.exempt
@blueprint.route('/automation/delete', methods=['POST'])
@login_required 
@user_approved_required
def job_delete():
    jobid = request.json['jobid']
    job = Automation.query.filter_by(job_id=jobid).first()
    
    if job:
        db.session.delete(job)
    
    Email.query.filter_by(job_id=jobid).delete()
    
    if scheduler.get_job(jobid):
        scheduler.remove_job(jobid)
        
    db.session.commit()
    return {"success": True, 'message': "Job deleted successfully."}


@csrf.exempt
@blueprint.route('/automation/archive', methods=['POST'])
@login_required 
@user_approved_required
def job_archive():
    jobid = request.json['jobid']
    job = Automation.query.filter_by(job_id=jobid).first()
    
    if job:
        job.is_archived = True
        db.session.commit()
    
    Email.query.filter_by(job_id=jobid).update({"is_archived": True})
    
    if scheduler.get_job(jobid):
        scheduler.remove_job(jobid)
        
    db.session.commit()
    return {"success": True, 'message': "Job deleted successfully."}



@csrf.exempt
@blueprint.route('/automation/retry', methods=['POST'])
@login_required 
@user_approved_required
def job_retry():
    try:
        campaignid = request.json['campaignid']
        # get all failed automations, joining Action by action_id
        failed_job = (
            db.session.query(Automation, Action)
            .join(Action, Automation.action_id == Action.id)
            .filter(Automation.campaignid == campaignid, Automation.status == "failed")
            .order_by(Automation.id)
            .first()
        )

        if failed_job is None:
            return {"success": False, "message": "No failed job found."}

        # first_failed_job_time = failed_job.action_datetime
        first_failed_job_id = failed_job.Automation.id
        pending_or_failed_automations = (
            db.session.query(Automation, Action)
            .join(Action, Automation.action_id == Action.id)
            .filter(Automation.campaignid == campaignid, Automation.id >= first_failed_job_id)
            .all()
        )

        for record in pending_or_failed_automations:
            automation = record.Automation
            action = record.Action
            # If job is completed or running, then skip
            if automation.status == "completed" or automation.status == "running":
                continue

            # print(automation.action_datetime)

            jobid = automation.job_id
            # days_diff = (automation.action_datetime - first_failed_job_time).days
            days_diff = automation.group_number + action.waitdays - failed_job.Automation.group_number - failed_job.Action.waitdays

            # print("days_diff", days_diff)   

            if automation.status == "failed":
                automation.status = "pending"  
                db.session.commit()
        
            job_starttime = datetime.datetime.now() + timedelta(days=days_diff, seconds=30)
            job_start_utctime = datetime.datetime.now(timezone.utc) + timedelta(days=days_diff, seconds=30)
            automation.action_datetime = job_start_utctime

            action_id = automation.action_id

            # delete job from scheduler if exist
            if scheduler.get_job(jobid):
                scheduler.remove_job(jobid)

            job = {
                "id" : jobid,
                'trigger' : 'date',
                "run_date" : job_starttime.strftime("%Y-%m-%d %H:%M:%S"),
                "func" : "jobs:email_automation_job",
                "args" : (nylas, action_id, jobid, current_user.email, current_user.id)
            }
            
            try:
                scheduler.add_job(**job) # TODO: Uncomment this line
                print("created job again", jobid)
            except Exception as e:
                print("Failed to create job", str(e))
                return {"success": False, "message": "Something went wrong. Please try again."}
            
            db.session.commit()

        return {"success": True, 'message': "Job rescheduled successfully."}
    
    except Exception as e:
        print(repr(e))
        return {"success": False, "message": "Something went wrong. Please try again."}


@csrf.exempt
@blueprint.route('/automation/force-fail', methods=['POST'])
@login_required 
@user_approved_required
def job_force_fail():
    try:
        campaignid = request.json['campaignid']
        first_pending_job = Automation.query.filter_by(campaignid=campaignid, status="pending").order_by(Automation.id).first()
        
        if first_pending_job is None:
            return {"success": False, "message": "No pending job found."}
        
        first_pending_job.status = "failed"
        db.session.commit()

        # delete job from scheduler if exist
        jobid = first_pending_job.job_id
        if scheduler.get_job(jobid):
            scheduler.remove_job(jobid)

        return {"success": True, 'message': "Job force failed successfully."}
    except Exception as e:
        print(repr(e))
        return {"success": False, "message": "Something went wrong. Please try again."}


@blueprint.route('/campaign/view/<campaignid>', methods=['GET'])
@login_required 
@user_approved_required
def campaign_view(campaignid):
    # print("campaignid", campaignid)
    return render_template('home/view_campaign.html', campaignid=campaignid )


@blueprint.route('/automation/view/<jobid>', methods=['GET'])
@login_required 
@user_approved_required
def automation_view(jobid):
    automation =Automation.query.filter_by(job_id = jobid).first()
    job = {
        "name" : automation.action_name,
        "jobid" : automation.job_id,
    }
    return render_template('home/view_automation.html', job=job )
    

@blueprint.route('/emails/<jobid>', methods=['GET'])
@login_required
def get_emails(jobid):
    emails = Email.query.filter(Email.job_id==jobid, or_(Email.is_archived == False , Email.is_archived == None)).all()
    temp_list = []

    for email in emails:
        
        temp_data = {
            'id': email.id,
            'email': email.email,
            'is_sent': email.is_sent,
            'is_opened': email.is_opened,
            'is_unsubscribed' : email.is_unsubscribed,
            'is_replied' : email.is_replied,
            'is_bounced' : email.is_bounced,
            'updated_datetime' : email.updated_datetime,
            'unsubscribe_token' : email.unsubscribe_token,
            'mail_id' : email.mail_id,
        }
        temp_list.append(temp_data)
        
    return jsonify(temp_list)

# /emails/archived'
@blueprint.route('/emails/archived', methods=['GET'])
@login_required
def get_archived_emails():

    user_id = current_user.id
    jobs = Automation.query.filter(Automation.userid == user_id).all()

    temp_list = []
    for job in jobs:
        job_id = job.job_id
        job_name = job.action_name
        emails = Email.query.filter(Email.is_archived == True).all()

        for email in emails:
            temp_data = {
                'id': email.id,
                'email': email.email,
                'is_sent': email.is_sent,
                'is_opened': email.is_opened,
                'is_unsubscribed' : email.is_unsubscribed,
                'is_replied' : email.is_replied,
                'is_bounced' : email.is_bounced,
                'updated_datetime' : email.updated_datetime,
                'unsubscribe_token' : email.unsubscribe_token,
                'mail_id' : email.mail_id,
                'job_id' : job_id,
                'job_name' : job_name,
            }
            temp_list.append(temp_data)
        
    return jsonify(temp_list)


@blueprint.route('/us/choose', methods=['GET'])
def unsubscribe_choose():
    id = request.args.get('_id')
    token = request.args.get('token')
    WEB_HOST_IP = os.getenv("WEB_HOST_IP")
    return render_template('home/unsubscribe_choose.html', token=token, domain=WEB_HOST_IP, id=id)

@blueprint.route('/unsubscribe/choose', methods=['GET'])
def unsub_choose():
    # redirect to unsubscribe_choose
    token = request.args.get('token')
    id = request.args.get('_id')
    return redirect(url_for('home_blueprint.unsubscribe_choose', token=token, _id=id))


@blueprint.route('/unsubscribe/all', methods=['GET'])
def unsub_all():
    # redirect to unsubscribe_all
    token = request.args.get('token')
    id = request.args.get('_id')
    return redirect(url_for('home_blueprint.unsubscribe_all', token=token, _id=id))

@blueprint.route('/us/all', methods=['GET'])
def unsubscribe_all():

    token = request.args.get('token')
    id = request.args.get('_id')

    emails = Email.query.filter_by(unsubscribe_token=token).all()
    service = Uploadedservice.query.filter_by(unsubscribe_token=token).first()
    
    try:
        for email in emails:
            email.is_unsubscribed = 1
            db.session.commit()
        
        if service:
            service.is_unsubscribed = 1
            address = service.address
            biz_id = service.biz_id

            if biz_id:
                # Unsubscribe all emails from this business : same business
                services = Uploadedservice.query.filter_by(user_id = id, biz_id=biz_id).all()
                for service in services:
                    # Unsubscribe all service with this business
                    service.is_unsubscribed = 1
                    
                    # Unsubscribe all emails from campaigns
                    unsubscribe_token = service.unsubscribe_token
                    email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                    if email:
                        print("unsubscribed", email.email)
                        email.is_unsubscribed = 1

                    db.session.commit()
                    # 1-25-2025 do not delete reminder
                    # email = service.email
                    # reminder = Reminder.query.filter_by(userid=id, email=email).first()
                    # if reminder:
                    #     job_id = reminder.job_id
                    #     if scheduler.get_job(job_id):
                    #         scheduler.remove_job(job_id)
                    #     db.session.delete(reminder)
                    #     db.session.commit()

            elif address:
                # Unsubscribe all emails from this address : same business
                services = Uploadedservice.query.filter_by(user_id = id, address=address).all()
                for service in services:
                    # Unsubscribe all service with this address
                    service.is_unsubscribed = 1
                    
                    # Unsubscribe all emails from campaigns
                    unsubscribe_token = service.unsubscribe_token
                    email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                    if email:
                        print("unsubscribed", email.email)
                        email.is_unsubscribed = 1

                    db.session.commit()
                    # 1-25-2025 do not delete reminder
                    # email = service.email
                    # reminder = Reminder.query.filter_by(userid=id, email=email).first()
                    # if reminder:
                    #     job_id = reminder.job_id
                    #     if scheduler.get_job(job_id):
                    #         scheduler.remove_job(job_id)
                    #     db.session.delete(reminder)
                    #     db.session.commit()
            else:
                phone = service.phone

                if phone:
                    # Unsubscribe all emails from this phone : same business
                    services = Uploadedservice.query.filter_by(user_id = id, phone=phone).all()
                    for service in services:
                        # Unsubscribe all service with this phone
                        service.is_unsubscribed = 1
                        
                        # Unsubscribe all emails from campaigns
                        unsubscribe_token = service.unsubscribe_token
                        email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                        if email:
                            print("unsubscribed", email.email)
                            email.is_unsubscribed = 1

                        db.session.commit()

                        # email = service.email
                        # reminder = Reminder.query.filter_by(userid=id, email=email).first()
                        # if reminder:
                        #     job_id = reminder.job_id
                        #     if scheduler.get_job(job_id):
                        #         scheduler.remove_job(job_id)
                        #     db.session.delete(reminder)
                        #     db.session.commit()

                else:
                    venue = service.name
                    if venue:
                        # Unsubscribe all emails from this venue : same business
                        services = Uploadedservice.query.filter_by(user_id = id, name=venue).all()
                        for service in services:
                            # Unsubscribe all service with this venue
                            service.is_unsubscribed = 1
                            
                            # Unsubscribe all emails from campaigns
                            unsubscribe_token = service.unsubscribe_token
                            email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                            if email:
                                print("unsubscribed", email.email)
                                email.is_unsubscribed = 1

                            db.session.commit()
                            # email = service.email
                            # reminder = Reminder.query.filter_by(userid=id, email=email).first()
                            # if reminder:
                            #     job_id = reminder.job_id
                            #     if scheduler.get_job(job_id):
                            #         scheduler.remove_job(job_id)
                            #     db.session.delete(reminder)
                            #     db.session.commit()
    
    except Exception as e:
        print(repr(e))
        return "Something went wrong. Please try again."
    
    return "You have been unsubscribed successfully."


@blueprint.route('/unsubscribe/<token>', methods=['GET'])
def unsub(token):
    # redirect to unsubscribe
    return redirect(url_for('home_blueprint.unsubscribe', token=token))

@blueprint.route('/us/<token>', methods=['GET'])
def unsubscribe(token):
    emails = Email.query.filter_by(unsubscribe_token=token).all()
    service = Uploadedservice.query.filter_by(unsubscribe_token=token).first()
    
    for email in emails:
        email.is_unsubscribed = 1
        db.session.commit()
    
    if service:
        service.is_unsubscribed = 1
        db.session.commit()

    # 1-25-2025 do not delete reminder
    # user_id = service.user_id
    # email = service.email
    # reminder = Reminder.query.filter_by(userid=user_id, email=email).first()
    # if reminder:
    #     job_id = reminder.job_id
    #     if scheduler.get_job(job_id):
    #         scheduler.remove_job(job_id)
    #     db.session.delete(reminder)
    #     db.session.commit()

    return "You have been unsubscribed successfully."


@blueprint.route('/subscribe/<token>', methods=['GET'])
def subscribe(token):
    emails = Email.query.filter_by(unsubscribe_token=token).all()
    service = Uploadedservice.query.filter_by(unsubscribe_token=token).first()
    
    for email in emails:
        email.is_unsubscribed = 0
        db.session.commit()
    
    if service:
        service.is_unsubscribed = 0

        serviceid = service.id
        WEB_HOST_IP = os.getenv("WEB_HOST_IP")
        creat_reminder_page_url =  f"{WEB_HOST_IP}/reminders?serviceid={serviceid}"
        db.session.commit()
        return "You have been subscribed successfully. <a href='" + creat_reminder_page_url + "'>Create Reminder</a>"
    
    return "You have been subscribed successfully."

# archive emails
@blueprint.route('/archive/<token>', methods=['GET'])
@login_required
@user_approved_required
def archive_email(token):
    print("archive_email", token)
    Email.query.filter_by(unsubscribe_token=token).update({"is_archived": 1})
    db.session.commit()
    return "Email archived successfully."


@blueprint.route('/passwordreset', methods=['GET', 'POST'])
def passwordreset():
    if request.method == 'POST':
        email = request.form['email'].lower()
        user = Users.query.filter_by(email=email).first()
        
        if user:
            token = generate_job_id(128)
            user.password_reset_token = token
            db.session.commit()
            
            WEB_HOST_IP = os.getenv("WEB_HOST_IP")
            reset_link = f"{WEB_HOST_IP}/newpassword/{token}"
            
            send_password_reset_email(email, reset_link)
            
            return render_template('home/password_reset.html', segment="passwordreset", msg="Please check your email for password reset link.")
        else:
            return render_template('home/password_reset.html', segment="passwordreset", msg="There is no user with this email.")
        
    else:
        return render_template('home/password_reset.html', segment="passwordreset")
    

@blueprint.route('/update_email', methods=['POST'])
def update_email():
    email = request.form['new_email'].lower()
    user = Users.query.filter_by(email=email).first()
    if user:
        return {"success": False, "message": "This email is already registered."}
    
    user = Users.query.get(current_user.id)
    user.email = email
    user.username = email
    # reset nylas access token
    user.nylas_access_token = None

    db.session.commit()
    return {"success": True, "message": "Email updated successfully."}
    


@blueprint.route('/newpassword/<token>', methods=['GET', 'POST'])
def newpassword(token):
    
    
    if request.method == "GET":
        user = Users.query.filter_by(password_reset_token=token).first()
        if user:
            return render_template('home/new_password.html', segment="newpassword", token=token)
        else:
            return render_template('home/page-404.html')
    
    else:
        password = request.form['password']
        token = request.form['token']
        user = Users.query.filter_by(password_reset_token=token).first()
        
        if user:
            user.password = hash_pass(password)
            user.password_reset_token = None
            db.session.commit()
            return redirect(url_for('authentication_blueprint.login')) 
        
        else:
            return render_template('home/page-404.html')
        

@blueprint.route('/privacy', methods=['GET'])
def privacy():
    return render_template('home/privacy_policy.html', segment="privacy")

@blueprint.route('/terms', methods=['GET'])
def terms():
    return render_template('home/terms_of_service.html', segment="terms")



@blueprint.route('/admin/connected_accounts', methods=['GET'])
@login_required
@role_required('admin')
def connected_accounts():
    return render_template('home/admin_connected_accounts.html', segment="connected_accounts")


@blueprint.route('/admin/get_connected_accounts', methods=['GET'])
@login_required
@role_required('admin')
def get_connected_accounts():
    # parase query params
    params = request.args.to_dict()
    draw = int(params.get('draw', 0))
    start = int(params.get('start', 0))
    length = int(params.get('length', 10))
    
    queryparams = {
        "limit": length,
        "offset": start
    }

    try:
        accounts = nylas.grants.list(query_params=queryparams).data
    except Exception as e:
        print(repr(e))
        return jsonify({"draw": draw, "recordsTotal": 0, "recordsFiltered": 0, "data": []})
    
    connected_accounts = []

    for account in accounts:
        user_email = account.email.lower()
        user = Users.query.filter_by(email=user_email).first()

        # if user.state == "pending":
        #     continue

        # print(account)
        data = {
            "id" : account.id,
            "account_id" : account.id,
            "email" : account.email,
            "grant_status" : account.grant_status,
        }
        
        if user:
            automations = Automation.query.filter(Automation.userid == user.id).all()
            all_automations = 0
            completed_automations = 0
            running_pending_automations = 0
            for automation in automations:
                if automation.status == "completed":
                    completed_automations += 1
                elif automation.status == "pending" or automation.status == "running":
                    running_pending_automations += 1
                
                all_automations += 1

            # print(account.email, "all_automations", all_automations, "completed_automations", completed_automations)
            if all_automations == completed_automations:
                status = "finished"
            else:
                status = "running"

            data.update({"user_id" : user.id, "automations_count" : running_pending_automations, "status" : status})
        else:
            status = "finished"
            data.update({"user_id" : None, "automations_count" : 0, "status" : status})

        connected_accounts.append(data)
    
    # sort connected_accounts by automations_count
    connected_accounts = sorted(connected_accounts, key=lambda x: x['automations_count'])
    
    return jsonify({"draw": draw, "recordsTotal": 1000, "recordsFiltered": 1000, "data": connected_accounts})
    

@blueprint.route('/admin/disconnect_account', methods=['POST'])
@login_required
@role_required('admin')
def disconnect_account():
    formdata = request.form
    grant_id =formdata['account_id']
    email = formdata['email'].lower()

    try:
        response = nylas.grants.destroy( grant_id )
        print(response)

        return {"success": True, "message": "Successfully disconnected account."}

    except Exception as e:
        print(repr(e))
        return {"success": False, "message": "Failed to delete account."}



@blueprint.route('/admin/get_users_campaign_settings', methods=['GET'])
@login_required
@role_required('admin')
def get_users_campaign_settings():
    users = db.session.query(Users, UserCampaignSetting).filter(Users.role != "admin").join(UserCampaignSetting, Users.id == UserCampaignSetting.userid, isouter=False).all()
    user_list = []

    for user in users:
        user_data = {
            'id': user[0].id,
            'email': user[0].email,
            'is_multisearch': user[0].is_multi_search,
            'update_datetime': user[1].update_datetime,
            'emails_daily_limit': user[1].emails_daily_limit,
        }
        user_list.append(user_data)

    return jsonify(user_list)

@csrf.exempt
@blueprint.route('/admin/enable_multisearch', methods=['POST'])
@login_required
@role_required('admin')
def enable_multisearch():
    userid = request.json['user_id']
    is_multisearch = 1 if request.json['is_multisearch'] else 0
    user = Users.query.filter_by(id=userid).first()
    user.is_multi_search = is_multisearch
    db.session.commit()
    return {"success": True, "message": "Multi search enabled."}


@blueprint.route('/admin/update/campaign_settings', methods=['POST'])
@login_required 
@role_required('admin')
def update_campaign_setting():
    userid = request.form['userid']
    emails_daily_limit = int(request.form['emails-daily-limit'])

    if userid:
        temp = UserCampaignSetting.query.filter(UserCampaignSetting.userid == userid).first()
        temp.emails_daily_limit = emails_daily_limit 

    db.session.commit()
    return redirect(url_for('home_blueprint.admin_users_campaign_settings'))


@blueprint.route('/connect_email', methods=['GET'])
@login_required
@user_approved_required
def connect_email():
    # redirect to nylas.login
    return redirect('/nylas/auth')


@blueprint.route('/nylas/auth', methods=['GET'])
@login_required
@user_approved_required
def nylas_auth():
    if current_user.nylas_access_token is None or current_user.nylas_access_token == "":
        NYLAS_AUTH_API_URI = os.getenv('NYLAS_AUTH_API_URI')
        NYLAS_CLIENT_ID = os.getenv('NYLAS_CLIENT_ID')
        NYLAS_REDIRECT_URI = os.getenv("WEB_HOST_IP") + "/oauth/exchange"

        nylas_auth = Client(
            api_key = NYLAS_API_KEY,
            api_uri = NYLAS_AUTH_API_URI,
        )
        config = URLForAuthenticationConfig(
            {"client_id": NYLAS_CLIENT_ID, 
            "redirect_uri" : NYLAS_REDIRECT_URI
            })

        url = nylas_auth.auth.url_for_oauth2(config)
        return redirect(url)
    
    else:
        return redirect(url_for('home_blueprint.index'))

@blueprint.route("/oauth/exchange", methods=["GET"])
@login_required
@user_approved_required
def authorized():
    if current_user.nylas_access_token is None:
        code = request.args.get("code")

        NYLAS_CLIENT_ID = os.getenv('NYLAS_CLIENT_ID')
        NYLAS_REDIRECT_URI = os.getenv("WEB_HOST_IP") + "/oauth/exchange"

        retry_count = 0
        NYLAS_AUTH_API_URI = os.getenv('NYLAS_AUTH_API_URI')

        nylas_auth = Client(
            api_key = NYLAS_API_KEY,
            api_uri = NYLAS_AUTH_API_URI,
        )

        exchangeRequest = CodeExchangeRequest(
            {"redirect_uri": NYLAS_REDIRECT_URI,
            "code": code, 
            "client_id": NYLAS_CLIENT_ID})
        while True:
            try:
                exchange = nylas_auth.auth.exchange_code_for_token(exchangeRequest)
                break
            except requests.exceptions.ConnectionError:
                print("Connection error")
                time.sleep(2)
                retry_count += 1

            if retry_count > 5:
                return redirect(url_for('home_blueprint.index'))
            
            continue

        grant_id = exchange.grant_id

        user = Users.query.filter_by(id=current_user.id).first()
        user.nylas_access_token = grant_id
        db.session.commit()

        print("Nylas token updated", grant_id)

        return redirect(url_for('home_blueprint.index'))
    
    else:
        return redirect(url_for('home_blueprint.index'))


@blueprint.route('/get_howto_text', methods=['GET'])
@login_required
def get_howto_text():

    howto_text = HowToFAQ.query.first()
    if howto_text is None:
        howto_text = HowToFAQ()
        howto_text.text = ""
        db.session.add(howto_text)
        db.session.commit()
    else:
        howto_text = HowToFAQ.query.first()

        return jsonify({"text": howto_text.content, "id": howto_text.id})


@blueprint.route('/update_howto_text', methods=['POST'])
@login_required
@role_required('admin')
def update_howto_text():
    text = request.form.get('text')
    id = request.form.get('id')
    howto_text = HowToFAQ.query.filter_by(id=id).first()
    try:
        if howto_text:
            howto_text.content = text
            db.session.commit()

        return jsonify({"success": True, "message": "Updated successfully."})
    except Exception as e:
        print(repr(e))
        return jsonify({"success": False, "message": repr(e)})


@blueprint.route('/reg_push_notify', methods=['POST'])
@login_required
def reg_push_notify():
    subscription_info = request.form.to_dict()
    user_id = subscription_info.get('user_id')
    subscrition = json.loads(subscription_info.get('subscription'))
    subscrition.update({"user_id": user_id})

    push_notifications = PushNotificationInfo.query.filter_by(userid=user_id).all()
    for push_notification in push_notifications:
        if subscrition['keys']['auth'] == push_notification.subscription_info['keys']['auth']:
            # delete existing subscription
            db.session.delete(push_notification)
            db.session.commit()
            print(f"User {user_id} already subscribed")
            break

    push_notification = PushNotificationInfo()
    push_notification.userid = user_id
    push_notification.subscription_info = subscrition
    db.session.add(push_notification)
    print(f"User {user_id} subscribed")
    db.session.commit()
    return jsonify({"success": True}), 200


@blueprint.route('/update_subscription', methods=['POST'])
def update_subscription():
    subscription_info = request.form.to_dict()
    user_id = subscription_info.get('user_id')
    subscrition = json.loads(subscription_info.get('subscription'))
    subscrition.update({"user_id": user_id})

    push_notification = PushNotificationInfo.query.filter_by(userid=user_id).first()
    push_notification.subscription_info = subscrition
    db.session.commit()
    return jsonify({"success": True}), 200

@csrf.exempt
@blueprint.route('/send_notification', methods=['POST'])
def send_notification():
    data = request.get_json()
    user_id = data.get('user_id')
    reminder_message = data.get('message')
    reminder_id = data.get('reminder_id')

    # Get the subscription info from JSON column
    subscription = PushNotificationInfo.query.filter_by(userid=user_id).first()
    
    if subscription:
        try:
            sub_info = subscription.subscription_info
            endpoint_url = sub_info.get('endpoint')
            parsed_url = urllib.parse.urlparse(endpoint_url)
            origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
            vapid_claims = current_app.config.get('VAPID_CLAIMS')
            vapid_claims.update({'aud' : origin})
            vapid_private_key = current_app.config.get('VAPID_PRIVATE_KEY')
            title = "Reminder"
            body = reminder_message
            url = f"/reminders"
            if send_push_notification(sub_info, title,  body, reminder_id, vapid_claims, vapid_private_key, url):
                return jsonify({"success": True}), 200
            else:
                return jsonify({"error": "Failed to send notification"}), 500
            
        except WebPushException as ex:
            return jsonify({"error": str(ex)}), 500
            
    return jsonify({"error": "User not subscribed"}), 404


@blueprint.route('/get_reminders', methods=['GET'])
@login_required
@user_approved_required
def get_reminders():
    user_id = request.args.get('_id')
    reminder_id = request.args.get('reminder_id')
    if reminder_id:
        reminders = (
                db.session.query(Reminder, Uploadedservice)
                .outerjoin(
                    Uploadedservice,
                    and_(
                        Reminder.email == Uploadedservice.email,
                        Reminder.userid == Uploadedservice.user_id
                    )
                )
                .filter(Reminder.id == reminder_id, Reminder.userid == user_id)
                .all()
            )
    else:
        reminders = (
            db.session.query(Reminder, Uploadedservice)
            .outerjoin(
                Uploadedservice,
                and_(
                    Reminder.email == Uploadedservice.email,
                    Reminder.userid == Uploadedservice.user_id
                )
            )
            .filter(Reminder.userid == user_id)
            .all()
        )
        
    reminder_list = []

    for reminder, uploadservice in reminders:
        reminder_data = {
            'reminder_id': reminder.id,
            'title': reminder.title,
            'note': reminder.note,
            'name': reminder.name,
            'email': reminder.email,
            'phone': reminder.phone,
            'venue': reminder.venue,
            'title_template': reminder.note_template,
            'reminder_time': reminder.reminder_time,
            'status': reminder.status,
            'created_datetime': reminder.create_datetime,
            'updated_datetime': reminder.update_datetime,
            'unsub_token' : uploadservice.unsubscribe_token if uploadservice else None,
            'is_unsubscribed' : uploadservice.is_unsubscribed if uploadservice else False,
        }
        reminder_list.append(reminder_data)

    return jsonify(reminder_list)

# get_reminder
@blueprint.route('/get_reminder', methods=['POST'])
@login_required
@user_approved_required
def get_reminder():
    reminder_id = request.form.get('reminder_id')
    reminder = Reminder.query.filter_by(id=reminder_id).first()
    if reminder is None:
        return jsonify({"error": "Reminder not found."}), 404
    else:
        reminder_data = {
            'reminder_id': reminder.id,
            'title': reminder.title,    
            'note': reminder.note,
            'name': reminder.name,
            'email': reminder.email,
            'phone': reminder.phone,
            'venue': reminder.venue,
            'title_template': reminder.note_template,
            'reminder_time': reminder.reminder_time,
            'status': reminder.status,
        }
        return jsonify(reminder_data)


@blueprint.route("/reminders", methods=["GET"])
@login_required
@user_approved_required
def reminders():
    reminder_id = request.args.get('reminder_id')
    serviceid = request.args.get('serviceid')
    print("reminder_id", reminder_id)
    print("serviceid", serviceid)
    user_id = current_user.id
    if reminder_id:
        reminder = Reminder.query.filter_by(id=reminder_id, userid=user_id).first()
        if reminder is None:
            return render_template('home/page-404.html')
        else:
            return render_template('home/reminders.html', segment="reminders", user_id=current_user.id, reminder_id=reminder_id)
    elif serviceid:
        return render_template('home/reminders.html', segment="reminders", user_id=current_user.id, reminder_id='', serviceid=serviceid)
    else:
        return render_template('home/reminders.html', segment="reminders", user_id=current_user.id, reminder_id='', serviceid='')
    

def get_local_time_from_utc(utc_time):
    utc_time = datetime.datetime.strptime(utc_time, '%Y-%m-%dT%H:%M:%S.%fZ')
    utc_time_iso_string = utc_time.strftime('%Y-%m-%d %H:%M:%S')
    local_zone = tzlocal.get_localzone()
    utc_zone = pytz.utc
    reminder_utc_time = utc_zone.localize(utc_time)
    reminder_local_time = reminder_utc_time.astimezone(local_zone)
    reminder_local_time_string = reminder_local_time.strftime('%Y-%m-%d %H:%M:%S')
    # print("reminder_local_time_string", reminder_local_time_string)
    # print("utc_time_iso_string", utc_time_iso_string)
    return reminder_local_time_string, utc_time_iso_string


def get_utc_time_from_local_time(local_time):
    local_time = datetime.datetime.strptime(local_time, '%Y-%m-%d %H:%M:%S')
    local_zone = tzlocal.get_localzone()
    utc_zone = pytz.utc
    reminder_local_time = local_zone.localize(local_time)
    reminder_utc_time = reminder_local_time.astimezone(utc_zone)
    reminder_utc_time_string = reminder_utc_time.strftime('%Y-%m-%d %H:%M:%S')
    return reminder_utc_time_string

    

@blueprint.route('/add_reminder', methods=['POST'])
def add_reminder():
    data = request.form
    if data.get('reminder_id'): # Update reminder
        reminder = Reminder.query.filter_by(id=data.get('reminder_id')).first()
        if reminder:
            job_id = reminder.job_id
            user_id = data.get('userid')
            reminder.title = data.get('title')

            reminder.note = data.get('note')
            reminder.name = data.get('name')
            reminder.email = data.get('email')
            reminder.phone = data.get('phone')
            reminder.venue = data.get('venue')
            reminder.note_template = data.get('title_template')
            reminder_local_time_string, utc_time_iso_string = get_local_time_from_utc(data['reminder_time'])
            reminder.reminder_time = utc_time_iso_string
            reminder.status = "active"

            job = {
                "id" : job_id,
                'trigger' : 'date',
                "run_date" : reminder_local_time_string,
                "func" : "jobs:job_push_notification_reminder",
                "args" : (job_id, user_id)
            }
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)

            try:
                scheduler.add_job(**job) # TODO: Uncomment this line
                print("created job", job_id)
            except Exception as e:
                print("Failed to create job", str(e))
                return {"success": False, "message": "Something went wrong. Please try again."}

            db.session.commit()
            return jsonify({"success": True, "message": "Reminder updated successfully."})
        else:
            return jsonify({"message": "Reminder not found."}), 404
        
    else: # Add reminder

        user_id = data.get('userid')
        email = data.get('email')

        reminder = Reminder.query.filter_by( userid=user_id, email=email).first()
        if reminder:
            job_id = reminder.job_id
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            db.session.delete(reminder)
            db.session.commit()

        job_id = "job_" + generate_job_id(32)
        reminder_local_time_string, utc_time_iso_string = get_local_time_from_utc(data['reminder_time'])

        job = {
            "id" : job_id,
            'trigger' : 'date',
            "run_date" : reminder_local_time_string,
            "func" : "jobs:job_push_notification_reminder",
            "args" : (job_id, user_id)
        }
        print(job)
        try:
            scheduler.add_job(**job) # TODO: Uncomment this line
            print("created job", job_id)
        except Exception as e:
            print("Failed to create job", str(e))
            return {"success": False, "message": "Something went wrong. Please try again."}
        
        reminder = Reminder()
        reminder.title = data.get('title')
        reminder.job_id = job_id
        reminder.note = data.get('note')
        reminder.name = data.get('name')
        reminder.email = data.get('email')
        reminder.phone = data.get('phone')
        reminder.venue = data.get('venue')
        reminder.note_template = data.get('title_template')
        reminder.reminder_time = utc_time_iso_string  
        reminder.status = "active"
        reminder.userid = data.get('userid')
        db.session.add(reminder)
        db.session.commit()

        return jsonify({"success": True, "message": "Reminder added successfully."})
    

@blueprint.route('/delete_reminder', methods=['POST'])
def delete_reminder():
    reminder_id = request.form.get('reminder_id')
    reminder = Reminder.query.filter_by(id=reminder_id).first()

    job_id = reminder.job_id
    if scheduler.get_job(job_id):
        print("Removing job", job_id)
        scheduler.remove_job(job_id)

    db.session.delete(reminder)
    db.session.commit()

    return jsonify({"success": True, "message": "Reminder deleted successfully."})


@blueprint.route('/complete_reminder/<int:reminder_id>', methods=['GET'])
def complete_reminder(reminder_id):
    # Ignore csrf token check
    reminder = Reminder.query.filter_by(id=reminder_id).first()
    if reminder is None:
        return jsonify({"error": "Reminder not found."}), 404
    
    reminder.status = "completed"
    db.session.commit()
    return jsonify({"success": True, "message": "Reminder completed successfully."})


# reschedule_reminder, days and hours
@blueprint.route('/reschedule_reminder', methods=['POST'])
def reschedule_reminder():
    data = request.form
    reminder_id = data.get('reminder_id')
    reminder = Reminder.query.filter_by(id=reminder_id).first()
    reminder_time = reminder.reminder_time # This is in UTC
    days = data.get('days', 0)
    hours = data.get('hours', 0)
    utc_time_now = datetime.datetime.now(timezone.utc)
    reminder_time = utc_time_now + timedelta(days=int(days), hours=int(hours))

    reminder_time_str = reminder_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    reminder_local_time_string, utc_time_iso_string = get_local_time_from_utc(reminder_time_str)    
    reminder.reminder_time = utc_time_iso_string

    job_id = reminder.job_id
    user_id = reminder.userid
    job = {
        "id" : job_id,
        'trigger' : 'date',
        "run_date" : reminder_local_time_string,
        "func" : "jobs:job_push_notification_reminder",
        "args" : (job_id, user_id)
    }
    print("Reschedular reminder", job)

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    try:
        scheduler.add_job(**job) # TODO: Uncomment this line
        db.session.commit()
        print("created job", job_id)
    except Exception as e:
        print("Failed to create job", str(e))
        return {"success": False, "message": "Something went wrong. Please try"}

    return jsonify({"success": True, "message": "Reminder rescheduled successfully."})


# update /update_auto_unsub
@blueprint.route('/update_auto_unsub', methods=['POST'])
@login_required
@user_approved_required
def update_auto_unsub():
    user_id = current_user.id
    is_auto_unsub = request.form.get('is_auto_unsub')
    user = Users.query.filter_by(id=user_id).first()
    user.is_auto_unsub = is_auto_unsub
    db.session.commit()
    return jsonify({"success": True, "message": "Auto Unsubscribe updated successfully."})


#  update /update_opt_musicians
@blueprint.route('/update_opt_musicians', methods=['POST'])
@login_required
@user_approved_required
def update_opt_musicians():
    user_id = current_user.id
    is_opt_musicians = request.form.get('is_opt_musicians')
    user = Users.query.filter_by(id=user_id).first()
    user.is_opt_musicians = is_opt_musicians
    db.session.commit()
    return jsonify({"success": True, "message": "Opt Musicians updated successfully."})


#  update /update_allow_deduplication
@blueprint.route('/update_allow_deduplication', methods=['POST'])
@login_required
@user_approved_required
def update_allow_deduplication():
    user_id = current_user.id
    is_allow_deduplicate = request.form.get('is_allow_deduplicate')
    user = Users.query.filter_by(id=user_id).first()
    user.is_allow_deduplicate = is_allow_deduplicate
    db.session.commit()
    return jsonify({"success": True, "message": "Allow Deduplication updated successfully."})


@blueprint.route('/get_service_with_userid_bizid', methods=['GET'])
def get_service_with_userid_bizid():
    biz_id = request.args.get('biz_id')
    user_id = request.args.get('user_id')
    services = Service.query.filter(Service.biz_id == biz_id).all()

    is_exist = False

    final_service = dict()
    emails = []
    for service in services:
        service_data = service.to_dict()

        service_user_id = service_data.get('user_id')
        if service_user_id == user_id:
            is_exist = True

        for k, v in service_data.items():
            if 'email' in k  and 'bademail' not in k and 'fbemail' not in k:
                if v and v.lower() not in emails:
                    emails.append(v.lower())
                    
            if final_service.get(k) is None:
                final_service[k] = v
            else:
                if isinstance(final_service[k], str) and isinstance(v, str):
                    if len(v) > len(final_service[k]):
                        final_service[k] = v
    
    if final_service:
        final_service['email1'] = emails[0] if len(emails) > 0 else ''
        final_service['email2'] = emails[1] if len(emails) > 1 else ''
        final_service['email3'] = emails[2] if len(emails) > 2 else ''
        final_service['email4'] = emails[3] if len(emails) > 3 else ''
        
                        
    # convert service model to dict
    return jsonify({"service": final_service, "is_exist": is_exist, "user_id": user_id}) 

@blueprint.route('/admin/users/bulk/update-plan', methods=['POST'])
@login_required
@role_required('admin')
def bulk_update_plan():
    """Update plan for multiple users"""
    try:
        # Get data from form (array of user_ids)
        user_ids = request.form.getlist('user_ids[]')
        plan = request.form.get('plan')
        
        if not user_ids or not plan:
            return jsonify({'success': False, 'message': 'Missing parameters'}), 400
        
        # Validate plan
        valid_plans = ['lite', 'normal', 'premium']
        if plan not in valid_plans:
            return jsonify({'success': False, 'message': 'Invalid plan type'}), 400
        
        updated_count = 0
        for user_id in user_ids:
            user = Users.query.get(user_id)
            if user and user.role != 'admin':  # Don't update admin users
                if plan == 'normal':
                    user.role = 'user'
                else:
                    user.role = plan
                
                # If it's lite plan, add initial credit
                if plan == 'lite':
                    user_credit = UserCredit.query.filter_by(userid=user_id).first()
                    user_initial_credit = 10
                    if user_credit:
                        user_credit.credit = user_initial_credit
                    else:
                        user_credit = UserCredit(userid=user_id, credit=user_initial_credit)
                        db.session.add(user_credit)
                
                updated_count += 1
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'Plan updated for {updated_count} user(s)'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@blueprint.route('/admin/users/bulk/update-status', methods=['POST'])
@login_required
@role_required('admin')
def bulk_update_status():
    """Update status for multiple users"""
    try:
        user_ids = request.form.getlist('user_ids[]')
        status = request.form.get('status')
        
        if not user_ids or not status:
            return jsonify({'success': False, 'message': 'Missing parameters'}), 400
        
        # Validate status
        valid_statuses = ['approve', 'inactive']
        if status not in valid_statuses:
            return jsonify({'success': False, 'message': 'Invalid status type'}), 400
        
        updated_count = 0
        for user_id in user_ids:
            user = Users.query.get(user_id)
            if user and user.role != 'admin':  # Don't update admin users
                if status == 'approve':
                    user.state = 'approved'
                elif status == 'inactive':
                    user.state = 'pending'
                updated_count += 1
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'Status updated for {updated_count} user(s)'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@blueprint.route('/admin/users/bulk/delete', methods=['POST'])
@login_required
@role_required('admin')
def bulk_delete_users():
    """Delete multiple users"""
    try:
        user_ids = request.form.getlist('user_ids[]')
        
        if not user_ids:
            return jsonify({'success': False, 'message': 'No users selected'}), 400
        
        deleted_count = 0
        for user_id in user_ids:
            user = Users.query.get(int(user_id))
            if user and user.role != 'admin':  # Don't delete admin users
                # Delete associated data
                Service.query.filter_by(user_id=user_id).delete()
                Yelpurl.query.filter_by(userid=user_id).delete()
                Uploadedservice.query.filter_by(user_id=user_id).delete()
                Uploadedcontactfile.query.filter_by(user_id=user_id).delete()
                Template.query.filter_by(userid=user_id).delete()
                
                # Delete automations and emails
                jobs = Automation.query.filter_by(userid=user_id).all()
                for job in jobs:
                    Email.query.filter_by(job_id=job.job_id).delete()
                    db.session.delete(job)
                
                # Delete other related data
                Action.query.filter_by(userid=user_id).delete()
                Campaign.query.filter_by(userid=user_id).delete()
                UserCredit.query.filter_by(userid=user_id).delete()
                UserCampaignSetting.query.filter_by(userid=user_id).delete()
                Reminder.query.filter_by(userid=user_id).delete()
                PushNotificationInfo.query.filter_by(userid=user_id).delete()
                
                # Delete the user
                db.session.delete(user)
                deleted_count += 1
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{deleted_count} user(s) deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@blueprint.route('/admin/users/bulk/reset-token', methods=['POST'])
@login_required
@role_required('admin')
def bulk_reset_tokens():
    """Reset Nylas tokens for multiple users"""
    try:
        user_ids = request.form.getlist('user_ids[]')
        
        if not user_ids:
            return jsonify({'success': False, 'message': 'No users selected'}), 400
        
        reset_count = 0
        for user_id in user_ids:
            user = Users.query.get(int(user_id))
            if user and user.role != 'admin' and user.nylas_access_token:  # Only reset if token exists
                user.nylas_access_token = None
                reset_count += 1
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'Tokens reset for {reset_count} user(s)'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
@blueprint.route('/admin/users/bulk/reset-unimail', methods=['POST'])
@login_required
@role_required('admin')
def bulk_reset_unimail():
    """Reset Unimail for multiple users"""
    try:
        user_ids = request.form.getlist('user_ids[]')
        
        if not user_ids:
            return jsonify({'success': False, 'message': 'No users selected'}), 400
        
        reset_count = 0
        for user_id in user_ids:
            user = Users.query.get(int(user_id))
            if user and user.role != 'admin':  # Don't reset admin users
                # Delete Mailing record for this user if exists
                mailing = Mailing.query.filter_by(user_id=user_id).first()
                if mailing:
                    db.session.delete(mailing)
                    reset_count += 1
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'Unimail disconnected for {reset_count} user(s)'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
