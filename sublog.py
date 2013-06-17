#coding=utf-8

#TODO
#添加发布时候的重试
#测试在没有session的情况下是否第一次发布的时候会报错
#不明觉厉的str和unicode，encode和decode
#密码加密
#发表摘要到微博
#init初始化ServerProxy会输出错误信息，但是却可以正常工作
#Traceback (most recent call last):
    #  File ".\sublime_plugin.py", line 71, in reload_plugin
    #  File ".\xmlrpclib.py", line 1199, in __call__
    #  File ".\xmlrpclib.py", line 1489, in __request
    #  File ".\xmlrpclib.py", line 1253, in request
    #  File ".\xmlrpclib.py", line 1392, in _parse_response
    #  File ".\xmlrpclib.py", line 838, in close
    #xmlrpclib.Fault: <Fault 0: 'unsupported method called: __bases__.__nonzero__'>
#每次重新加载这个插件，就会再补全列表里加上一次分类的重复

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "markdown"))
import markdown

import traceback
import threading
from xmlrpclib import ServerProxy, Error
import HTMLParser
from itertools import groupby
from operator import itemgetter
import xmlrpclib
import json

import sublime
import sublime_plugin

global cats
global login_name
global login_password
global server

def init():
    global cats
    global login_name
    global login_password
    global server

    login_name = get_login_name()
    login_password = get_login_password()
    url = get_xml_rpc_url()
    server = ServerProxy(url)
    get_cats_async()

def get_cats_async():
    t = threading.Thread(target=get_cats)
    t.start()
    handle_thread(t, "Geting cats")

def get_cats():
    global cats
    try:
        result = server.metaWeblog.getCategories("", login_name, login_password)
        status("Successful", True)
        cats = []
        for item in result:
            cat = (strip_title(item["title"]) + "\t" + u"博客分类",
            strip_title(item["description"]))
            cats.append(cat)
            
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        errorMsg = 'Error: %s' % e
        status(errorMsg, True)

def strip_title(title):
    if title.startswith(u"[随笔分类]"):
        title = title[6:]
    return title

def status(msg, thread=False):
    if not thread:
        sublime.status_message(msg)
    else:
        sublime.set_timeout(lambda: status(msg), 0)

def update_blog_info(view, blog_info):
    sublime.set_timeout(lambda: do_update_blog_info(view, blog_info), 0)

def do_update_blog_info(view, blog_info):
    blog_info_str = dump_in_str(blog_info)
    edit = view.begin_edit()
    view.replace(edit, view.line(0), "#blog %s" % blog_info_str)
    view.end_edit(edit)

def load_in_str(str):
    obj = json.loads(str)
    for key in obj.keys():
        obj[key] = obj[key].encode('utf-8')
    return obj

def dump_in_str(obj):
    str = "{";
    keys = obj.keys()
    for i in range(0, len(keys) - 1):
        key = keys[i]
        str += '"%s": "%s", ' % (key, obj[key].decode('utf-8'))
    key = keys[-1]
    str += '"%s": "%s"' % (key, obj[key].decode('utf-8'))
    str += "}"
    return str

def handle_thread(thread, msg=None, cb=None, i=0, direction=1, width=8):
    if thread.is_alive():
        next = i + direction
        if next > width:
            direction = -1
        elif next < 0:
            direction = 1
        bar = [' '] * (width + 1)
        bar[i] = '='
        i += direction
        status('%s [%s]' % (msg, ''.join(bar)))
        sublime.set_timeout(lambda: handle_thread(thread, msg, cb, i,
                            direction, width), 100)
    elif not (cb == None):
        cb()

def get_login_name():
    settings = sublime.load_settings('meetrice.sublime-settings')
    login_name = settings.get('login_name')

    if not login_name:
        sublime.error_message("No Login name found in settings")

    return login_name

def get_login_password():
    settings = sublime.load_settings('meetrice.sublime-settings')
    login_password = settings.get('login_password')

    if not login_password:
        sublime.error_message("No login_password found in settings")

    return login_password

def get_xml_rpc_url():
    settings = sublime.load_settings('meetrice.sublime-settings')
    xml_rpc_url = settings.get('xml_rpc_url')

    if not xml_rpc_url:
        sublime.error_message("No login_password found in settings")

    return xml_rpc_url

init()

class SublogPlugin(sublime_plugin.EventListener):
    def on_query_completions(self, view, prefix, locations):
        #如果当前是在第一行，准备插入分类才触发
        current_file = view.file_name()
        if '.md' in current_file:
            first_line = view.line(0)
            if locations[0] >= first_line.begin() and locations[0] <= first_line.end():
                return cats

class GetCatsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        get_cats_async()

class BlogInfoCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.insert(edit, 0, '#blog {"title":"", "category":"", "tags":"", "publish":"false"}\r\n\r\n\r\n\r\n# Goal of this Article\r\n\r\n\r\n\r\n# Conclusions\r\n\r\n')

class TipCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        status(u"中国", False)

class PublishCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if not (self.get_blog_info()):
            status("Please config blog info")
            return

        if not (self.blog_info.has_key("title")):
            status("Please set title")
            return

        if not (self.get_blog_content()):
            status("Content may not be empty")
            return

        self.post = { 'title': self.blog_info['title'],
                'description': self.markdown2html(self.blog_content),
                'link': '',
                'author': login_name,
                "categories": [self.blog_info['category']],
                "mt_keywords": self.blog_info['tags']
            }
        self.publish_async()

    def get_blog_info(self):
        first_line = self.view.substr(self.view.line(0))
        if first_line.startswith("#blog"):
            first_line = first_line.replace("#blog", "")
            first_line = first_line.lstrip()
            self.blog_info = load_in_str(first_line)
            return True
        else:
            return False

    def get_blog_content(self):
        first_line_region = self.view.line(0)
        begin = first_line_region.end() + 1
        end = self.view.size()
        if end > begin:
            self.blog_content = self.view.substr(sublime.Region(begin, end))
            return True
        else:
            return False

    def publish_async(self):
        t = threading.Thread(target=self.publish)
        t.start()
        handle_thread(t, 'Publishing ...')

    def markdown2html(self, content):
        html = markdown.markdown(content)
        return html

    def publish(self):
        try:
            if self.blog_info.has_key("blog_id"):
                print "edit post"
                result = server.metaWeblog.editPost(self.blog_info["blog_id"], login_name, login_password, self.post, self.blog_info["publish"] == "true")
                if result:
                    status('Successful', True)
                else:
                    status('Error', True)
            else:
                print "new post"
                result = server.metaWeblog.newPost("", login_name, login_password, self.post, self.blog_info["publish"] == "true")
                if len(result) > 0:
                    self.blog_info["blog_id"] = result
                    update_blog_info(self.view, self.blog_info)
                    status('Successful', True)
                else:
                    status('Error', True)
        except xmlrpclib.Fault as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_traceback)
            errorMsg = 'Error: %s' % e.faultString
            status(errorMsg, True)
