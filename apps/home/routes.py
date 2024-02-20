# from scrapy.crawler import CrawlerProcess
# from apps.home.script import  homes
from functools import wraps
import os
import pprint

from apps.authentication.models import Users
from apps.authentication.util import verify_pass, hash_pass
from apps.home import blueprint
from flask import render_template, request, jsonify, redirect, url_for, current_app
from flask_login import login_required, current_user, logout_user, login_user
from jinja2 import Template as JT

from apps.config import API_GENERATOR
import requests
from datetime import datetime, timedelta
from apps import db, scheduler
import multiprocessing
from apps.home.script import yelp_scraper_run
from apps.models import *
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import Insert

from concurrent.futures import ThreadPoolExecutor
from apps.authentication.forms import LoginForm, CreateAccountForm
from flask_dance.contrib.nylas import nylas
from apps.home.emailler import send_test_email, send_email_via_nylas, send_password_reset_email
from apps.authentication.util import generate_job_id
from nylas import APIClient

import pandas as pd
import urllib.parse

from apps.authentication.oauth import nylas_bp
from apps.home.utils import check_blacklisted

executor = ThreadPoolExecutor(4)

processes = {}


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



@blueprint.route('/home')
@login_required
def index():
    page_data = get_page_data()
    if nylas.authorized : 
        if not current_user.nylas_access_token:
            
            user = Users.query.filter_by(id=current_user.id).first()
            user.nylas_access_token = nylas.access_token
            db.session.commit()
            logout_user()

            # delete nyals token from storage
            del nylas_bp.token
            
            return redirect(url_for('authentication_blueprint.login')) 
            
    return render_template('home/index.html', segment='index', API_GENERATOR=len(API_GENERATOR), page_data=page_data )


@compiles(Insert, "sqlite")
def sqlite_insert_ignore(insert, compiler, **kw):
    return compiler.visit_insert(insert.prefix_with("OR IGNORE"), **kw)

@blueprint.route('/url', methods=['POST', 'GET'])
@login_required
def url():
    if request.method == 'POST':
        location = request.form['location']
        business = request.form['business']

        base_url = 'https://www.yelp.com/search?'
        encoded_business = urllib.parse.quote(business)
        encoded_location = urllib.parse.quote(location)

        encoded_url = f"find_desc={encoded_business}&find_loc={encoded_location}"
        url = base_url + encoded_url

        existing_url = Yelpurl.query.filter_by(product_url=url, userid=current_user.id).first()
        if existing_url is None:
            new_url = Yelpurl(product_url=url, userid=current_user.id, state="idle", name=business)
            db.session.add(new_url)
            db.session.commit()
            
            existing_url = Yelpurl.query.filter_by(product_url=url, userid=current_user.id).first()
            url_id = existing_url.id
            
            return redirect(url_for('home_blueprint.fetch', id=url_id))
            
        else:
            print("already present in db")
            message = "This url is already reistered."

            if current_user.role == "lite":
                credit = UserCredit.query.filter_by(userid=current_user.id).first().credit
                consumed = Service.query.filter_by(user_id=current_user.id, is_credited=1).count()
                available_credit = credit - consumed
                return render_template('home/view_scraped_data.html', segment='history', available_credit=available_credit, user_credit=credit, consumed=consumed, message=message)
            
            return render_template('home/view_urls.html', segment='history', message=message )
        
    else:
        return render_template('home/add_url.html', segment='url')


@blueprint.route('/url_history')
@login_required
def url_history():
    user_urls = Yelpurl.query.filter_by(userid=current_user.id).order_by(Yelpurl.create_datetime.desc()).all()
    url_list = []

    for url_entry in user_urls:
        url_data = {
            'url_id': url_entry.userid,
            'product_url': url_entry.product_url,
            'id': url_entry.id,
            'name': url_entry.name,
            'state' : url_entry.state
        }
        url_list.append(url_data)

    return jsonify(url_list)


@blueprint.route('/view_url_history/<int:url_id>')
@login_required
def view_url_history(url_id):
    # Return only the urls that are credited
    user_urls = Service.query.filter_by(url_id=url_id, user_id=current_user.id).all()
    # print(user_urls)
    url_list = []
    for url_entry in user_urls:
        url_data = {
            "id": url_entry.id,
            "venue": url_entry.name,
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
            "firstname": "",
            "customtext": "",
            "originalemail": "",
        }
        url_list.append(url_data)
    return jsonify(url_list)


@blueprint.route('/view_scraped_data', methods=['GET'])
@login_required
def view_scraped_data():
    
    # Return only the services that are not credited
    user_urls = Service.query.filter_by(user_id=current_user.id, is_credited=0).limit(10).all()
    url_list = []
    for url_entry in user_urls:
        url_data = {
            "id": url_entry.id,
            "name": url_entry.name,
            "venue_type": url_entry.venue_type,
            "website": url_entry.website,
            "phone": url_entry.phone,
            "address": url_entry.address,
            # "facebook": url_entry.facebook,
            # "instagram": url_entry.instagram,
            # "twitter": url_entry.twitter,
            # "email1": url_entry.email1,
            # "email2": url_entry.email2,
            # "email3": url_entry.email3,
            # "email4": url_entry.email4,
            # "fbemail1": url_entry.fbemail1,
            # "fbemail2": url_entry.fbemail2,
            # "bademail": url_entry.bademail,
            "url_id": url_entry.url_id,
            "user_id": url_entry.user_id,
        }
        url_list.append(url_data)
    return jsonify(url_list)


@blueprint.route('/view_credited_data', methods=['GET'])
@login_required
def view_credited_data():
    
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


@blueprint.route('/history', methods=['POST', 'GET'])
@login_required
def history():
    if current_user.role == "lite":
        credit = UserCredit.query.filter_by(userid=current_user.id).first().credit
        consumed = Service.query.filter_by(user_id=current_user.id, is_credited=1).count()
        available_credit = credit - consumed
        
        return render_template('home/view_scraped_data.html', segment='history', available_credit=available_credit, user_credit=credit, consumed=consumed)
    else:
        return render_template('home/view_urls.html', segment='history')
    

@blueprint.route('/view_credited')
@login_required
def view_credited():
    credited = Service.query.filter_by(user_id=current_user.id, is_credited=1).count()
    return render_template('home/view_credited_data.html', segment='history', credited=credited)


@blueprint.route('/update/credit', methods=['POST'])
@login_required
def credit_service():
    serviceid = request.json['id']
    action = request.json['action']

    user_credit = db.session.query(UserCredit).filter_by(userid = current_user.id).first()

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

            db.session.commit()
            return {"success": True, 'message': message, "available_credit" : available_credit, "user_credit" : user_credit.credit }
        
        else:
            return {"success": False, 'message': "You consumed all credit. You can not add more services."}
    else:
        service.is_credited = 2
        message = f"Service '{service.name}' is not credited."
        available_credit = user_available_credit
        db.session.commit()
        return {"success": True, 'message': message, "available_credit" : available_credit, "user_credit" : user_credit.credit }



@blueprint.route('/fetch/<int:id>', methods=['GET', 'POST'])
@login_required
def fetch(id):
    obj = Yelpurl.query.get(id)
    if obj.state != "running":
        obj.state = "running"
        
        urls = obj.product_url.split(',')
        
        #delete all sevices in db before run
        services = Service.query.filter_by(url_id=id).all()
        if len(services):
            for service in services:
                db.session.delete(service)
        db.session.commit()
        # run scraper
        try:
            executor.submit(lets_start, urls, current_user.id, id)
        except:
            print("something went wrong")
        
    return redirect(url_for('home_blueprint.fetching', id=id))


@blueprint.route('/complete', methods=['POST'])
def complete_process():
    id = request.json['id']
    yelpurl = Yelpurl.query.get(int(id))
    yelpurl.state = "completed"
    db.session.commit()
    return "Completed"


@blueprint.route('/fetching', methods=['GET', 'POST'])
@login_required
def fetching():
    id = request.args.get('id')
    yelpurl = Yelpurl.query.get(id)
    
    if yelpurl.state == "running":
        return render_template('home/fetch_url_data.html', segment='url', current_url=yelpurl )
    else:
        return redirect(url_for('home_blueprint.url_view', id=id))
    
    
@blueprint.route('/uploaded_files', methods=['GET'])
@login_required
def uploaded_files():
    uploaded_files = Uploadedcontactfile.query.filter_by(user_id=current_user.id).order_by(Uploadedcontactfile.create_datetime.desc()).all()
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

    return jsonify(files)
    
    
@blueprint.route('/upload_contact', methods=['GET', 'POST'])
@login_required
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
        
        description = request.form['description']
        contact_file = Uploadedcontactfile(filename=f.filename, filepath=filepath, description=description, user_id=current_user.id)
        db.session.add(contact_file)
        db.session.flush()
        file_id = contact_file.id
        
        services = []
        df.fillna("", inplace=True)
        for idx, item in df.iterrows():
            try:
                venue = item['venue']
                venue_type = item['type']
                website = item['website']
                phone = item['phone']
                address = item['address']
                facebook = item['facebook']
                firstname = item['firstname']
                customtext = item['customtext']
                originalemail = item['originalemail']
            except Exception as e:
                print(repr(e))
                continue
            
            if item['email1'].strip() != "" and check_blacklisted(item['email1'].strip()):
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['email1'].strip(), user_id = current_user.id, file_id=file_id)
                service.website = website
                service.phone = phone
                service.address = address
                service.facebook = facebook
                service.firstname = firstname
                service.customtext = customtext
                service.originalemail = originalemail
                services.append(service)
                
            if item['email2'].strip() != "" and check_blacklisted(item['email2'].strip()):
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['email2'].strip(), user_id = current_user.id, file_id=file_id)
                service.website = website
                service.phone = phone
                service.address = address
                service.facebook = facebook
                service.firstname = firstname
                service.customtext = customtext
                service.originalemail = originalemail
                services.append(service)
                
            if item['email3'].strip() != "" and check_blacklisted(item['email3'].strip()):
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['email3'].strip(), user_id = current_user.id, file_id=file_id)
                service.website = website
                service.phone = phone
                service.address = address
                service.facebook = facebook
                service.firstname = firstname
                service.customtext = customtext
                service.originalemail = originalemail
                services.append(service)
                
            if item['email4'].strip() != "" and check_blacklisted(item['email4'].strip()):
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['email4'].strip(), user_id = current_user.id, file_id=file_id)
                service.website = website
                service.phone = phone
                service.address = address
                service.facebook = facebook
                service.firstname = firstname
                service.customtext = customtext
                service.originalemail = originalemail
                services.append(service)
                
            if item['facebookemail1'].strip() != "" and check_blacklisted(item['facebookemail1'].strip()):
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['facebookemail1'].strip(), user_id = current_user.id, file_id=file_id)
                service.website = website
                service.phone = phone
                service.address = address
                service.facebook = facebook
                service.firstname = firstname
                service.customtext = customtext
                service.originalemail = originalemail
                services.append(service)
                
            if item['facebookemail2'].strip() != "" and check_blacklisted(item['facebookemail2'].strip()):
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['facebookemail2'].strip(), user_id = current_user.id, file_id=file_id)
                service.website = website
                service.phone = phone
                service.address = address
                service.facebook = facebook
                service.firstname = firstname
                service.customtext = customtext
                service.originalemail = originalemail
                services.append(service)
        
        db.session.bulk_save_objects(services)
        db.session.commit()
        return redirect(url_for('home_blueprint.upload_contact'))
        
        
@blueprint.route('/contact/delete', methods=['POST'])
@login_required
def contact_delete():
    file_id = int(request.form['fileid'])
    file = Uploadedcontactfile.query.get(file_id)
    db.session.delete(file)
    Uploadedservice.query.filter_by(file_id=file_id).delete()
    db.session.commit()
    return redirect(url_for('home_blueprint.upload_contact'))
        
 
@blueprint.route('/contact/<int:id>', methods=['GET'])
@login_required
def view_contact(id):
    userid = current_user.id
    uploaded_file = Uploadedcontactfile.query.filter_by(id=id, user_id=userid).first()

    if uploaded_file:
        file_desc = uploaded_file.description
        return render_template('home/view_contact.html', fileid=id, file_desc=file_desc)
        
    else:
        return render_template('home/page-404.html')
    
@blueprint.route('/masterview', methods=['GET'])
@login_required
def view_all_contact():
    return render_template('home/view_all_contact.html')
        
        
@blueprint.route('/contacts/list/<int:id>', methods=['GET'])
@login_required
def contacts_list(id):
    services = Uploadedservice.query.filter_by(user_id=current_user.id, file_id=id).order_by(Uploadedservice.create_datetime.desc()).all()
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
            'originalemail': service.originalemail
        }
        all_services.append(data)

    return jsonify(all_services)

@blueprint.route('/contacts/all', methods=['GET'])
@login_required
def contacts_all_list():
    services = Uploadedservice.query.filter_by(user_id=current_user.id).order_by(Uploadedservice.create_datetime.desc()).all()
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
            
        }
        all_services.append(data)

    return jsonify(all_services)

     
@blueprint.route('/service/delete', methods=['POST'])
@login_required
def service_delete():
    
    serviceid = request.json['serviceid']
    service = Uploadedservice.query.get(serviceid)
    
    
    if service:
        unsubscribe_token = service.unsubscribe_token
        Email.query.filter_by(unsubscribe_token=unsubscribe_token).delete()
        
        db.session.delete(service)
        
    db.session.commit()
    return {"success": True, 'message': "Service deleted successfully."}


@blueprint.route('/url/view/<int:id>', methods=['GET', 'POST'])
@login_required
def url_view(id):
    yelpurl = Yelpurl.query.get(id)
    return render_template('home/view_url_data.html', segment='history', current_url=yelpurl)
    
@blueprint.route('/url/delete', methods=['POST'])
@login_required
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
    if user_credit:
        credit  = user_credit.credit
    else:
        credit = None
    return render_template('home/profile.html', segment='profile', user_credit=credit)


@blueprint.route('/process_stop/<int:id>')
def process_state(id):
    yelpurl = Yelpurl.query.get(int(id))
    yelpurl.state = "completed"
    db.session.commit()
    return redirect(url_for('home_blueprint.url_view', id=id))


@blueprint.route('/check_state', methods=['POST'])
def check_state():
    id = request.json['id']
    yelpurl = Yelpurl.query.get(int(id))
    return yelpurl.state


def get_segment(request):
    try:
        segment = request.path.split('/')[-1]
        if segment == '':
            segment = 'index'

        return segment

    except:
        return None


def get_all_filters():
    user_urls = Yelpurl.query.filter_by(userid=current_user.id).all()
    return user_urls


def get_all_notifications():
    user_urls = Yelpurl.query.filter_by(userid=current_user.id).all()
    return user_urls


def get_page_data():
    data_filter = get_all_filters()
    data_noti = get_all_notifications()
    page_data = {
        'total_filters': len(data_filter),
        'total_noti': len(data_noti)
    }
    return page_data


def get_admin_data():
    user_urls = Yelpurl.query.all()
    users = Users.query.filter(Users.role != "admin").all()
    services = Service.query.all()

    page_data = {
        'total_filters': len(user_urls),
        'total_users': len(users),
        'services': len(services)
    }
    return page_data


def lets_start(urls, user_id, id):
    process = multiprocessing.Process(target=starting,
                                      args=(urls, user_id, id))
    process.start()

    process.join()


def starting(urls, user_id, id):
    if len(urls) > 0:
        
        WEB_HOST_IP = os.getenv("WEB_HOST_IP")
        for url in urls:
            yelp_scraper_run(url, user_id, id)
        
        response = requests.post(f'{WEB_HOST_IP}/complete', json={'id': id})
        response = requests.post(f'{WEB_HOST_IP}/msg', json={'result': "completed", 'id' : id, 'user_id' : user_id})
        print("Processes", response.text)


@blueprint.route('/admin/register', methods=['POST'])
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
    return render_template("home/admin_users.html",
                           segment='users', API_GENERATOR=len(API_GENERATOR),
                           page_data=page_data,
                           users=users
                           )


@blueprint.route('/admin/users_credit', methods=['GET'])
@login_required
@role_required('admin')
def admin_users_credit():
    return render_template("home/admin_users_credit.html", segment='users_credit')


@blueprint.route('/admin/get_users_credit', methods=['GET'])
@login_required
@role_required('admin')
def get_users_credit():
    # users = Users.query.filter(Users.role != "admin").join(UserCredit, UserCredit.userid == Users.id, isouter=False).all()

    users = db.session.query(Users, UserCredit).filter(Users.role == "lite").join(UserCredit, Users.id == UserCredit.userid, isouter=False).all()
    user_list = []

    for user in users:
        user_data = {
            'id': user[0].id,
            'username': user[0].username,
            'email': user[0].email,
            'update_datetime': user[1].update_datetime,
            'credit': user[1].credit
        }
        user_list.append(user_data)

    return jsonify(user_list)

@blueprint.route('/admin/update/credit', methods=['POST'])
@login_required 
@role_required('admin')
def update_credit():
    userid = request.form['userid']
    user_credit = request.form['user-credit']
    
    if userid:
        temp = UserCredit.query.filter(UserCredit.userid == userid).first()
        temp.credit = user_credit

        credited_services = Service.query.filter_by(user_id = userid, is_credited = 1).count()

        if int(user_credit) < credited_services:
            limit = credited_services - user_credit
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

    # User initial credit = 30
    user_initial_credit = 30

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


@blueprint.route('/update/workflowstatus', methods=['POST'])
@login_required 
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
def workflow_delete():
    templateid = request.json['workflowid']
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
    tempid = int(request.form['tempid'])
    tid = request.form['tid']
    action = Action.query.get(actionid)
    db.session.delete(action)
    
    db.session.commit()
    return redirect(url_for('home_blueprint.template_view', tid=tid))


@blueprint.route('/action/delete', methods=['POST'])
@login_required
def action_delete():
    actionid = request.json['actionid']
    automations = Automation.query.filter((Automation.action_id == actionid) & (Automation.status != "completed")).all()
    
    if len(automations) > 0:
        return {"success": False, "message": "This action is already used in automation."}
    
    action = Action.query.get(actionid)
    db.session.delete(action)
    db.session.commit()
    return {"success": True, "message": "Action deleted successfully."}
    
       
@blueprint.route('/myworkflow', methods=['POST', 'GET'])
@login_required 
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


@blueprint.route('/get_workflows', methods=['GET', 'POST'])
@login_required
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
            temp_data = {
                'id': temp.id,
                'description': temp.description,
                'create_datetime' : temp.create_datetime
            }
            contacts_list.append(temp_data)
            
        data = {
            "templates" : temp_list,
            "contacts" : contacts_list
        }
        
        return jsonify(data)


@blueprint.route('/import/workflow', methods=['POST'])
@login_required
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
    
    db.session.bulk_save_objects(new_actions)
    db.session.commit()
    return redirect(url_for('home_blueprint.my_workflow'))


@blueprint.route('/update/workflow', methods=['POST'])
@login_required 
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
    
    SENDER_MAIL = os.environ.get('SENDER_MAIL')
    
    jinja_temp = JT(action.message)
    mail_body = jinja_temp.render(test_service)
    
    if send_test_email(action.subject , action.fromname, mail_body, SENDER_MAIL, SENDER_MAIL):
        return {"success": True}
    
    else:
        return {"success": False}
    

@blueprint.route('/action/test', methods=['POST'])
@login_required 
def action_test():
    
    actionid = request.json['id']
    action = Action.query.filter_by(id=actionid).first()
    
    test_service = {
        "venue" : "Servcie Name",
        "unsubscribe_link" : "unsubscribe_link",
        "firstname" : "firstname",
        "customtext" : "customtext",
        "originalemail" : "originalemail"
    }
    
    receiver = current_user.email
    
    try:
        jinja_temp = JT(action.message)
        mail_body = jinja_temp.render(test_service)
        
        client = APIClient(
            client_id=current_app.config["NYLAS_OAUTH_CLIENT_ID"],
            client_secret=current_app.config["NYLAS_OAUTH_CLIENT_SECRET"],
            access_token=current_user.nylas_access_token,
        )
        
        if send_email_via_nylas(client, action.subject , "Servcie Name",  current_user.email, action.fromname,  mail_body, receiver):
            return {"success": True}

        else:
            return {"success": False, "message": "Please check Nylas API"}
        
    except Exception as e:
        print(repr(e))
        return {"success": False, "message": str(e)}
    

@blueprint.route('/action/get', methods=['POST'])
@login_required 
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

    
    
@blueprint.route('/webhook', methods=['POST', "GET"])
def webhook():
    if request.method == "GET" : 
        # Verify webhooks on nylas settings 
        challenge = request.args['challenge']
        return challenge
    
    else:
        # print(request.json)
        # pprint.pprint(request.json)
        
        event_type = request.json['deltas'][0]['type']
        
        if event_type == "message.opened":
            message_id = request.json['deltas'][0]['object_data']['metadata']['message_id']
            email = Email.query.filter_by(mail_id=message_id).first()
            if email:
                email.is_opened = 1
                db.session.commit()
            
        elif event_type == "thread.replied":
            message_id = request.json['deltas'][0]['object_data']['metadata']['reply_to_message_id']
            email = Email.query.filter_by(mail_id=message_id).first()
            if email:
                email.is_replied = 1
                db.session.commit()
        
        return "okay"


   
@blueprint.route('/automation', methods=['POST', 'GET'])
@login_required 
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
        
        return render_template('home/campaigns.html', segment="campaigns")
    
    
@blueprint.route('/create/campaign', methods=['POST'])
@login_required 
def create_campaign():
    
    workflow_id = request.json['workflow_id']
    contactfile_id = request.json['contactfile_id']
    # number of emails in a Group is 150 , so we need to divide emails into groups
    group_size = 150
    
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
        
    group_count =  len(services) // group_size
    if len(services ) % group_size != 0:
        group_count += 1
    
    groups = []
    emails = []
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
                "args" : (current_user.nylas_access_token, action.id, group.job_id, current_user.email)
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
    
    db.session.add(campaign)
    db.session.bulk_save_objects(groups)
    db.session.bulk_save_objects(emails)
    db.session.commit()
    
    return {"success": True, "message": "Campaign created successfully. It will start on the scheduled time."}


@blueprint.route('/get_campaigns', methods=['GET'])
@login_required
def get_campaigns():
    userid = current_user.id
    campaigns = Campaign.query.filter_by(userid=userid).order_by(Campaign.create_datetime.desc()).all()
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
def get_automations(campaignid):
    userid = current_user.id
    # print('get_automations', campaignid)
    automations = Automation.query.filter_by(userid=userid, campaignid=campaignid).all()
    temp_list = []

    for temp in automations:
        temp_data = {
            'id': temp.id,
            'action_nanme': temp.action_name,
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
def camp_delete():
    id = request.json['campid']
    camp = Campaign.query.get(id)
    
    if camp:
        campid = camp.campaignid
        db.session.delete(camp)
        
    automations = Automation.query.filter_by(campaignid=campid).all()
    
    for automation in automations:
        jobid = automation.job_id
        db.session.delete(automation)
        Email.query.filter_by(job_id=jobid).delete()
        
        if scheduler.get_job(jobid):
            scheduler.remove_job(jobid)
        
    db.session.commit()
    return {"success": True, 'message': "Campaign deleted successfully."}


@blueprint.route('/automation/delete', methods=['POST'])
@login_required 
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


@blueprint.route('/automation/retry', methods=['POST'])
@login_required 
def job_retry():
    try:
        jobid = request.json['jobid']
        job = Automation.query.filter_by(job_id=jobid).first()
        job.status = "pending"
        
        emails = Email.query.filter_by(job_id=jobid).all()

        for email in emails:
            email.is_sent = 0
            email.is_opened = 0
            email.is_unsubscribed = 0
            email.is_replied = 0
        
        job_starttime = datetime.datetime.now() + timedelta(seconds=30)
        job_start_utctime = datetime.datetime.utcnow() + timedelta(seconds=30)
        job.action_datetime = job_start_utctime

        action_id = job.action_id

        job = {
            "id" : jobid,
            'trigger' : 'date',
            "run_date" : job_starttime.strftime("%Y-%m-%d %H:%M:%S"),
            "func" : "jobs:email_automation_job",
            "args" : (current_user.nylas_access_token, action_id, jobid, current_user.email)
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
    


@blueprint.route('/campaign/view/<campaignid>', methods=['GET'])
@login_required 
def campaign_view(campaignid):
    # print("campaignid", campaignid)
    return render_template('home/view_campaign.html', campaignid=campaignid )


@blueprint.route('/automation/view/<jobid>', methods=['GET'])
@login_required 
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
    emails = Email.query.filter_by(job_id=jobid).all()
    temp_list = []

    for email in emails:
        
        temp_data = {
            'id': email.id,
            'email': email.email,
            'is_sent': email.is_sent,
            'is_opened': email.is_opened,
            'is_unsubscribed' : email.is_unsubscribed,
            'is_replied' : email.is_replied,
            'updated_datetime' : email.updated_datetime,
            'unsubscribe_token' : email.unsubscribe_token
        }
        temp_list.append(temp_data)
        
    return jsonify(temp_list)


@blueprint.route('/unsubscribe/choose', methods=['GET'])
def unsubscribe_choose():
    id = request.args.get('_id')
    token = request.args.get('token')
    WEB_HOST_IP = os.getenv("WEB_HOST_IP")
    return render_template('home/unsubscribe_choose.html', token=token, domain=WEB_HOST_IP, id=id)


@blueprint.route('/unsubscribe/all', methods=['GET'])
def unsubscribe_all():

    token = request.args.get('token')
    id = request.args.get('_id')

    emails = Email.query.filter_by(unsubscribe_token=token).all()
    service = Uploadedservice.query.filter_by(unsubscribe_token=token).first()
    
    try:
        for email in emails:
            email.is_unsubscribed = 1
        
        if service:
            service.is_unsubscribed = 1
            address = service.address
            if address:
                # Unsubscribe all emails from this address : same business
                services = Uploadedservice.query.filter_by(address=address, user_id = id).all()
                for service in services:
                    # Unsubscribe all service with this address
                    service.is_unsubscribed = 1
                    
                    # Unsubscribe all emails from campaigns
                    unsubscribe_token = service.unsubscribe_token
                    email = Email.query.filter_by(unsubscribe_token=unsubscribe_token).first()
                    if email:
                        print("unsubscribed", email.email)
                        email.is_unsubscribed = 1
            else:
                phone = service.phone

                if phone:
                    # Unsubscribe all emails from this phone : same business
                    services = Uploadedservice.query.filter_by(phone=phone, user_id = current_user.id).all()
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
    
    except Exception as e:
        print(repr(e))
        return "Something went wrong. Please try again."
    
    return "You have been unsubscribed successfully."

@blueprint.route('/unsubscribe/<token>', methods=['GET'])
def unsubscribe(token):
    emails = Email.query.filter_by(unsubscribe_token=token).all()
    service = Uploadedservice.query.filter_by(unsubscribe_token=token).first()
    
    for email in emails:
        email.is_unsubscribed = 1
    
    if service:
        service.is_unsubscribed = 1
    
    db.session.commit()

    return "You have been unsubscribed successfully."


@blueprint.route('/subscribe/<token>', methods=['GET'])
def subscribe(token):
    emails = Email.query.filter_by(unsubscribe_token=token).all()
    service = Uploadedservice.query.filter_by(unsubscribe_token=token).first()
    
    for email in emails:
        email.is_unsubscribed = 0
    
    if service:
        service.is_unsubscribed = 0
    db.session.commit()
    
    return "You have been subscribed successfully."

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
    return render_template('home/privacy.html', segment="privacy")
