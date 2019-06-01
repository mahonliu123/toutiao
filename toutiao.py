'''
注意,必须将前三行
import gevent
from gevent import monkey
gevent.monkey.patch_all()

放在所有导入模块语句的最前面,否则会报错
'''
import gevent
from gevent import monkey
gevent.monkey.patch_all()
import requests
import re
from urllib.parse import urlencode
from requests.exceptions import RequestException
import json
import pymongo
from config import *   # 导入mongodb配置文件
from hashlib import md5
import os, time
from selenium import webdriver

# 声明一个MongoDB客户端对象，传入MongoDB的URL地址
client = pymongo.MongoClient(MONGO_URL, connect=False)
# 连接至数据库
db = client[MONGO_DB]

# 请求索引页面的信息，分析网页可得网页为动态Ajax请求，并得到提交的表单数据中只有offset关键字是按规律变化的
# 为了得到更多的ajax请求，将offset参数传入函数。由于关键字keyword为要搜索的内容，如街拍，将该参数也传入
# 函数，得到更为广泛地应用。
def get_page_index(offset, keyword):
    # 实验证明不加请求头信息，会被拒绝请求。
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36",
        'x-requested-with': 'XMLHttpRequest'
    }
    # 在ajax请求中的表单提交信息
    # timestamp = int(round(time.time()*1000))
    data = {
        # 'aid': 24,
        # 'app_name': 'web_search',
        'offset': offset,
        # 'format': 'json',
        'keyword': keyword,
        # 'autoload': 'true',
        # 'count': 20,
        # 'en_qc': 1,
        # 'cur_tab': 1,
        # 'from': 'search_tab',
        # 'pd': 'synthesis',
        # 'timestamp': timestamp
    }
    # 将data数据编码后得到确切的索引页URL
    url = 'https://www.toutiao.com/api/search/content/?' + urlencode(data)
    # 请求索引页并返回索引页html，若请求失败，则打印自定义错误信息
    # 'https: // www.toutiao.com / api / search / content /?aid = 24 & app_name = web_search & offset = 0 & format = json & keyword = % E8 % A1 % 97 % E6 % 8B % 8D & autoload = true & count = 20 & en_qc = 1 & cur_tab = 1 &from=search_tab & pd = synthesi & timestamp = 1557321206115'
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        return None
    except RequestException:
        print('请求索引页失败')
        return None

# 解析索引页信息
def parse_page_index(html):
    # 由于索引页是ajax加载的，所以返回的信息为json格式数据，因此将该数据转化为json变量
    data = json.loads(html)
    print(data)
    # 如果data存在，且'data'存在于data的键中，则遍历data中键为'data'的值，并从中得到键为'article_url'的值
    if data and 'data' in data.keys():
        for item in data.get('data'):
            yield item.get('article_url')

# 请求详情页信息, 将从索引页得到的详情页的url传入如下函数, 同样需要传入请求头headers, 并返回详情页信息
def get_page_detail(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36",
        'x-requested-with': 'XMLHttpRequest'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        return None
    except RequestException:
        print('请求详情页失败')
        return None

# 解析详情页信息, 得到想要的数据, 分析返回的Response, 得到需要的图片信息放在键为gallery的json数据中
def parse_page_detail(html, url):
    try:
        # 用正则表达式提取需要的数据，由于得到的数据中由很多'\'插入其中,所以使用replace方法去除
        data = re.search(r'gallery: JSON.parse(.*?)siblingList', html, re.S).group(1).replace('\\', '').strip()[2:-3]
        title = re.search(r'title: (.*?)isOriginal', html, re.S).group(1).strip()[1:-2]
        data_detail = json.loads(data)
        if data_detail and 'sub_images' in data_detail.keys():
            images = [finalitem.get('url') for finalitem in data_detail.get('sub_images')]
            return {
            'title': title,
            'url': url,
            'images':images,
        }
    except:
        print('无匹配对象')

# 将数据储存至mongodb数据库中
def save_to_mongo(result):
    # 向表单中插入数据并打印结果
    if db[MONGO_TABLE].insert_one(result):
        print('储存至mongodb成功', result)
        return True
    else:
        return False

# 将所需图片下载下来
def download_images(images_url):
    print('正在下载:', images_url)
    try:
        response = requests.get(images_url)
        if response.status_code == 200:
            save_images(response.content)
        return None
    except RequestException:
        print('请求图片失败')
        return None

# 将图片写入文件中
def save_images(images_content):
    # 写入的文件路径为当前路径, 并且过滤重复的图片
    file_path = '{0}/{1}.{2}'.format(os.getcwd(), md5(images_content).hexdigest(), 'jpg')
    # 若当前路径不存在该文件名, 则创建该文件并写入
    if not os.path.exists(file_path):
        with open(file_path, 'wb') as f:
            f.write(images_content)

# 将请求索引页的函数的参数传入主函数main中, 以备后面的多协程并发提高爬取速度
def main(offset, keyword):
        html = get_page_index(offset, keyword)
        # print(html)
        # print(parse_page_index(html))
        for url in parse_page_index(html):
            if url:
                # print(url)
                detail_html = get_page_detail(url)
                if detail_html:
                    images = parse_page_detail(detail_html, url)
                    if images:
                        for image in images.get('images'):
                            download_images(image)
                        save_to_mongo(images)

if __name__ == '__main__':
    # 爬取10页索引页内容,将所有offset值放入列表中
    offsets = [x * 20 for x in range(10)]
    '''
    定义协程的结构，和数量
    注意, 这里不能定义太多协程, 如10个
    否则会因爬取速度太快而被网站屏蔽
    '''
    xclist = [[], [], [], [], []]
    N = len(xclist)
    # 将10个offset平均分配给这5个协程，每个协程内2个offset，也就是说每个协程爬取2个索引页
    for i in range(len(offsets)):
        xclist[i % N].append(offsets[i])
    # 定义一个协程任务列表
    tasklist = []
    # 由于每个协程中有2个offset, 所以需要逐一遍历取出
    for x in range(2):
        for i in range(N):
            tasklist.append(gevent.spawn(main, xclist[i][x], '街拍'))
    gevent.joinall(tasklist)

