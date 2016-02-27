# -*- coding:utf-8 -*-

# Copyright (c) 2009-2014 - Simon Conseil

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

# Additional copyright notice:
#
# Several lines of code concerning extraction of GPS data from EXIF tags where
# taken from a GitHub Gist by Eran Sandler at
#
#   https://gist.github.com/erans/983821
#
# and partially modified. The code in question is licensed under MIT license.

# Copyright (c) 2014      - Scott Boone (https://github.com/sawall/)
# Minor updates to image.py from Sigal.

# TODO: merge with video.py

import logging
import os
import pilkit.processors
import sys

from copy import deepcopy
from datetime import datetime
from PIL.ExifTags import TAGS, GPSTAGS
from PIL import Image as PILImage
from PIL import ImageOps
from pilkit.processors import Transpose
from pilkit.utils import save_image

from . import compat #, signals

def _has_exif_tags(img):
    return hasattr(img, 'info') and 'exif' in img.info


def generate_image(source, outname, settings, options=None):
    """Image processor, rotate and resize the image.

    :param source: path to an image
    :param outname: output filename
    :param settings: settings dict
    :param options: dict with PIL options (quality, optimize, progressive)

    """

    logger = logging.getLogger(__name__)
    img = PILImage.open(source)
    original_format = img.format

    if settings['SIGLICAN_COPY_EXIF_DATA'] and settings['SIGLICAN_AUTOROTATE_IMAGES']:
        logger.warning("The 'autorotate_images' and 'copy_exif_data' settings "
                       "are not compatible because Sigal can't save the "
                       "modified Orientation tag.")

    # Preserve EXIF data
    if settings['SIGLICAN_COPY_EXIF_DATA'] and _has_exif_tags(img):
        if options is not None:
            options = deepcopy(options)
        else:
            options = {}
        options['exif'] = img.info['exif']

    # Rotate the img, and catch IOError when PIL fails to read EXIF
    if settings['SIGLICAN_AUTOROTATE_IMAGES']:
        try:
            img = Transpose().process(img)
        except (IOError, IndexError):
            pass

    # Resize the image
    if settings['SIGLICAN_IMG_PROCESSOR']:
        try:
            logger.debug('Processor: %s', settings['SIGLICAN_IMG_PROCESSOR'])
            processor_cls = getattr(pilkit.processors,
                                    settings['SIGLICAN_IMG_PROCESSOR'])
        except AttributeError:
            logger.error('Wrong processor name: %s', settings['SIGLICAN_IMG_PROCESSOR'])
            sys.exit()

        processor = processor_cls(*settings['SIGLICAN_IMG_SIZE'], upscale=False)
        img = processor.process(img)
    
    # TODO ** delete (maintained from Sigal for reference)
    # signal.send() does not work here as plugins can modify the image, so we
    # iterate other the receivers to call them with the image.
    #for receiver in signals.img_resized.receivers_for(img):
    #    img = receiver(img, settings=settings)

    outformat = img.format or original_format or 'JPEG'
    logger.debug(u'Save resized image to {0} ({1})'.format(outname, outformat))
    save_image(img, outname, outformat, options=options, autoconvert=True)


def generate_thumbnail(source, outname, box, fit=True, options=None):
    """Create a thumbnail image."""

    logger = logging.getLogger(__name__)
    img = PILImage.open(source)
    original_format = img.format

    if fit:
        img = ImageOps.fit(img, box, PILImage.ANTIALIAS)
    else:
        img.thumbnail(box, PILImage.ANTIALIAS)

    outformat = img.format or original_format or 'JPEG'
    logger.debug(u'Save thumnail image: {0} ({1})'.format(outname, outformat))
    save_image(img, outname, outformat, options=options, autoconvert=True)


def process_image(filepath, outpath, settings):
    """Process one image: resize, create thumbnail."""

    logger = logging.getLogger(__name__)
    filename = os.path.split(filepath)[1]
    outname = os.path.join(outpath, filename)
    ext = os.path.splitext(filename)[1]

    if ext in ('.jpg', '.jpeg', '.JPG', '.JPEG'):
        options = settings['SIGLICAN_JPG_OPTIONS']
    elif ext == '.png':
        options = {'optimize': True}
    else:
        options = {}

    try:
        generate_image(filepath, outname, settings, options=options)
    except Exception as e:
        logger.error('Failed to process image: %s', e)
        return

    if settings['SIGLICAN_MAKE_THUMBS']:
        thumb_name = os.path.join(outpath, get_thumb(settings, filename))
        generate_thumbnail(outname, thumb_name, settings['SIGLICAN_THUMB_SIZE'],
                           fit=settings['SIGLICAN_THUMB_FIT'], options=options)


def _get_exif_data(filename):
    """Return a dict with EXIF data."""

    img = PILImage.open(filename)
    exif = img._getexif() or {}
    data = {TAGS.get(tag, tag): value for tag, value in exif.items()}

    if 'GPSInfo' in data:
        data['GPSInfo'] = {GPSTAGS.get(tag, tag): value
                           for tag, value in data['GPSInfo'].items()}
    return data


def dms_to_degrees(v):
    """Convert degree/minute/second to decimal degrees."""

    d = float(v[0][0]) / float(v[0][1])
    m = float(v[1][0]) / float(v[1][1])
    s = float(v[2][0]) / float(v[2][1])
    return d + (m / 60.0) + (s / 3600.0)

def get_exif_tags(source):
    """Read EXIF tags from file @source and return a tuple of two dictionaries,
    the first one containing the raw EXIF data, the second one a simplified
    version with common tags.
    """

    logger = logging.getLogger(__name__)

    if os.path.splitext(source)[1].lower() not in ('.jpg', '.jpeg'):
        return (None, None)

    try:
        data = _get_exif_data(source)
    except (IOError, IndexError, TypeError, AttributeError):
        logger.warning(u'Could not read EXIF data from %s', source)
        return (None, None)

    simple = {}

    # Provide more accessible tags in the 'simple' key
    if 'FNumber' in data:
        fnumber = data['FNumber']
        if len(fnumber) == 1:
            simple['fstop'] = float(fnumber[0])
        else:
            simple['fstop'] = float(fnumber[0]) / fnumber[1]

    if 'FocalLength' in data:
        focal = data['FocalLength']
        if len(focal) == 1:
            simple['focal'] = float(focal[0])
        else:
            simple['focal'] = round(float(focal[0]) / focal[1])

    if 'ExposureTime' in data:
        exp_time = data['ExposureTime']
        if isinstance(exp_time, tuple):
            if len(exp_time) == 1:
                simple['exposure'] = str(exp_time[0])
            else:
                simple['exposure'] = '{0}/{1}'.format(*exp_time)
        elif isinstance(exp_time, int):
            simple['exposure'] = str(exp_time)
        else:
            logger.warning('Unknown format for ExposureTime: %r (%s)',
                           data['ExposureTime'], source)

    if 'ISOSpeedRatings' in data:
        simple['iso'] = data['ISOSpeedRatings']

    if 'DateTimeOriginal' in data:
        try:
            # Remove null bytes at the end if necessary
            date = data['DateTimeOriginal'][0].rsplit('\x00')[0]
            simple['dateobj'] = datetime.strptime(date, '%Y:%m:%d %H:%M:%S')
            dt = simple['dateobj'].strftime('%A, %d. %B %Y')

            if compat.PY2:
                simple['datetime'] = dt.decode('utf8')
            else:
                simple['datetime'] = dt
        except (ValueError, TypeError) as e:
            logger.warning(u'Could not parse DateTimeOriginal of %s: %s',
                           source, e)

    if 'GPSInfo' in data:
        info = data['GPSInfo']
        lat_info = info.get('GPSLatitude')
        lon_info = info.get('GPSLongitude')
        lat_ref_info = info.get('GPSLatitudeRef')
        lon_ref_info = info.get('GPSLongitudeRef')

        if lat_info and lon_info and lat_ref_info and lon_ref_info:
            try:
                lat = dms_to_degrees(lat_info)
                lon = dms_to_degrees(lon_info)
            except (ZeroDivisionError, ValueError):
                logger.warning('Failed to read GPS info for %s', source)
                lat = lon = None

            if lat and lon:
                simple['gps'] = {
                    'lat': - lat if lat_ref_info != 'N' else lat,
                    'lon': - lon if lon_ref_info != 'E' else lon,
                }

    return (data, simple)

def get_thumb(settings, filename):
    """Return the path to the thumb.

    examples:
    >>> default_settings = create_settings()
    >>> get_thumb(default_settings, "bar/foo.jpg")
    "bar/thumbnails/foo.jpg"
    >>> get_thumb(default_settings, "bar/foo.png")
    "bar/thumbnails/foo.png"

    for videos, it returns a jpg file:
    >>> get_thumb(default_settings, "bar/foo.webm")
    "bar/thumbnails/foo.jpg"
    """

    path, filen = os.path.split(filename)
    name, ext = os.path.splitext(filen)

    # TODO: replace this list with Video.extensions github #16
    if ext.lower() in ('.mov', '.avi', '.mp4', '.webm', '.ogv'):
        ext = '.jpg'
    return os.path.join(path, settings['SIGLICAN_THUMB_DIR'], settings['SIGLICAN_THUMB_PREFIX'] +
                name + settings['SIGLICAN_THUMB_SUFFIX'] + ext)

