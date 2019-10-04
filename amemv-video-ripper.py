# -*- coding: utf-8 -*-
import codecs
import copy
import getopt
import hashlib
import json
import os
import re
import sys
import time
import urllib
import random
import shutil
from threading import Thread
from ipaddress import ip_address
from datetime import datetime

from douyin.config import hot_energy_url
from douyin.config import hot_search_url
from douyin.config import hot_video_url
from douyin.utils import fetch

import douyin

import requests
from six.moves import queue as Queue

# Setting timeout
TIMEOUT = 10

# Retry times
RETRY = 5

# Numbers of downloading threads concurrently
THREADS = 2

HEADERS = {
    'accept-encoding': 'gzip, deflate, br',
    'accept-language': 'zh-CN,zh;q=0.9',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'upgrade-insecure-requests': '1',
    'user-agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 Mobile/15A372 Safari/604.1",
}
HEADERS_FAVORITE = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'accept-encoding': 'gzip, deflate, br',
    'accept-language': 'zh-CN,zh;q=0.9',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Linux; U; Android 5.1.1; zh-cn; MI 4S Build/LMY47V) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/53.0.2785.146 Mobile Safari/537.36 XiaoMi/MiuiBrowser/9.1.3',
}

def gen_ip_address():
    rip = ip_address('0.0.0.0')
    while rip.is_private:
        rip = ip_address('.'.join(map(str, (random.randint(0, 255) for _ in range(4)))))
    return rip

def gen_header(default = HEADERS):
    headers = copy.copy(default)
    ip = gen_ip_address()
    headers['X-Real-IP'] = str(ip)
    headers['X-Forwarded-For'] = str(ip)
    return headers

def get_real_address(url):
    if url.find('v.douyin.com') < 0:
        return url
    res = requests.get(url, headers=gen_header(), allow_redirects=False)
    return res.headers['Location'] if res.status_code == 302 else None


def get_dytk(url):
    res = requests.get(url, headers=gen_header())
    if not res:
        return None
    dytk = re.findall("dytk: '(.*)'", res.content.decode('utf-8'))
    if len(dytk):
        return dytk[0]
    return None


def get_hot_video():
    result = fetch(map_hot_func.get(hot_opt))
    # process json data
    video_list = result.get('aweme_list', [])
    return video_list

def is_reach_max_record(current_record):
    return True if max_record is not None and current_record >= max_record else False


def download(medium_type, uri, medium_url, target_folder, newest_folder):

    headers = copy.copy(gen_header())
    file_name = uri
    if medium_type == 'video':
        file_name += '.mp4'
        headers['user-agent'] = 'Aweme/27014 CFNetwork/974.2.1 Darwin/18.0.0'
    elif medium_type == 'image':
        file_name += '.jpg'
        file_name = file_name.replace("/", "-")
    else:
        return

    file_path = os.path.join(target_folder, file_name)
    if os.path.isfile(file_path):
        print(file_name + " is exist at: " + file_path + " so REJECT")
        return

    print("Downloading %s from %s.\n" % (file_name, medium_url))
    # VIDEOID_DICT[VIDEO_ID] = 1  # 记录已经下载的视频
    retry_times = 0
    while retry_times < RETRY:
        try:
            resp = requests.get(medium_url, headers=headers, stream=True, timeout=TIMEOUT)
            if resp.status_code == 403:
                retry_times = RETRY
                print("Access Denied when retrieve %s.\n" % medium_url)
                raise Exception("Access Denied")
            with open(file_path, 'wb') as fh:
                for chunk in resp.iter_content(chunk_size=1024):
                    fh.write(chunk)
            if allow_newest and newest_folder is not None:
                shutil.copy(file_path, newest_folder)
            break
        except:
            pass
        retry_times += 1
    else:
        try:
            os.remove(file_path)
        except OSError:
            pass
        print("Failed to retrieve %s from %s.\n" % (uri, medium_url))
        time.sleep(1)

class DownloadWorker(Thread):
    def __init__(self, queue):
        Thread.__init__(self)
        self.queue = queue

    def run(self):
        while True:
            medium_type, uri, download_url, target_folder, newest_folder = self.queue.get()
            download(medium_type, uri, download_url, target_folder, newest_folder)
            self.queue.task_done()


class CrawlerScheduler(object):

    def __init__(self, items):
        self.numbers = []
        self.challenges = []
        self.musics = []
        self.videos = []
        self.hots = []
        self.url_key = {}
        for i in range(len(items)):
            if isinstance(items[i], dict):
                self.hots = items
                break
            url = get_real_address(items[i])
            self.url_key[url] = items[i].rstrip().lstrip().split('/')[-2]
            if not url:
                continue
            if re.search('share/user', url):
                self.numbers.append(url)
            if re.search('share/challenge', url):
                self.challenges.append(url)
            if re.search('share/music', url):
                self.musics.append(url)
            if re.search('share/video', url):
                self.videos.append(url)

        self.queue = Queue.Queue()
        self.scheduling()

    @staticmethod
    def generateSignature(value):
        p = os.popen('node fuck-byted-acrawler.js %s' % value)
        return p.readlines()[0]

    @staticmethod
    def calculateFileMd5(filename):
        hmd5 = hashlib.md5()
        fp = open(filename, "rb")
        hmd5.update(fp.read())
        return hmd5.hexdigest()

    def scheduling(self):
        for x in range(THREADS):
            worker = DownloadWorker(self.queue)
            worker.daemon = True
            worker.start()
        hot_count = 0
        for url in self.numbers:
            self.download_user_videos(url)
        for url in self.challenges:
            self.download_challenge_videos(url)
        for url in self.musics:
            self.download_music_videos(url)
        for url in self.videos:
            self.download_video(url)
        for aweme in self.hots:
            if is_reach_max_record(hot_count):
                break
            hot_count += 1
            self.download_hot_video(aweme)
            self.queue.join()
            print("\nFinish Downloading All the hot video")

    def download_hot_video(self, aweme):
        current_folder = os.getcwd()
        now = datetime.now().strftime('%Y%m%d')
        target_folder = os.path.join(current_folder, 'download/{}_{}'.format(map_opts.get(hot_opt), now))
        if not os.path.isdir(target_folder):
            os.mkdir(target_folder)
        newest_folder = os.path.join(current_folder, 'download/newest_video_%s' % now)
        if not os.path.isdir(newest_folder):
            os.mkdir(newest_folder)
        # for aweme in aweme_list:
        # video_count += 1
        hostname = urllib.parse.urlparse(aweme['aweme_info']['share_url']).hostname
        aweme['aweme_info']['hostname'] = hostname
        self._join_download_queue(aweme['aweme_info'], target_folder, newest_folder)


    def download_video(self, url):
        video = re.findall(r'share/video/(\d+)', url)
        if not len(video):
            return

        video_id = video[0]
        video_count = self._download_video_media(video_id, url)
        self.queue.join()
        print("\nAweme number %s, video number %s\n\n" %
              (video_id, str(video_count)))
        print("\nFinish Downloading All the videos from %s\n\n" % video_id)

    def download_user_videos(self, url):
        number = re.findall(r'share/user/(\d+)', url)
        if not len(number):
            return
        dytk = get_dytk(url)
        hostname = urllib.parse.urlparse(url).hostname
        if hostname != 't.tiktok.com' and not dytk:
            return
        user_id = number[0]
        video_count = self._download_user_media(user_id, dytk, url)
        self.queue.join()
        print("\nAweme number %s, video number %s\n\n" %
              (user_id, str(video_count)))
        print("\nFinish Downloading All the videos from %s\n\n" % user_id)

    def download_challenge_videos(self, url):
        challenge = re.findall('share/challenge/(\d+)', url)
        if not len(challenge):
            return
        challenges_id = challenge[0]
        video_count = self._download_challenge_media(challenges_id, url)
        self.queue.join()
        print("\nAweme challenge #%s, video number %d\n\n" %
              (challenges_id, video_count))
        print("\nFinish Downloading All the videos from #%s\n\n" % challenges_id)

    def download_music_videos(self, url):
        music = re.findall('share/music/(\d+)', url)
        if not len(music):
            return
        musics_id = music[0]
        video_count = self._download_music_media(musics_id, url)
        self.queue.join()
        print("\nAweme music @%s, video number %d\n\n" %
              (musics_id, video_count))
        print("\nFinish Downloading All the videos from @%s\n\n" % musics_id)

    def _join_download_queue(self, aweme, target_folder, newest_folder=None):
        try:
            if aweme.get('video', None):
                uri = aweme['video']['play_addr']['uri']
                download_url = "https://aweme.snssdk.com/aweme/v1/play/?{0}"
                download_params = {
                    'video_id': uri,
                    'line': '0',
                    'ratio': '720p',
                    'media_type': '4',
                    'vr_type': '0',
                    'test_cdn': 'None',
                    'improve_bitrate': '0',
                }
                if aweme.get('hostname') == 't.tiktok.com':
                    download_url = 'http://api.tiktokv.com/aweme/v1/play/?{0}'
                    download_params = {
                        'video_id': uri,
                        'line': '0',
                        'ratio': '720p',
                        'media_type': '4',
                        'vr_type': '0',
                        'test_cdn': 'None',
                        'improve_bitrate': '0',
                        'version_code': '1.7.2',
                        'language': 'en',
                        'app_name': 'trill',
                        'vid': 'D7B3981F-DD46-45A1-A97E-428B90096C3E',
                        'app_version': '1.7.2',
                        'device_id': '6619780206485964289',
                        'channel': 'App Store',
                        'mcc_mnc': '',
                        'tz_offset': '28800'
                    }
                share_info = aweme.get('share_info', {})
                url = download_url.format(
                    '&'.join([key + '=' + download_params[key] for key in download_params]))
                self.queue.put(('video', uri, url, target_folder, newest_folder))
            else:
                if aweme.get('image_infos', None):
                    image = aweme['image_infos']['label_large']
                    self.queue.put(
                        ('image', image['uri'], image['url_list'][0], target_folder, newest_folder))

        except KeyError:
            return
        except UnicodeDecodeError:
            print("Cannot decode response data from DESC %s" % aweme['desc'])
            return

    # def __download_favorite_media(self, user_id, dytk, hostname, signature, favorite_folder, video_count):
    #     if not os.path.exists(favorite_folder):
    #         os.makedirs(favorite_folder)
    #     # favorite_video_url = "https://%s/aweme/v1/aweme/favorite/" % hostname
    #     favorite_video_url = "https://%s/web/api/v2/aweme/like/" % hostname
    #     favorite_video_params = {
    #         'user_id': str(user_id),
    #         'count': '21',
    #         'max_cursor': '0',
    #         'aid': '1128',
    #         '_signature': signature,
    #         'dytk': dytk
    #     }
    #     max_cursor = None
    #     while True:
    #         if max_cursor:
    #             favorite_video_params['max_cursor'] = str(max_cursor)
    #         res = requests.get(favorite_video_url,
    #                            headers=HEADERS, params=favorite_video_params)
    #         contentJson = json.loads(res.content.decode('utf-8'))
    #         favorite_list = contentJson.get('aweme_list', [])
    #         for aweme in favorite_list:
    #             video_count += 1
    #             aweme['hostname'] = hostname
    #             self._join_download_queue(aweme, favorite_folder)
    #         if contentJson.get('has_more'):
    #             max_cursor = contentJson.get('max_cursor')
    #         else:
    #             break
    #     return video_count
    def _download_video_media(self, aweme_id, url):
        current_folder = os.getcwd()
        target_folder = os.path.join(current_folder, 'download/videos')
        if not os.path.isdir(target_folder):
            os.mkdir(target_folder)

        if not aweme_id:
            print("Video %s does not exist" % aweme_id)
            return
        hostname = urllib.parse.urlparse(url).hostname
        hostname = 'aweme.snssdk.com'
        user_video_url =  "https://%s/aweme/v1/aweme/detail/" % hostname
        user_video_params = {
            'aweme_id': str(aweme_id)
        }
        # headers = {
        #     'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
        # }

        res = requests.get('https://aweme.snssdk.com/aweme/v1/aweme/detail/?aweme_id=6737210825959869708', headers=gen_header())
        contentJson = json.loads(res.content.decode('utf-8'))
        a= 1

    def _download_user_media(self, user_id, dytk, url):
        print('Start download user media: %s' % user_id)
        if not user_id:
            print("Number %s does not exist" % user_id)
            return
        current_folder = os.getcwd()
        target_folder = os.path.join(current_folder, 'download/{}_{}'.format(user_id, self.url_key[url]))
        if not os.path.isdir(target_folder):
            os.mkdir(target_folder)
        if download_favorite:
            target_folder += '/favorite'
        if not os.path.isdir(target_folder):
            os.mkdir(target_folder)
        now = datetime.now().strftime('%Y%m%d')
        newest_folder = os.path.join(current_folder, 'download/newest_video_%s' % now)
        if not os.path.isdir(newest_folder):
            os.mkdir(newest_folder)
        hostname = urllib.parse.urlparse(url).hostname
        signature = self.generateSignature(str(user_id))
        if download_favorite:
            user_video_url = "https://www.douyin.com/aweme/v1/aweme/favorite/"
            headers = gen_header(HEADERS_FAVORITE)
        else:
            user_video_url = "https://%s/aweme/v1/aweme/post/" % hostname
            headers = gen_header()
        user_video_params = {
            'user_id': str(user_id),
            'count': '21',
            'max_cursor': '0',
            'aid': '1128',
            '_signature': signature,
            'dytk': dytk
        }
        if hostname == 't.tiktok.com':
            user_video_params.pop('dytk')
            user_video_params['aid'] = '1180'

        max_cursor, video_count = None, 0
        reach_max_record = False
        res_count = 0
        while True:
            res_count += 1
            # headers = gen_header(HEADERS_FAVORITE) if download_favorite else gen_header()
            print("res_count: {} ----- {}\n".format(res_count, url))
            if max_cursor:
                user_video_params['max_cursor'] = str(max_cursor)
            res = requests.get(user_video_url, headers=headers,
                               params=user_video_params)
            contentJson = json.loads(res.content.decode('utf-8'))
            aweme_list = contentJson.get('aweme_list', [])
            for aweme in aweme_list:
                if is_reach_max_record(video_count):
                    reach_max_record = True
                    break
                video_count += 1
                aweme['hostname'] = hostname
                self._join_download_queue(aweme, target_folder, newest_folder)
            if reach_max_record:
                break
            if contentJson.get('has_more'):
                max_cursor = contentJson.get('max_cursor')
            else:
                break
        # if True:
        #     favorite_folder = target_folder + '/favorite'
        #     video_count = self.__download_favorite_media(
        #         user_id, dytk, hostname, signature, favorite_folder, video_count)

        if video_count == 0:
            print("There's no video in number %s." % user_id)

        return video_count

    def _download_challenge_media(self, challenge_id, url):
        if not challenge_id:
            print("Challenge #%s does not exist" % challenge_id)
            return
        current_folder = os.getcwd()
        target_folder = os.path.join(
            current_folder, 'download/#%s' % challenge_id)
        if not os.path.isdir(target_folder):
            os.mkdir(target_folder)

        hostname = urllib.parse.urlparse(url).hostname
        signature = self.generateSignature(str(challenge_id) + '9' + '0')

        challenge_video_url = "https://%s/aweme/v1/challenge/aweme/" % hostname
        challenge_video_params = {
            'ch_id': str(challenge_id),
            'count': '9',
            'cursor': '0',
            'aid': '1128',
            'screen_limit': '3',
            'download_click_limit': '0',
            '_signature': signature
        }

        cursor, video_count = None, 0
        while True:
            if cursor:
                challenge_video_params['cursor'] = str(cursor)
                challenge_video_params['_signature'] = self.generateSignature(
                    str(challenge_id) + '9' + str(cursor))
            res = requests.get(challenge_video_url,
                               headers=gen_header(), params=challenge_video_params)
            try:
                contentJson = json.loads(res.content.decode('utf-8'))
            except:
                print(res.content)
            aweme_list = contentJson.get('aweme_list', [])
            if not aweme_list:
                break
            for aweme in aweme_list:
                aweme['hostname'] = hostname
                video_count += 1
                self._join_download_queue(aweme, target_folder)
                print("number: ", video_count)
            if contentJson.get('has_more'):
                cursor = contentJson.get('cursor')
            else:
                break
        if video_count == 0:
            print("There's no video in challenge %s." % challenge_id)
        return video_count

    def _download_music_media(self, music_id, url):
        if not music_id:
            print("Challenge #%s does not exist" % music_id)
            return
        current_folder = os.getcwd()
        target_folder = os.path.join(current_folder, 'download/@%s' % music_id)
        if not os.path.isdir(target_folder):
            os.mkdir(target_folder)

        hostname = urllib.parse.urlparse(url).hostname
        signature = self.generateSignature(str(music_id))
        music_video_url = "https://%s/aweme/v1/music/aweme/?{0}" % hostname
        music_video_params = {
            'music_id': str(music_id),
            'count': '9',
            'cursor': '0',
            'aid': '1128',
            'screen_limit': '3',
            'download_click_limit': '0',
            '_signature': signature
        }
        if hostname == 't.tiktok.com':
            for key in ['screen_limit', 'download_click_limit', '_signature']:
                music_video_params.pop(key)
            music_video_params['aid'] = '1180'

        cursor, video_count = None, 0
        while True:
            if cursor:
                music_video_params['cursor'] = str(cursor)
                music_video_params['_signature'] = self.generateSignature(
                    str(music_id) + '9' + str(cursor))

            url = music_video_url.format(
                '&'.join([key + '=' + music_video_params[key] for key in music_video_params]))
            res = requests.get(url, headers=gen_header())
            contentJson = json.loads(res.content.decode('utf-8'))
            aweme_list = contentJson.get('aweme_list', [])
            if not aweme_list:
                break
            for aweme in aweme_list:
                aweme['hostname'] = hostname
                video_count += 1
                self._join_download_queue(aweme, target_folder)
            if contentJson.get('has_more'):
                cursor = contentJson.get('cursor')
            else:
                break
        if video_count == 0:
            print("There's no video in music %s." % music_id)
        return video_count


def usage():
    print("1. Please create file share-url.txt under this same directory.\n"
          "2. In share-url.txt, you can specify amemv share page url separated by "
          "comma/space/tab/CR. Accept multiple lines of text\n"
          "3. Save the file and retry.\n\n"
          "Sample File Content:\nurl1,url2\n\n"
          "Or use command line options:\n\n"
          "Sample:\npython amemv-video-ripper.py url1,url2\n\n\n")
    print(u"未找到share-url.txt文件，请创建.\n"
          u"请在文件中指定抖音分享页面URL，并以 逗号/空格/tab/表格鍵/回车符 分割，支持多行.\n"
          u"保存文件并重试.\n\n"
          u"例子: url1,url12\n\n"
          u"或者直接使用命令行参数指定链接\n"
          u"例子: python amemv-video-ripper.py url1,url2")


def parse_sites(fileName):
    with open(fileName, "rb") as f:
        txt = f.read().rstrip().lstrip()
        txt = codecs.decode(txt, 'utf-8')
        txt = txt.replace("\t", ",").replace(
            "\r", ",").replace("\n", ",").replace(" ", ",")
        txt = txt.split(",")
    numbers = list()
    for raw_site in txt:
        site = raw_site.lstrip().rstrip()
        if site:
            numbers.append(site)
    return numbers

download_favorite = False
hot_opt = None
allow_newest = False
max_record = None
map_opts = {
    '-h': 'hot',
    '-e': 'energy',
    '-s': 'search',
}
map_hot_func = {
    '-h': hot_video_url,
    '-e': hot_energy_url,
    '-s': hot_search_url,
}

if __name__ == "__main__":
    content, opts, args = None, None, []
    try:
        if len(sys.argv) >= 2:
            opts, args = getopt.getopt(sys.argv[1:], "hefc", ["max="])
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)

    if opts:
        for o, val in opts:
            if o in ("-h", "-e"):
                hot_opt = o
                content = get_hot_video()
            if o in ("-f"):
                download_favorite = True
            if o in ("--max"):
                max_record = int(val)
            if o in ("-c"):
                allow_newest = True
    if not hot_opt:
        if not args:
            # check the sites file
            filename = "share-url.txt"
            if os.path.exists(filename):
                content = parse_sites(filename)
            else:
                usage()
                sys.exit(1)
        else:
            print(args)
            content = (args[0] if args else '').split(",")
    print(opts)
    if len(content) == 0 or content[0] == "":
        usage()
        sys.exit(1)

    if opts:
        for o, val in opts:
            if o in ("--favorite"):
                download_favorite = True
                break

    CrawlerScheduler(content)
