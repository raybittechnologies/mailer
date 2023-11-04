# from scrapy.crawler import CrawlerProcess
# from apps.home.script import  homes
from functools import wraps
import os

from apps.authentication.models import Users
from apps.authentication.util import verify_pass
from apps.home import blueprint
from flask import render_template, request, jsonify, redirect, url_for, current_app
from flask_login import login_required, current_user, logout_user, login_user
from jinja2 import Template as JT

from apps.config import API_GENERATOR
import requests
from datetime import datetime
from apps.models import Yelpurl
from apps import db
import multiprocessing
from apps.home.script import yelp_scraper_run
from apps.models import *
from sqlalchemy import desc, asc
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import Insert

from concurrent.futures import ThreadPoolExecutor
from apps.authentication.forms import LoginForm, CreateAccountForm
from flask_dance.contrib.nylas import nylas
from apps.home.emailler import send_test_email, user_test_email

import pandas as pd

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
            
            return redirect(url_for('authentication_blueprint.login')) 
            
        
    return render_template('home/index.html', segment='index', API_GENERATOR=len(API_GENERATOR),
                           page_data=page_data
                           )


@blueprint.route('/add/url')
@login_required
def add_filter():
    page_data = get_page_data()
    return render_template('home/add_url.html', segment='index', API_GENERATOR=len(API_GENERATOR),
                           page_data=page_data
                           )


@compiles(Insert, "sqlite")
def sqlite_insert_ignore(insert, compiler, **kw):
    return compiler.visit_insert(insert.prefix_with("OR IGNORE"), **kw)

@blueprint.route('/url', methods=['POST', 'GET'])
@login_required
def url():
    if request.method == 'POST':
        url = request.form['url']
        name = request.form['name']
        page_data = get_page_data()
        data = {
            'url': url
        }
        existing_url = Yelpurl.query.filter_by(product_url=url, userid=current_user.id).first()
        if existing_url is None:
            new_url = Yelpurl(product_url=url, userid=current_user.id, state="idle", name=name)
            db.session.add(new_url)
            db.session.commit()
            
            existing_url = Yelpurl.query.filter_by(product_url=url, userid=current_user.id).first()
            url_id = existing_url.id
            
            return redirect(url_for('home_blueprint.fetch', id=url_id))
            
        else:
            
            print("already present in db")
            message = "This url is already reistered."
            return render_template('home/view_urls.html',
                                segment='history',
                                API_GENERATOR=len(API_GENERATOR),
                                page_data=page_data,
                                data=data,
                                message=message
                                )
    else:
        page_data = get_page_data()
        data = {
            'url': "",
            'name': ""
        }
        return render_template('home/add_url.html',
                               segment='url',
                               API_GENERATOR=len(API_GENERATOR),
                               page_data=page_data,
                               data=data
                               )


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


@blueprint.route('/viwe_url_history/<int:url_id>')
@login_required
def viwe_url_history(url_id):
    user_urls = Service.query.filter_by(url_id=url_id, user_id=current_user.id).all()
    # print(user_urls)
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
    page_data = get_page_data()
    return render_template('home/view_urls.html', segment='history', API_GENERATOR=len(API_GENERATOR),
                           page_data=page_data)


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
            executor.submit(lets_start, urls, current_user.username, current_user.id, id)
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
    page_data = get_page_data()
    yelpurl = Yelpurl.query.get(id)
    
    if yelpurl.state == "running":
        return render_template('home/fetch_url_data.html', segment='url', API_GENERATOR=len(API_GENERATOR),
                            page_data=page_data,
                            current_url=yelpurl
                            )
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
        return render_template('home/upload_contact.html',
                                segment='upload_contact',
                                API_GENERATOR=len(API_GENERATOR),
                                )
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
            venue = item['venue']
            venue_type = item['type']
            
            if item['email1'] != "":
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['email1'], user_id = current_user.id, file_id=file_id)
                services.append(service)
                
            if item['email2'] != "":
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['email2'], user_id = current_user.id, file_id=file_id)
                services.append(service)
                
            if item['email3'] != "":
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['email3'], user_id = current_user.id, file_id=file_id)
                services.append(service)
                
            if item['email4'] != "":
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['email4'], user_id = current_user.id, file_id=file_id)
                services.append(service)
                
            if item['facebookemail1'] != "":
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['facebookemail1'], user_id = current_user.id, file_id=file_id)
                services.append(service)
                
            if item['facebookemail2'] != "":
                service = Uploadedservice(name=venue, venue_type=venue_type, email=item['facebookemail2'], user_id = current_user.id, file_id=file_id)
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
    
    sevices = Uploadedservice.query.filter_by(file_id=file_id).all()
    for service in sevices:
        db.session.delete(service)
        
    db.session.commit()
    return redirect(url_for('home_blueprint.upload_contact'))
        
 
@blueprint.route('/contacts', methods=['GET', 'POST'])
@login_required
def contacts():
    if request.method == "GET":
        return render_template('home/contacts.html',
                                segment='contacts',
                                )
@blueprint.route('/contacts/list', methods=['GET'])
@login_required
def contacts_list():
    services = Uploadedservice.query.filter_by(user_id=current_user.id).order_by(Uploadedservice.create_datetime.desc()).all()
    all_services = []

    for service in services:
        data = {
            'id': service.id,
            'name': service.name,
            'venue_type': service.venue_type,
            'email': service.email,
            'is_bad' : service.is_bad,
            'create_datetime' : service.create_datetime
        }
        all_services.append(data)

    return jsonify(all_services)
     
@blueprint.route('/service/delete', methods=['POST'])
@login_required
def service_delete():
    serviceid = int(request.form['serviceid'])
    service = Uploadedservice.query.get(serviceid)
    db.session.delete(service)
    
    db.session.commit()
    return redirect(url_for('home_blueprint.contacts'))


@blueprint.route('/url/view/<int:id>', methods=['GET', 'POST'])
@login_required
def url_view(id):
    page_data = get_page_data()
    yelpurl = Yelpurl.query.get(id)
    return render_template('home/view_url_data.html', segment='url', API_GENERATOR=len(API_GENERATOR),
                           page_data=page_data,
                           current_url=yelpurl
                           )
    
@blueprint.route('/url/delete', methods=['POST'])
@login_required
def url_delete():
    url_id = int(request.form['urlid'])
    yelpurl = Yelpurl.query.get(url_id)
    sevices = Service.query.filter_by(url_id=url_id).all()
    for service in sevices:
        db.session.delete(service)
    db.session.delete(yelpurl)
    
    db.session.commit()
    return redirect(url_for('home_blueprint.history'))
    

@blueprint.route('/profile')
@login_required
def profile():
    page_data = get_page_data()
    return render_template('home/profile.html', segment='rem-process', API_GENERATOR=len(API_GENERATOR),
                           page_data=page_data
                           )


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


def lets_start(urls, user_name, user_id, id):
    process = multiprocessing.Process(target=starting,
                                      args=(urls, user_name, user_id, id))
    process.start()

    process.join()


def starting(urls, user_name, user_id, id):
    if len(urls) > 0:
        
        WEB_HOST_IP = os.getenv("WEB_HOST_IP")
        for url in urls:
            yelp_scraper_run(url, user_name, user_id, id)
        
        response = requests.post(f'{WEB_HOST_IP}/complete', json={'id': id})
        response = requests.post(f'{WEB_HOST_IP}/msg', json={'result': "completed", 'id' : id, 'user_id' : user_id})
        print("Processes", response.text)


@blueprint.route('/admin/register', methods=['POST'])
def register():
    username = request.json.get('name')
    email = request.json.get('email')
    password = request.json.get('password')
    role = request.json.get('role', 'user')

    if not username or not email or not password or not role:
        return jsonify({'message': 'Missing required fields'}), 400

    user = Users.query.filter_by(username=username).first()
    if user:
        return jsonify({'message': 'Username already registered'}), 400

    # Check email exists
    user = Users.query.filter_by(email=email).first()
    if user:
        return jsonify({'message': 'Email already registered'}), 400

    # else we can create the user
    user = Users(username=username, email=email, password=password, role=role)
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'User registered successfully'}), 201


@blueprint.route('/admin/login', methods=['POST', 'GET'])
def admin_login():
    logout_user()
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = Users.query.filter_by(email=email).first()
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
    users = Users.query.filter(Users.role != "admin").all()
    return render_template("home/admin_users.html",
                           segment='users', API_GENERATOR=len(API_GENERATOR),
                           page_data=page_data,
                           users=users
                           )


@blueprint.route('/admin/profile', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def admin_profile():
    return render_template("home/admin_profile.html",
                           segment='users', API_GENERATOR=len(API_GENERATOR),
                           )


@blueprint.route('/admin/users/delete/<id>', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def delete_user(id):
    user = Users.query.get(id)
    if user:
        db.session.delete(user)
        services = Service.query.filter_by(user_id=id).all()
        for service in services:
            db.session.delete(service)
        urls = Yelpurl.query.filter_by(userid=id).all()
        for url__ in urls:
            db.session.delete(url__)
        db.session.commit()
    page_data = get_admin_data()
    users = Users.query.filter(Users.role != "admin").all()
    return redirect(url_for("home_blueprint.admin_users",
                            segment='users', API_GENERATOR=len(API_GENERATOR),
                            page_data=page_data,
                            users=users,
                            ))
    
@blueprint.route('/admin/users/approve/<id>', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def approve_user(id):
    user = Users.query.get(id)
    user.state = "approved"
    db.session.add(user)
    db.session.commit()
    page_data = get_admin_data()
    users = Users.query.filter(Users.role != "admin").all()
    return redirect(url_for("home_blueprint.admin_users",
                            segment='users', API_GENERATOR=len(API_GENERATOR),
                            page_data=page_data,
                            users=users,
                            ))
    
@blueprint.route('/admin/users/inactive/<id>', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def inactive_user(id):
    user = Users.query.get(id)
    user.state = "pending"
    db.session.add(user)
    db.session.commit()
    page_data = get_admin_data()
    users = Users.query.filter(Users.role != "admin").all()
    return redirect(url_for("home_blueprint.admin_users",
                            segment='users', API_GENERATOR=len(API_GENERATOR),
                            page_data=page_data,
                            users=users,
                            ))

@blueprint.route('/admin/add/user', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def add_user():
    create_account_form = CreateAccountForm(request.form)
    if request.method == 'POST':
        print(request.form)
        username = request.form['username']
        email = request.form['email']

        # Check username exists
        user = Users.query.filter_by(username=username).first()
        if user:
            return render_template('home/admin_add_user.html',
                                   msg='Username already registered',
                                   success=False,
                                   form=create_account_form,
                                   segment="add_user"
                                   )

        # Check email exists
        user = Users.query.filter_by(email=email).first()
        if user:
            return render_template('home/admin_add_user.html',
                                   msg='Email already registered',
                                   success=False,
                                   form=create_account_form,
                                   segment="add_user"
                                   )

        user = Users(**request.form)
        user.role = "user"
        user.state = "pending"
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('home_blueprint.admin_users'))
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
    
    actions = Action.query.filter_by(tempid=templateid).all()
    for action in actions:
        db.session.delete(action)
    
    db.session.commit()
    return redirect(url_for('home_blueprint.add_template'))


@blueprint.route('/workflow/delete', methods=['POST'])
@login_required
def workflow_delete():
    templateid = int(request.form['workflowid'])
    temp = Template.query.get(templateid)
    db.session.delete(temp)
    
    actions = Action.query.filter_by(tempid=templateid).all()
    for action in actions:
        db.session.delete(action)
    
    db.session.commit()
    
    return redirect(url_for('home_blueprint.my_workflow'))



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
    actions = Action.query.filter_by(tempid=int(id)).order_by(Action.id.asc()).all()
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
    actions = Action.query.filter_by(tempid=int(id)).order_by(Action.id.asc()).all()
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
    actionid = int(request.form['actionid'])
    tempid = int(request.form['tempid'])
    tid = request.form['tid']
    action = Action.query.get(actionid)
    db.session.delete(action)
    
    db.session.commit()
    return redirect(url_for('home_blueprint.workflow_view', tid=tid))
    
       
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
        
        admin = Users.query.filter_by(role='admin').first()
        admin_id = admin.id
        
        templates = Template.query.filter_by(status="publish", userid=admin_id).all()
        template_list = []
        
        for temp in templates:
            data = {
                'id' : temp.id,
                'template_name' : temp.template_name,
                'template_desc' : temp.template_desc,
            }
            template_list.append(data)
        
        return render_template('home/my_workflow.html', segment="myworkflow", template_list=template_list)


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


@blueprint.route('/workflows', methods=['GET'])
@login_required
def get_users_workflow():
    userid = current_user.id
    templates = Template.query.filter_by(userid=userid).order_by(Template.create_datetime.desc()).all()
    temp_list = []

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
        "service_name" : "Servcie Name",
        "company_name" : "Company Name"
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
        "service_name" : "Servcie Name",
        "company_name" : "Company Name"
    }
    
    
    SENDER_MAIL = current_user.email
    
    try:
        jinja_temp = JT(action.message)
        mail_body = jinja_temp.render(test_service)
        if user_test_email(action.subject , action.fromname, mail_body, SENDER_MAIL):
            return {"success": True}

        else:
            return {"success": False, "message": "Please check Nylas api"}
        
    except Exception as e:
        return {"success": False, "message": str(e)}
    
    
    