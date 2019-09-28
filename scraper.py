from __future__ import print_function
import time
import sys
import json
import re
import os
from PIL import Image
import requests
from io import BytesIO
from tqdm import tqdm
from bs4 import BeautifulSoup

with open('credentials.json') as infile:
    creds = json.load(infile)

KEY = creds['KEY']
SECRET = creds['SECRET']

def download_file(url, local_filename, min_dim=None, resize_to=None):
    if local_filename is None:
        local_filename = url.split('/')[-1]
    r = requests.get(url, stream=True)
    
    response = requests.get(url)
    img = Image.open(BytesIO(response.content))
    w, h = float(img.width), float(img.height)
    aspect = w / h

    if w < min_dim or h < min_dim:
        return None

    if resize_to is not None:
        rw, rh = w / resize_to, h / resize_to
        r = min(rw, rh)
        w2, h2 = int(w/r), int(h/r)
        img = img.resize((w2, h2), Image.LANCZOS)

    img.save(local_filename)
    return local_filename


def get_group_id_from_url(url):
    params = {
        'method' : 'flickr.urls.lookupGroup',
        'url': url,
        'format': 'json',
        'api_key': KEY,
        'format': 'json',
        'nojsoncallback': 1
    }
    results = requests.get('https://api.flickr.com/services/rest', params=params).json()
    return results['group']['id']


def get_photos(qs, qg, page=1, original=False, bbox=None):
    params = {
        'content_type': '7',
        'per_page': '500',
        'media': 'photos',
        'format': 'json',
        'advanced': 1,
        'nojsoncallback': 1,
        'extras': 'media,realname,%s,o_dims,geo,tags,machine_tags,date_taken' % ('url_o' if original else 'url_l'), #url_c,url_l,url_m,url_n,url_q,url_s,url_sq,url_t,url_z',
        'page': page,
        'api_key': KEY
    }

    if qs is not None:
        params['method'] = 'flickr.photos.search',
        params['text'] = qs
    elif qg is not None:
        params['method'] = 'flickr.groups.pools.getPhotos',
        params['group_id'] = qg

    # bbox should be: minimum_longitude, minimum_latitude, maximum_longitude, maximum_latitude
    if bbox is not None and len(bbox) == 4:
        params['bbox'] = ','.join(bbox)

    results = requests.get('https://api.flickr.com/services/rest', params=params).json()['photos']
    return results


def search(qs, qg, bbox=None, original=False, max_pages=None, min_dim=None, resize_to=None):
    # create a folder for the query if it does not exist
    foldername = os.path.join('images', re.sub(r'[\W]', '_', qs if qs is not None else "group_%s"%qg))
    if bbox is not None:
        foldername += '_'.join(bbox)

    if not os.path.exists(foldername):
        os.makedirs(foldername)

    jsonfilename = os.path.join(foldername, 'results.json')

    if not os.path.exists(jsonfilename):

        # save results as a json file
        photos = []
        current_page = 1

        results = get_photos(qs, qg, page=current_page, original=original, bbox=bbox)

        total_pages = results['pages']
        if max_pages is not None and total_pages > max_pages:
            total_pages = max_pages

        photos += results['photo']

        while current_page < total_pages:
            print('downloading metadata, page {} of {}'.format(current_page, total_pages))
            current_page += 1
            photos += get_photos(qs, qg, page=current_page, original=original, bbox=bbox)['photo']
            time.sleep(0.5)

        with open(jsonfilename, 'w') as outfile:
            json.dump(photos, outfile)

    else:
        with open(jsonfilename, 'r') as infile:
            photos = json.load(infile)

    # download images
    print('Downloading images')
    for photo in tqdm(photos):
        try:
            url = photo.get('url_o' if original else 'url_l')
            extension = url.split('.')[-1]
            localname = os.path.join(foldername, '{}.{}'.format(photo['id'], extension))
            if not os.path.exists(localname):
                download_file(url, localname, min_dim=min_dim, resize_to=resize_to)
        except Exception as e:
            continue


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Download images from flickr')
    parser.add_argument('--search', '-s', dest='q_search', default=None, required=False, help='Search term')
    parser.add_argument('--group', '-g', dest='q_group', default=None, required=False, help='Group url, e.g. https://www.flickr.com/groups/scenery/')
    parser.add_argument('--original', '-o', dest='original', action='store_true', default=False, required=False, help='Download original sized photos if True, large (1024px) otherwise')
    parser.add_argument('--max-pages', '-m', dest='max_pages', type=int, required=False, help='Max pages (default none)')
    parser.add_argument('--bbox', '-b', dest='bbox', required=False, help='Bounding box to search in, separated by commas like so: minimum_longitude,minimum_latitude,maximum_longitude,maximum_latitude')
    parser.add_argument('--min-dim', '-d', dest='min_dim', type=int, default=None, required=False, help='Reject images whose smallest dimension is below this')
    parser.add_argument('--resize-to', '-r', dest='resize_to', type=int, default=None, required=False, help='Resize images so smallest dimension is this')
    args = parser.parse_args()

    qs = args.q_search
    qg = args.q_group
    original = args.original
    min_dim = args.min_dim
    resize_to = args.resize_to

    if qs is None and qg is None:
        sys.exit('Must specify a search term or group id')

    try:
        bbox = args.bbox.split(',')
    except Exception as e:
        bbox = None

    if bbox and len(bbox) != 4:
        bbox = None

    if qg is not None:
        qg = get_group_id_from_url(qg)

    print('Searching for {}'.format(qs if qs is not None else "group %s"%qg))
    if bbox:
        print('Within', bbox)

    max_pages = None
    if args.max_pages:
        max_pages = int(args.max_pages)

    search(qs, qg, bbox, original, max_pages, min_dim, resize_to)

