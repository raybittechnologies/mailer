# from scrapy.crawler import CrawlerProcess
# from apps.home.script import  homes
from functools import wraps
import os

from apps.authentication.models import Users
from apps.authentication.util import verify_pass
from apps.home import blueprint
from flask import render_template, request, jsonify, redirect, url_for, current_app
from flask_login import login_required, current_user, logout_user, login_user

from apps.config import API_GENERATOR
import requests
from datetime import datetime
from apps.models import Yelpurl
from apps import db
from run import socketio, emit, send
import multiprocessing
from apps.home.script import yelp_scraper_run
from apps.models import Service

from concurrent.futures import ThreadPoolExecutor
from apps.authentication.forms import LoginForm, CreateAccountForm

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


@socketio.on('message')
def handle_message(data):
    message = data['message']
    socketio.send({'message': message}, broadcast=True)


@blueprint.route('/home')
@login_required
def index():
    page_data = get_page_data()
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
        if not existing_url:
            new_url = Yelpurl(product_url=url, userid=current_user.id, state="idle", name=name)
            db.session.add(new_url)
            db.session.commit()
        else:
            print("already present in db")

        return render_template('home/view_urls.html',
                               segment='history',
                               API_GENERATOR=len(API_GENERATOR),
                               page_data=page_data,
                               data=data
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
    user_urls = Yelpurl.query.filter_by(userid=current_user.id).all()
    url_list = []

    for url_entry in user_urls:
        url_data = {
            'url_id': url_entry.userid,
            'product_url': url_entry.product_url,
            'id': url_entry.id,
            'name': url_entry.name
        }
        url_list.append(url_data)

    return jsonify(url_list)


@blueprint.route('/viwe_url_history/<int:url_id>')
@login_required
def viwe_url_history(url_id):
    user_urls = Service.query.filter_by(user_id=current_user.id, url_id=url_id).all()
    print(user_urls)
    url_list = []
    for url_entry in user_urls:
        url_data = {
            "id": url_entry.id,
            "url": url_entry.url,
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


@blueprint.route('/scrapper/<int:id>', methods=['GET', 'POST'])
@login_required
def scrapper(id):
    obj = Yelpurl.query.get(id)
    obj.state = "running"
    db.session.commit()
    urls = obj.product_url.split(',')
    try:
        executor.submit(lets_start, urls, current_user.username, current_user.id, id)
    except:
        print("something went wrong")
    return redirect(url_for('home_blueprint.scraping', id=id))


@blueprint.route('/complete', methods=['POST'])
def complete_process():
    id = request.json['id']
    yelpurl = Yelpurl.query.get(int(id))
    yelpurl.state = "completed"
    db.session.commit()
    return "Completed"


@blueprint.route('/scraping', methods=['GET', 'POST'])
@login_required
def scraping():
    id = request.args.get('id')
    page_data = get_page_data()
    yelpurl = Yelpurl.query.get(id)
    return render_template('home/fetch_url_data.html', segment='url', API_GENERATOR=len(API_GENERATOR),
                           page_data=page_data,
                           current_url=yelpurl
                           )


@blueprint.route('/url/view/<int:id>', methods=['GET', 'POST'])
@login_required
def url_view(id):
    page_data = get_page_data()
    yelpurl = Yelpurl.query.get(id)
    print(yelpurl)
    return render_template('home/view_url_data.html', segment='url', API_GENERATOR=len(API_GENERATOR),
                           page_data=page_data,
                           current_url=yelpurl
                           )


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
    print(yelpurl.state)
    yelpurl.state = "completed"
    db.session.commit()
    return redirect(url_for('home_blueprint.url_view', id=id))


@blueprint.route('/check_state', methods=['POST'])
def check_state():
    id = request.json['id']
    yelpurl = Yelpurl.query.get(int(id))
    print("Checking Process Status ----------------------------------------------------------", yelpurl.state)
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
        # process = CrawlerProcess({
        #     'USER_AGENT': 'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)'
        # })
        # process.crawl(homes, urls=urls, username=user_name, user_id=user_id, url_id=id)
        # process.start()
        
        WEB_HOST_IP = os.getenv("WEB_HOST_IP")
        print("starting", WEB_HOST_IP)
        for url in urls:
            yelp_scraper_run(url, user_name, user_id, id)
        
        print("process has completed")
        response = requests.post(f'http://{WEB_HOST_IP}/complete', json={'id': id})
        print(response.text)
        response = requests.post(f'http://{WEB_HOST_IP}/msg', json={'result': "completed"})
        # response = requests.post('http://146.190.51.19/msg', json={'result': "completed"})
        print(response.text)


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
        print(email)
        user = Users.query.filter_by(email=email).first()
        print()
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


@blueprint.route('/admin/add/user', methods=['POST', 'GET'])
@login_required
@role_required('admin')
def add_user():
    create_account_form = CreateAccountForm(request.form)
    if request.method == 'POST':
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
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('home_blueprint.admin_users'))
    else:
        return render_template('home/admin_add_user.html',
                               form=create_account_form,
                               segment="add_user"
                               )
