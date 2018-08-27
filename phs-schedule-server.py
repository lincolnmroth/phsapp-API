from flask import Flask, request, jsonify, abort
import urllib.request, json
import os
from bs4 import BeautifulSoup
from fbbot.infra import Session
import requests
from collections import namedtuple
from urllib.parse import urljoin, urlsplit
import re
import pandas as pd
import lxml
from tabulate import tabulate


app = Flask(__name__)


@app.route('/')
def webResponse():
    return 'PHS Scheduler'

@app.route('/getSchedule', methods=['POST'])
def getSchedule():
    username = request.headers.get('username')
    ldappassword = request.headers.get('ldappassword')
    pw = request.headers.get('pw')
    dbpw = request.headers.get('dbpw')
    schedFormat = request.headers.get('format')

    url = 'https://pschool.princetonk12.org/public/home.html'
    rses = requests.Session()
    lp = rses.get(url)
    fd = Session._Session__form_data(lp.text, 'LoginForm', {

        'account': username,
        'pw': pw,
        'ldappassword': ldappassword,
        'dbpw': dbpw,
    }, form_url=url)
    rses.post(fd.post_url, data=fd.params)

    if schedFormat == 'currentYear':
        text = rses.get('https://pschool.princetonk12.org/guardian/studentsched.html').content
    elif schedFormat == 'weekly':
        text = rses.get('https://pschool.princetonk12.org/guardian/studentbellsched.html').content
    elif schedFormat == 'matrix':
        text = rses.get('https://pschool.princetonk12.org/guardian/studentmatrixsched.html').content
    else:
        return 'Invalid schedule type, try currentYear, weekly, or matrix'

    soup = BeautifulSoup(text,'lxml')
    table = soup.find_all('table')[0]
    df = pd.read_html(str(table))

    return jsonify(df[0].to_json(orient='records'))

@app.route('/getLetterDay', methods=['POST'])
def getLetterDay():
    url = 'https://pschool.princetonk12.org/public/home.html'
    rses = requests.Session()
    lp = rses.get(url)

    username = request.headers.get('username')
    ldappassword = request.headers.get('ldappassword')
    pw = request.headers.get('pw')
    dbpw = request.headers.get('dbpw')

    fd = Session._Session__form_data(lp.text, 'LoginForm', {
        'account': username,
        'pw': pw,
        'ldappassword': ldappassword,
        'dbpw': dbpw,
    }, form_url=url)
    rses.post(fd.post_url, data=fd.params)
    text = rses.get('https://pschool.princetonk12.org/guardian/home.html').text
    soup = BeautifulSoup(text, 'html.parser')
    tools = soup.find('ul', attrs={'id': 'tools'})
    date = tools.find_all('li')[1]
    match = re.search(r'\(([A-G])\)', date.text)
    if match:
        return match.group(1)
    else:
        return 'No school today'




class Session:
    FormInfo = namedtuple('FormInfo', ['params', 'post_url'])

    def __init__(self, settings):
        self.settings = settings
        self.req = requests.Session()
        self.req.headers.update({
            'User-Agent': self.settings.user_agent,
        })

    @staticmethod
    def __form_data(text, formid, params, soup=None, form_url=None):
        if type(params) is not dict:
            raise TypeError('Params must be a dict')
        if soup is None:
            soup = BeautifulSoup(text, 'html.parser')
        form = soup.find('form', attrs={'id': formid})
        action = form.attrs.get('action')
        if not urlsplit(action).netloc:
            if form_url is None or not urlsplit(form_url).netloc:
                raise ValueError('kwarg form_url must be specified if form '
                                 'action lacks a host')
            action = urljoin(form_url, action)
        inputs = form.find_all('input') + form.find_all('textarea')
        for i in inputs:
            try:
                name = i.attrs['name']
                type_ = i.attrs['type']
                value = params.get(name)
                if type_ == 'submit':
                    continue
                elif type_ == 'hidden':
                    value = i.attrs['value'] if value is None else value
                elif value is None:
                    raise ValueError('kwarg params dictionary is missing a '
                                     'value for a non-hidden field')
            except KeyError:
                pass
            else:
                params[name] = value
        return Session.FormInfo(params=params, post_url=action)

    def __complete_form(self, form_url, form_id, params, get_params={}):
        page = self.req.get(form_url, params=get_params)
        fd = Session.__form_data(page.text, form_id, params, form_url=form_url)
        self.req.post(fd.post_url, data=fd.params)

    def login(self):
        self.__complete_form(
            'https://mbasic.facebook.com/login.php',
            'login_form',
            {
                'email': self.settings.username,
                'pass': self.settings.password,
            },
        )

    def message(self, user_id, body):
        self.__complete_form(
            'https://mbasic.facebook.com/messages/compose/',
            'composer_form',
            {'body': body},
            get_params={'ids': user_id},
        )
