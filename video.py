# -*- coding:utf-8 -*-

# Copyright (c)      2013 - Christophe-Marie Duquesne
# Copyright (c) 2013-2014 - Simon Conseil

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

from __future__ import with_statement

import logging
import os
import re
import shutil
from os.path import splitext

from . import image
from .utils import call_subprocess

# TODO: merge with image.py

def check_subprocess(cmd, source, outname):
    """Run the command to resize the video and remove the output file if the
    processing fails.

    """
    logger = logging.getLogger(__name__)
    try:
        returncode, stdout, stderr = call_subprocess(cmd)
    except KeyboardInterrupt:
        logger.debug('Process terminated, removing file %s', outname)
        os.remove(outname)
        raise

    if returncode:
        logger.error('Failed to process ' + source)
        logger.debug('STDOUT:\n %s', stdout)
        logger.debug('STDERR:\n %s', stderr)
        logger.debug('Process failed, removing file %s', outname)
        os.remove(outname)


def video_size(source):
    """Returns the dimensions of the video."""

    ret, stdout, stderr = call_subprocess(['ffmpeg', '-i', source])
    pattern = re.compile(r'Stream.*Video.* ([0-9]+)x([0-9]+)')
    match = pattern.search(stderr)

    if match:
        x, y = int(match.groups()[0]), int(match.groups()[1])
    else:
        x = y = 0
    return x, y


def generate_video(source, outname, size, options=None):
    """Video processor.

    :param source: path to a video
    :param outname: path to the generated video
    :param size: size of the resized video `(width, height)`
    :param options: array of options passed to ffmpeg

    """
    logger = logging.getLogger(__name__)

    # Don't transcode if source is in the required format and
    # has fitting datedimensions, copy instead.
    w_src, h_src = video_size(source)
    w_dst, h_dst = size
    logger.debug('Video size: %i, %i -> %i, %i', w_src, h_src, w_dst, h_dst)

    base, src_ext = splitext(source)
    base, dst_ext = splitext(outname)
    if dst_ext == src_ext and w_src <= w_dst and h_src <= h_dst:
        logger.debug('Video is smaller than the max size, copying it instead')
        shutil.copy(source, outname)
        return

    # http://stackoverflow.com/questions/8218363/maintaining-ffmpeg-aspect-ratio
    # + I made a drawing on paper to figure this out
    if h_dst * w_src < h_src * w_dst:
        # biggest fitting dimension is height
        resize_opt = ['-vf', "scale=trunc(oh*a/2)*2:%i" % h_dst]
    else:
        # biggest fitting dimension is width
        resize_opt = ['-vf', "scale=%i:trunc(ow/a/2)*2" % w_dst]

    # do not resize if input dimensions are smaller than output dimensions
    if w_src <= w_dst and h_src <= h_dst:
        resize_opt = []

    # Encoding options improved, thanks to
    # http://ffmpeg.org/trac/ffmpeg/wiki/vpxEncodingGuide
    cmd = ['ffmpeg', '-i', source, '-y']  # -y to overwrite output files
    if options is not None:
        cmd += options
    cmd += resize_opt + [outname]

    logger.debug('Processing video: %s', ' '.join(cmd))
    check_subprocess(cmd, source, outname)


def generate_thumbnail(source, outname, box, fit=True, options=None):
    """Create a thumbnail image for the video source, based on ffmpeg."""

    logger = logging.getLogger(__name__)
    tmpfile = outname + ".tmp.jpg"

    # dump an image of the video
    cmd = ['ffmpeg', '-i', source, '-an', '-r', '1',
           '-vframes', '1', '-y', tmpfile]
    logger.debug('Create thumbnail for video: %s', ' '.join(cmd))
    check_subprocess(cmd, source, outname)

    # use the generate_thumbnail function from sigal.image
    image.generate_thumbnail(tmpfile, outname, box, fit, options)
    # remove the image
    os.unlink(tmpfile)


def process_video(filepath, outpath, settings):
    """Process a video: resize, create thumbnail."""

    filename = os.path.split(filepath)[1]
    basename = splitext(filename)[0]
    outname = os.path.join(outpath, basename + '.webm')

    generate_video(filepath, outname, settings['video_size'],
                   options=settings['webm_options'])

    if settings['make_thumbs']:
        thumb_name = os.path.join(outpath, get_thumb(settings, filename))
        generate_thumbnail(
            outname, thumb_name, settings['thumb_size'],
            fit=settings['thumb_fit'], options=settings['jpg_options'])

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
    return os.path.join(path, settings['thumb_dir'], settings['thumb_prefix'] +
                name + settings['thumb_suffix'] + ext)


