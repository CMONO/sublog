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
#under ubuntu, print u"xxx" will throw a ascii codec decode error, we should use print u"xxx".encode("utf-8")

import os
from os.path import join
import locale
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "markdown"))
import re  
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
global header_template
global package_path
global sublog_js_path

def init():
    global cats
    global header_template
    global package_path
    global sublog_js_path

    package_path = join(sublime.packages_path(), "sublog")
    sublog_js_path = join(join(package_path, "sublog_js"), "sublog.js")
    header_template = "<!--sublog\n" + "{\n" + "    \"title\":\"%s\",\n" + "    \"category\":\"%s\",\n" + "    \"tags\":\"%s\",\n" + "    \"publish\":\"%s\",\n" + "    \"blog_id\":\"%s\"\n" + "}\n" + "sublog-->"
    #load settings
    get_cats_async()

def get_cats_async():
    settings = sublime.load_settings('sublog.sublime-settings')
    login_name = settings.get('login_name')
    login_password = settings.get('login_password');
    url = settings.get('xml_rpc_url')
    #t = threading.Thread(target=get_cats)
    t = threading.Thread(target=lambda: get_cats(login_name, login_password, url))
    t.start()
    handle_thread(t, "Geting cats")

def get_cats(login_name, login_password, url):
    server = ServerProxy(url)
    global cats
    try:
        result = server.metaWeblog.getCategories("", login_name, login_password)
        status("Successful", True)
        cats = []
        for item in result:
            cat = strip_title(item["title"])
            cats.append(cat)

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        errorMsg = 'Error: %s' % e
        status(errorMsg, True)

def check_unicode(str):
    if(type(str) != type(u"")):
        str = str.decode("utf-8")
    return str

def strip_title(title):
    utitle = check_unicode(title)
    if utitle.startswith(u"[随笔分类]"):
        utitle = utitle[6:]
        description = utitle + "\t" + u"随笔分类"
    elif utitle.startswith(u"「网站分类」"):
        utitle = utitle[6:]
        description = utitle + "\t" + u"网站分类"
    else:
        description = utitle + "\t" + u"博客分类"
    return (description, utitle)

def status(msg, thread=False):
    msg = check_unicode(msg)
    if not thread:
        sublime.status_message(msg)
    else:
        sublime.set_timeout(lambda: status(msg), 0)

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

#加载的时候开始执http://www.cnblogs.com/zhengwenwei/services/metaweblog.aspx行
init()

class SublogPlugin(sublime_plugin.EventListener):
    def on_query_completions(self, view, prefix, locations):
        current_file = view.file_name()
        if '.md' in current_file:
            line = view.substr(view.line(locations[0]))
            if "\"category\":" in line:
                return cats

class GetCatsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        get_cats_async()

class BlogInfoCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        header_str = header_template % ('', '', '', 'false', '')
        self.view.insert(edit, 0, header_str + "\n\n")

class PublishCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if not (self.get_blog_info()):
            status("Please config blog info")
            return

        if not (self.blog_info.has_key("title")):
            status("Please set title")
            return

        settings = sublime.load_settings('sublog.sublime-settings')
        self.current_file = self.view.file_name()
        self.login_name = settings.get('login_name')
        self.login_password = settings.get('login_password');
        self.url = settings.get('xml_rpc_url')
        self.post = { 'title': self.blog_info['title'],
                #'description': self.markdown2html(self.blog_content),
                'description': self.node_markdown2html(),
                'link': '',
                'author': self.login_name,
                "categories": [self.blog_info['category']],
                "mt_keywords": self.blog_info['tags']
            }
        self.publish_async()

    def get_blog_info(self):
        self.get_header_region()
        if not self.header_region:
            return False
        header_str = self.view.substr(self.header_region) 
        if self.is_old_format:
            header_str = header_str.replace("#blog", "")
            header_str = header_str.lstrip()
            self.blog_info = json.loads(header_str)
            #针对 #blog{...}的旧格式进行更新
            if not self.blog_info.has_key("blog_id"):
                self.blog_info["blog_id"] = ""
            header_str = header_template % (self.blog_info['title'],
             self.blog_info['category'],
             self.blog_info['tags'],
             self.blog_info['publish'],
             self.blog_info['blog_id'])
            self.is_old_format = True
            edit = self.view.begin_edit()
            self.view.erase(edit, self.header_region)
            self.view.insert(edit, 0, header_str + "\n\n")
            self.view.end_edit(edit)
            self.get_header_region()
        else:
            pattern = re.compile("<!--sublog(.*?)sublog-->", re.MULTILINE | re.DOTALL)
            match = pattern.match(header_str)
            header = match.group(1)
            self.blog_info = json.loads(header)
        return True

    def get_header_region(self):
        self.is_old_format = False
        first_line = self.view.substr(self.view.line(0))
        if first_line.startswith("#blog"):
            self.header_region = self.view.line(0)
            self.is_old_format = True
        elif first_line.startswith("<!--sublog"):
            self.header_region = self.view.find("<!--sublog((.|\n)*?)sublog-->", 0)
        else:
            self.header_region = None

    def update_blog_info(self):
        sublime.set_timeout(lambda: self.do_update_blog_info(), 0)

    def do_update_blog_info(self):
        header_str = header_template % (self.blog_info['title'],
         self.blog_info['category'],
         self.blog_info['tags'],
         self.blog_info['publish'],
         self.blog_info['blog_id'])
        edit = self.view.begin_edit()
        self.view.replace(edit, self.header_region, header_str)
        self.view.end_edit(edit)

    def publish_async(self):
        t = threading.Thread(target=self.publish)
        t.start()
        handle_thread(t, 'Publishing ...')

    def node_markdown2html(self):
        post_file = self.current_file
        show_ln_str = "false"
        settings = sublime.load_settings('sublog.sublime-settings')
        if settings.has('show_ln'):
            show_ln = settings.get('show_ln');
            if show_ln:
                show_ln_str = "true"
        command = u"node \"%s\" \"%s\" %s" % (sublog_js_path, post_file, show_ln_str)
        p = os.popen(command.encode(locale.getpreferredencoding()))
        str = p.read()
        return str

    def upload_local_images(self, blog_content):
        pattern = re.compile("<img data-sublog=\"image\" src=\"(file://(.*?))\".*?>", re.MULTILINE | re.DOTALL)
        while True:
            m= pattern.search(blog_content)
            if m:
                try:
                    origin = m.group(0)
                    file_url = m.group(1)
                    path = m.group(2)
                    path = path.decode('utf-8')
                    #expand ~ on UNIX like
                    path = os.path.expanduser(path)
                    current_path = os.path.dirname(self.current_file)
                    path = os.path.normpath(join(current_path, path))
                    with open(path.encode(locale.getpreferredencoding()), "rb") as image_file:
                        content = image_file.read()
                    #上传时候使用的名字并没有多大作用
                    image_name = "image.jpg"
                    image_type = "image/jpeg"
                    if path.endswith("gif"):
                        image_name = "image.gif"
                        image_type = "image/gif"
                    elif path.endswith("png"):
                        image_name = "image.png"
                        image_type = "image/png"
                    #name必须带后缀名，否则会提示无效的文件类型；bits虽然接口说要base64，但是反而需要使用原始数据
                    self.media = { 'bits': xmlrpclib.Binary(content), 'name': image_name, 'type': image_type}
                    result = self.server.metaWeblog.newMediaObject("", self.login_name,
                     self.login_password, self.media)
                    if not result:
                        status('Error when uploading %s' % origin, True)
                        return False
                    http_url = result["url"]
                    replaced = origin.replace(file_url, http_url)
                    blog_content = blog_content.replace(origin, replaced)
                    self.post["description"] = blog_content
                    #闭包
                    sublime.set_timeout(lambda file_url=file_url, http_url=http_url: self.update_image_url(file_url, http_url), 0)
                except IOError as e:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    traceback.print_exception(exc_type, exc_value, exc_traceback)
                    errorMsg = 'Error when uploading %s: %s' % (file_url, e)
                    status(errorMsg, True)
                    return False
                except xmlrpclib.Fault as e:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    traceback.print_exception(exc_type, exc_value, exc_traceback)
                    errorMsg = 'Error when uploading %s: %s' % (file_url, e.faultString)
                    status(errorMsg, True)
                    return False
            else:
                return True

    def update_image_url(self, file_url, http_url):
        file_url = file_url.decode('utf-8')
        url_len = len(http_url)
        from_position = 0
        while True:
            region = self.view.find("]\(" + file_url + "\)", from_position)
            if region:
                region = sublime.Region(region.a + 2, region.b - 1)
                edit = self.view.begin_edit()
                self.view.replace(edit, region, http_url)
                self.view.end_edit(edit)
                from_position = region.a + url_len
            else:
                return

    def publish(self):
        try:
            self.server = ServerProxy(self.url)
            #检查是否有需要上传的图片
            if not self.upload_local_images(self.post["description"]):
                return
            if self.blog_info.has_key("blog_id") and self.blog_info["blog_id"] != "":
                print "edit post"
                result = self.server.metaWeblog.editPost(self.blog_info["blog_id"], self.login_name,
                 self.login_password, self.post, self.blog_info["publish"] == "true")
                if result:
                    status('Successful', True)
                else:
                    status('Error', True)
            else:
                print "new post"
                result = self.server.metaWeblog.newPost("", self.login_name, self.login_password,
                 self.post, self.blog_info["publish"] == "true")
                if result:
                    self.blog_info["blog_id"] = result
                    self.update_blog_info()
                    status('Successful', True)
                else:
                    status('Error', True)
        except xmlrpclib.Fault as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_traceback)
            errorMsg = 'Error: %s' % e.faultString
            status(errorMsg, True)
